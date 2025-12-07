"""Sandbox service for isolated code execution."""

import logging
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any
from uuid import UUID

import docker
from docker.errors import ImageNotFound

from app.core.config import settings

logger = logging.getLogger(__name__)


def get_sandbox_base_dir() -> str:
    """Get base directory for sandbox workdirs.

    Uses SANDBOX_ROOT_DIR from settings, defaulting to /tmp.
    Creates the directory if it doesn't exist.

    Returns:
        Path to base directory for sandbox workdirs.
    """
    base_dir = settings.sandbox_root_dir or "/tmp"
    os.makedirs(base_dir, exist_ok=True)
    return base_dir


def get_host_mount_path(container_path: str) -> str:
    """Translate container path to host path for Docker volume mounting.

    When Celery runs inside a Docker container, the sandbox workdir path
    (e.g., /app/sandbox_data/n9r-sandbox-xxx) must be translated to the
    corresponding path on the Docker host for sibling container mounting.

    For local development (host_sandbox_path is empty), returns the path unchanged.

    Example:
        Container path: /app/sandbox_data/n9r-sandbox-abc123
        Host path:      /home/user/n9r/sandbox_data/n9r-sandbox-abc123

    Args:
        container_path: Path inside the Celery container.

    Returns:
        Corresponding path on Docker host (or unchanged for local dev).
    """
    host_path = settings.host_sandbox_path
    container_base = settings.sandbox_root_dir

    # Local development mode - no translation needed
    if not host_path:
        return container_path

    # Docker mode - translate path
    if container_path.startswith(container_base):
        return container_path.replace(container_base, host_path, 1)

    # Path doesn't match expected base - return unchanged with warning
    logger.warning(
        f"Sandbox path '{container_path}' doesn't start with expected base '{container_base}'. "
        "Volume mounting may fail in Docker mode."
    )
    return container_path


# Sandbox Docker image configuration
SANDBOX_IMAGE = "n9r-sandbox:latest"
SANDBOX_DOCKERFILE = """
FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    jq \
    && rm -rf /var/lib/apt/lists/*

# Install Node.js (for JavaScript/TypeScript analysis)
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# Install analysis tools
RUN pip install --no-cache-dir \
    radon \
    lizard \
    pylint \
    flake8 \
    bandit \
    tree-sitter \
    tree-sitter-python \
    tree-sitter-javascript \
    tree-sitter-typescript

# Install npm tools
RUN npm install -g \
    jscpd \
    eslint \
    typescript

# Create non-root user
RUN useradd -m -s /bin/bash sandbox
USER sandbox
WORKDIR /workspace

# Set environment
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
"""


class SandboxManager:
    """Manages isolated sandbox containers for code analysis."""

    def __init__(self):
        self.client = docker.from_env()
        self._ensure_image()

    def _ensure_image(self):
        """Ensure sandbox image exists, build if necessary."""
        try:
            self.client.images.get(SANDBOX_IMAGE)
            logger.info(f"Sandbox image {SANDBOX_IMAGE} found")
        except ImageNotFound:
            logger.info(f"Building sandbox image {SANDBOX_IMAGE}")
            # Build image from Dockerfile string
            with tempfile.TemporaryDirectory() as tmpdir:
                dockerfile_path = Path(tmpdir) / "Dockerfile"
                dockerfile_path.write_text(SANDBOX_DOCKERFILE)
                self.client.images.build(
                    path=tmpdir,
                    tag=SANDBOX_IMAGE,
                    rm=True,
                )
            logger.info(f"Sandbox image {SANDBOX_IMAGE} built successfully")

    async def create_sandbox(
        self,
        repository_id: UUID,
        memory_limit: str = "4g",
        cpu_limit: float = 2.0,
        timeout: int = 1800,  # 30 minutes
    ) -> "Sandbox":
        """Create a new sandbox for a repository."""
        sandbox = Sandbox(
            client=self.client,
            repository_id=repository_id,
            memory_limit=memory_limit,
            cpu_limit=cpu_limit,
            timeout=timeout,
        )
        await sandbox.start()
        return sandbox


class Sandbox:
    """An isolated sandbox container for code analysis.

    SECURITY NOTE:
    This sandbox runs with network_mode="none" which provides complete
    network isolation. The container cannot:
    - Access the internet
    - Access internal services (PostgreSQL, Redis, etc.)
    - Communicate with other containers

    Repository code is cloned on the HOST before the sandbox starts,
    then mounted into the sandbox via volume. This ensures malicious
    code in the repository cannot make network requests.

    See docs/sandbox_security_research.md for full security analysis.
    """

    def __init__(
        self,
        client: docker.DockerClient,
        repository_id: UUID,
        memory_limit: str = "4g",
        cpu_limit: float = 2.0,
        timeout: int = 1800,
    ):
        self.client = client
        self.repository_id = repository_id
        self.memory_limit = memory_limit
        self.cpu_limit = cpu_limit
        self.timeout = timeout
        self.container = None
        self.workdir = None

    def _supports_storage_opt(self) -> bool:
        """Check if Docker storage driver supports storage_opt.

        storage_opt with size limit is only supported by:
        - devicemapper
        - overlay2 with xfs backing filesystem

        Returns False for other drivers to prevent container start failures.
        """
        try:
            info = self.client.info()
            driver = info.get("Driver", "")
            # overlay2 with xfs supports quota
            # devicemapper supports size option
            return driver in ("devicemapper",)
        except Exception:
            return False

    async def start(self):
        """Start the sandbox container."""
        # Create temporary directory for repository
        # Uses configurable base directory for Docker compatibility
        base_dir = get_sandbox_base_dir()
        self.workdir = tempfile.mkdtemp(
            prefix=f"n9r-sandbox-{self.repository_id}-",
            dir=base_dir,
        )

        logger.info(f"Starting sandbox for repository {self.repository_id}")
        logger.info(f"Sandbox workdir: {self.workdir}")

        # Translate path for Docker volume mounting
        # When Celery runs in Docker, we need to use the host path for volumes
        host_workdir = get_host_mount_path(self.workdir)
        if host_workdir != self.workdir:
            logger.info(f"Docker mode: host path = {host_workdir}")

        # Run container with security constraints
        # SECURITY: network_mode="none" prevents any network access from sandbox
        # Repository is cloned on host before sandbox starts (via RepoAnalyzer)
        # Sandbox only performs local analysis on mounted files
        self.container = self.client.containers.run(
            SANDBOX_IMAGE,
            command="sleep infinity",  # Keep container running
            detach=True,
            volumes={
                host_workdir: {"bind": "/workspace", "mode": "rw"},
            },
            mem_limit=self.memory_limit,
            nano_cpus=int(self.cpu_limit * 1e9),
            # SECURITY FIX: Complete network isolation
            # Previously: network_mode="bridge" allowed unrestricted internet access
            # Risk: Malicious code could attack internal network or exfiltrate data
            # See: docs/sandbox_security_research.md for full analysis
            network_mode="none",
            security_opt=["no-new-privileges:true"],
            cap_drop=["ALL"],
            read_only=False,  # Need to write to /workspace
            tmpfs={"/tmp": "size=1G,mode=1777"},
            # Additional security: limit disk space
            storage_opt={"size": "10G"} if self._supports_storage_opt() else {},
            environment={
                "HOME": "/workspace",
                "PYTHONDONTWRITEBYTECODE": "1",
            },
        )

        # FIX: Docker permissions issue
        # Files cloned on host may have different uid than sandbox user inside container.
        # Run chown as root to fix ownership before any sandbox operations.
        # This ensures sandbox user (uid=1000) can write to /workspace (e.g., __pycache__, .pytest_cache)
        self.container.exec_run(
            "chown -R sandbox:sandbox /workspace",
            user="root",
        )

        logger.info(f"Sandbox container {self.container.id[:12]} started with fixed permissions")

    def clone_repository_on_host(
        self,
        clone_url: str,
        branch: str = "main",
        depth: int = 1,
        access_token: str | None = None,
    ) -> bool:
        """Clone a repository on the HOST into the sandbox's workdir.

        SECURITY: This method clones on the host machine, NOT inside the sandbox.
        This is required because the sandbox has network_mode="none" and cannot
        access the internet.

        The cloned repository is placed in self.workdir which is mounted into
        the sandbox at /workspace. After cloning, the sandbox can analyze the
        code without any network access.

        Args:
            clone_url: Git repository URL
            branch: Branch to clone
            depth: Clone depth (1 for shallow clone)
            access_token: GitHub access token for private repos

        Returns:
            True if clone succeeded, False otherwise
        """
        import subprocess

        if not self.workdir:
            logger.error("Sandbox workdir not initialized. Call start() first.")
            return False

        # Construct authenticated URL if token provided
        authenticated_url = clone_url
        if access_token and "github.com" in clone_url:
            # Insert token into URL for private repos
            authenticated_url = clone_url.replace(
                "https://github.com",
                f"https://x-access-token:{access_token}@github.com"
            )

        repo_dir = Path(self.workdir) / "repo"

        logger.info(f"Cloning repository on host to {repo_dir}")
        logger.info("[SECURITY] Clone happens on HOST, sandbox has no network access")

        try:
            result = subprocess.run(
                [
                    "git", "clone",
                    "--depth", str(depth),
                    "--branch", branch,
                    authenticated_url,
                    str(repo_dir),
                ],
                capture_output=True,
                text=True,
                timeout=300,  # 5 minute timeout
            )

            if result.returncode != 0:
                logger.error(f"Git clone failed: {result.stderr}")
                return False

            logger.info(f"Repository cloned successfully to {repo_dir}")

            # Fix permissions so sandbox user can write to cloned files
            self.fix_workspace_permissions()

            return True

        except subprocess.TimeoutExpired:
            logger.error("Git clone timed out after 300 seconds")
            return False
        except Exception as e:
            logger.error(f"Clone failed: {e}")
            return False

    def fix_workspace_permissions(self) -> bool:
        """Fix permissions on workspace directory for sandbox user.

        Called after cloning or writing files to ensure sandbox user
        (uid=1000 inside container) can read/write all files.

        This is necessary because:
        - Files cloned on host have host process uid (may be root or different uid)
        - Sandbox container runs as 'sandbox' user (uid=1000)
        - Without chown, sandbox user gets Permission denied on write operations

        Returns:
            True if permissions fixed successfully, False otherwise
        """
        if not self.container:
            logger.warning("Cannot fix permissions: container not started")
            return False

        try:
            exit_code, output = self.container.exec_run(
                "chown -R sandbox:sandbox /workspace",
                user="root",
                demux=True,
            )

            if exit_code != 0:
                stderr = output[1].decode() if output[1] else ""
                logger.error(f"Failed to fix permissions: {stderr}")
                return False

            logger.info("Fixed workspace permissions for sandbox user")
            return True

        except Exception as e:
            logger.error(f"Error fixing permissions: {e}")
            return False

    async def clone_repository(
        self,
        clone_url: str,
        branch: str = "main",
        depth: int = 1,
        access_token: str | None = None,
    ) -> bool:
        """Clone a repository into the sandbox.

        DEPRECATED: This method will NOT work with network_mode="none".
        Use clone_repository_on_host() instead.

        This method is kept for backwards compatibility but will fail
        because the sandbox container has no network access.
        """
        logger.warning(
            "clone_repository() called but sandbox has network_mode='none'. "
            "Use clone_repository_on_host() instead for host-side cloning."
        )

        # Construct authenticated URL if token provided
        if access_token and "github.com" in clone_url:
            # Insert token into URL for private repos
            clone_url = clone_url.replace(
                "https://github.com",
                f"https://{access_token}@github.com"
            )

        # This will fail because network_mode="none"
        cmd = f"git clone --depth {depth} --branch {branch} {clone_url} repo"

        try:
            exit_code, output = await self.exec(cmd, workdir="/workspace")
            if exit_code != 0:
                logger.error(f"Git clone failed (expected - no network): {output}")
                return False
            logger.info("Repository cloned successfully")
            return True
        except Exception as e:
            logger.error(f"Clone failed: {e}")
            return False

    async def exec(
        self,
        command: str,
        workdir: str = "/workspace/repo",
        timeout: int | None = None,
    ) -> tuple[int, str]:
        """Execute a command in the sandbox.

        SECURITY: The command string is passed to sh -c, so it supports shell
        features like pipes and redirects. However, any dynamic values
        (especially file paths) MUST be escaped with shlex.quote() before
        being interpolated into the command string to prevent injection.

        For commands with untrusted arguments, prefer exec_args() instead.
        """
        if not self.container:
            raise RuntimeError("Sandbox not started")

        timeout = timeout or self.timeout

        logger.debug(f"Executing in sandbox: {command}")

        # Execute command via shell
        # SECURITY: Command is passed as a list to avoid double-escaping issues.
        # The caller is responsible for escaping any dynamic values in the command.
        exec_result = self.container.exec_run(
            ["sh", "-c", command],
            workdir=workdir,
            demux=True,
        )

        exit_code = exec_result.exit_code
        stdout = exec_result.output[0] or b""
        stderr = exec_result.output[1] or b""

        output = (stdout + stderr).decode("utf-8", errors="replace")

        return exit_code, output

    async def exec_args(
        self,
        args: list[str],
        workdir: str = "/workspace/repo",
        timeout: int | None = None,
    ) -> tuple[int, str]:
        """Execute a command in the sandbox without shell interpretation.

        SECURITY: This method executes commands directly without a shell,
        making it safe for untrusted arguments (e.g., file paths from repos).
        No shell escaping is needed. This is the preferred method when
        shell features (pipes, redirects, etc.) are not required.

        Args:
            args: Command and arguments as a list, e.g., ["python", "-m", "pytest", "test.py"]
            workdir: Working directory inside the container
            timeout: Command timeout in seconds

        Returns:
            Tuple of (exit_code, combined stdout+stderr output)
        """
        if not self.container:
            raise RuntimeError("Sandbox not started")

        timeout = timeout or self.timeout

        logger.debug(f"Executing in sandbox (no shell): {args}")

        # Execute command directly without shell - safe for untrusted arguments
        exec_result = self.container.exec_run(
            args,
            workdir=workdir,
            demux=True,
        )

        exit_code = exec_result.exit_code
        stdout = exec_result.output[0] or b""
        stderr = exec_result.output[1] or b""

        output = (stdout + stderr).decode("utf-8", errors="replace")

        return exit_code, output

    async def run_analysis_tool(
        self,
        tool: str,
        args: list[str] | None = None,
        output_format: str = "json",
    ) -> dict[str, Any]:
        """Run a specific analysis tool."""
        args = args or []

        tool_commands = {
            "radon_cc": f"radon cc {' '.join(args)} -j .",
            "radon_mi": f"radon mi {' '.join(args)} -j .",
            "lizard": f"lizard {' '.join(args)} --csv .",
            "jscpd": f"jscpd {' '.join(args)} --reporters json .",
            "pylint": f"pylint {' '.join(args)} --output-format=json .",
            "flake8": f"flake8 {' '.join(args)} --format=json .",
            "eslint": f"npx eslint {' '.join(args)} --format json .",
        }

        if tool not in tool_commands:
            raise ValueError(f"Unknown tool: {tool}")

        cmd = tool_commands[tool]
        exit_code, output = await self.exec(cmd)

        # Parse JSON output
        try:
            import json
            result = json.loads(output)
            return {"status": "success", "data": result, "exit_code": exit_code}
        except json.JSONDecodeError:
            return {"status": "error", "output": output, "exit_code": exit_code}

    async def get_file_list(self, extensions: list[str] | None = None) -> list[str]:
        """Get list of files in the repository."""
        cmd = "find . -type f"
        if extensions:
            ext_filter = " -o ".join([f'-name "*.{ext}"' for ext in extensions])
            cmd = f"find . -type f \\( {ext_filter} \\)"

        exit_code, output = await self.exec(cmd)
        if exit_code != 0:
            return []

        files = [f.strip() for f in output.split("\n") if f.strip()]
        return files

    async def read_file(self, filepath: str) -> str | None:
        """Read a file from the repository."""
        cmd = f"cat '{filepath}'"
        exit_code, output = await self.exec(cmd)
        return output if exit_code == 0 else None

    async def get_file_stats(self) -> dict[str, Any]:
        """Get statistics about files in the repository."""
        # Count lines of code by extension
        cmd = """
        find . -type f -name '*.py' | xargs wc -l 2>/dev/null | tail -1 | awk '{print $1}'
        """
        _, py_lines = await self.exec(cmd)

        cmd = """
        find . -type f \\( -name '*.js' -o -name '*.ts' -o -name '*.tsx' -o -name '*.jsx' \\) | xargs wc -l 2>/dev/null | tail -1 | awk '{print $1}'
        """
        _, js_lines = await self.exec(cmd)

        # Count files
        cmd = "find . -type f | wc -l"
        _, file_count = await self.exec(cmd)

        return {
            "python_lines": int(py_lines.strip() or 0),
            "javascript_lines": int(js_lines.strip() or 0),
            "total_files": int(file_count.strip() or 0),
        }

    async def cleanup(self):
        """Stop and remove the sandbox."""
        if self.container:
            try:
                self.container.stop(timeout=5)
                self.container.remove(force=True)
                logger.info(f"Sandbox container {self.container.id[:12]} removed")
            except Exception as e:
                logger.error(f"Failed to cleanup container: {e}")

        if self.workdir and os.path.exists(self.workdir):
            try:
                shutil.rmtree(self.workdir)
                logger.info(f"Sandbox workdir {self.workdir} removed")
            except Exception as e:
                logger.error(f"Failed to cleanup workdir: {e}")

    async def __aenter__(self):
        """Context manager entry."""
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        await self.cleanup()


# Singleton manager
_sandbox_manager: SandboxManager | None = None


def get_sandbox_manager() -> SandboxManager:
    """Get or create sandbox manager singleton."""
    global _sandbox_manager
    if _sandbox_manager is None:
        _sandbox_manager = SandboxManager()
    return _sandbox_manager
