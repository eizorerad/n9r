"""Healing Orchestrator - Coordinates all agents for auto-healing with iterative retry loop."""

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from uuid import UUID

import docker

from app.services.agents.diagnosis import DiagnosisAgent, DiagnosisResult
from app.services.agents.fix import FixAgent, FixResult
from app.services.agents.test import TestAgent, TestResult
from app.services.sandbox import Sandbox

logger = logging.getLogger(__name__)

# Configuration
MAX_HEALING_ITERATIONS = 3  # Maximum retry attempts for healing


class HealingStatus(Enum):
    """Status of healing process."""
    PENDING = "pending"
    DIAGNOSING = "diagnosing"
    FIXING = "fixing"
    TESTING = "testing"
    VALIDATING = "validating"
    RETRYING = "retrying"  # New status for retry iterations
    COMPLETED = "completed"
    FAILED = "failed"
    MANUAL_REQUIRED = "manual_required"


@dataclass
class HealingLog:
    """Log entry for healing process."""
    timestamp: datetime
    stage: str
    message: str
    details: dict = field(default_factory=dict)


@dataclass
class HealingResult:
    """Complete result of healing process."""
    issue_id: str
    status: HealingStatus
    diagnosis: DiagnosisResult | None = None
    fix: FixResult | None = None
    test: TestResult | None = None
    validation_passed: bool = False
    error_message: str | None = None
    logs: list[HealingLog] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)
    iterations_used: int = 0  # Track how many iterations were needed


class HealingOrchestrator:
    """Orchestrates the complete healing process with iterative retry support."""

    def __init__(self, max_iterations: int = MAX_HEALING_ITERATIONS):
        self.diagnosis_agent = DiagnosisAgent()
        self.fix_agent = FixAgent()
        self.test_agent = TestAgent()
        self.max_iterations = max_iterations
        # Docker client for sandbox creation
        self._docker_client: docker.DockerClient | None = None

    def _get_docker_client(self) -> docker.DockerClient:
        """Get or create Docker client lazily."""
        if self._docker_client is None:
            self._docker_client = docker.from_env()
        return self._docker_client

    async def heal_issue(
        self,
        issue: dict,
        repository: dict,
        file_content: str,
        related_files: list[dict] | None = None,
        on_log: Callable | None = None,
        max_iterations: int | None = None,
        access_token: str | None = None,
    ) -> HealingResult:
        """
        Execute the complete healing process for an issue with iterative retry.
        
        If validation fails, the process will retry up to max_iterations times,
        passing the error output back to the FixAgent to generate an improved fix.
        
        Args:
            issue: Issue dict with type, severity, title, description, etc.
            repository: Repository dict with id, full_name, clone_url, etc.
            file_content: Content of the file with the issue
            related_files: List of related file contents for context
            on_log: Callback for log events (for streaming to UI)
            max_iterations: Override default max iterations
            access_token: GitHub access token for cloning private repositories
        
        Returns:
            HealingResult with complete healing status
        """
        max_iter = max_iterations or self.max_iterations

        result = HealingResult(
            issue_id=issue.get("id", "unknown"),
            status=HealingStatus.PENDING,
        )

        def log(stage: str, message: str, details: dict = None):
            entry = HealingLog(
                timestamp=datetime.utcnow(),
                stage=stage,
                message=message,
                details=details or {},
            )
            result.logs.append(entry)
            logger.info(f"[{stage}] {message}")
            if on_log:
                on_log(entry)

        try:
            # Stage 1: Diagnosis (only done once)
            log("diagnosis", "Starting issue diagnosis")
            result.status = HealingStatus.DIAGNOSING

            diagnosis = await self.diagnosis_agent.diagnose(
                issue=issue,
                file_content=file_content,
                related_files=related_files,
            )
            result.diagnosis = diagnosis

            log("diagnosis", "Diagnosis complete", {
                "fix_path": diagnosis.fix_path.value,
                "confidence": diagnosis.confidence,
                "complexity": diagnosis.complexity_score,
                "can_auto_fix": diagnosis.can_auto_fix,
            })

            # Check if auto-fix is possible
            if not diagnosis.can_auto_fix:
                log("diagnosis", "Issue requires manual intervention")
                result.status = HealingStatus.MANUAL_REQUIRED
                return result

            # Iterative Fix-Test-Validate Loop
            previous_error: str | None = None
            current_file_content = file_content

            for iteration in range(1, max_iter + 1):
                result.iterations_used = iteration

                if iteration > 1:
                    log("retry", f"Starting retry iteration {iteration}/{max_iter}", {
                        "previous_error": previous_error[:500] if previous_error else None,
                    })
                    result.status = HealingStatus.RETRYING

                # Stage 2: Fix Generation (with previous error context if retrying)
                log("fix", f"Generating code fix (iteration {iteration})")
                result.status = HealingStatus.FIXING

                fix = await self.fix_agent.generate_fix(
                    diagnosis=diagnosis,
                    issue=issue,
                    file_content=current_file_content,
                    repository_id=str(repository.get("id", "")),
                    previous_error=previous_error,
                    iteration=iteration,
                )
                result.fix = fix

                if not fix.success:
                    log("fix", "Fix generation failed", {"error": fix.explanation})
                    # If fix generation itself fails, try again if we have iterations left
                    if iteration < max_iter:
                        previous_error = f"Fix generation failed: {fix.explanation}"
                        continue
                    result.status = HealingStatus.FAILED
                    result.error_message = "Failed to generate fix after all attempts"
                    return result

                log("fix", "Fix generated successfully", {
                    "changes": fix.changes_summary,
                    "confidence": fix.confidence,
                    "iteration": iteration,
                })

                # Stage 3: Test Generation
                log("test", "Generating regression test")
                result.status = HealingStatus.TESTING

                test = await self.test_agent.generate_test(
                    fix_result=fix,
                    issue=issue,
                )
                result.test = test

                if test.success:
                    log("test", f"Generated {test.test_count} test(s)", {
                        "framework": test.test_framework,
                        "test_file": test.test_file_path,
                    })
                else:
                    log("test", "Test generation failed, continuing without tests")

                # Stage 4: Sandbox Validation
                log("validation", f"Validating fix in sandbox (iteration {iteration})")
                result.status = HealingStatus.VALIDATING

                validation_result = await self._validate_in_sandbox(
                    repository=repository,
                    fix=fix,
                    test=test,
                    access_token=access_token,
                )

                result.validation_passed = validation_result["passed"]

                if validation_result["passed"]:
                    log("validation", f"Validation passed on iteration {iteration}", {
                        **validation_result,
                        "iterations_used": iteration,
                    })
                    result.status = HealingStatus.COMPLETED
                    return result

                # Validation failed - prepare for retry
                error_details = self._extract_error_details(validation_result)
                previous_error = error_details

                log("validation", f"Validation failed on iteration {iteration}", {
                    "error": validation_result.get("error", "Unknown error"),
                    "details": error_details[:500] if error_details else None,
                    "will_retry": iteration < max_iter,
                })

                # Update file content for next iteration if we got partial fix
                if fix.fixed_content and fix.fixed_content != current_file_content:
                    # Keep the attempted fix as base for next iteration
                    # This allows building upon partial improvements
                    pass  # current_file_content remains original to avoid accumulating errors

            # All iterations exhausted
            log("failed", f"Healing failed after {max_iter} iterations", {
                "last_error": previous_error[:500] if previous_error else None,
            })
            result.status = HealingStatus.FAILED
            result.error_message = f"Validation failed after {max_iter} attempts. Last error: {previous_error}"
            return result

        except Exception as e:
            logger.error(f"Healing failed with exception: {e}")
            result.status = HealingStatus.FAILED
            result.error_message = str(e)
            log("error", f"Healing process failed: {e}")
            return result

    def _extract_error_details(self, validation_result: dict) -> str:
        """Extract detailed error information from validation result for retry context."""
        error_parts = []

        # Main error message
        if validation_result.get("error"):
            error_parts.append(f"Error: {validation_result['error']}")

        # Lint check details
        if "details" in validation_result:
            details = validation_result["details"]
            if isinstance(details, dict):
                if details.get("output"):
                    error_parts.append(f"Output:\n{details['output']}")
                if details.get("error"):
                    error_parts.append(f"Details: {details['error']}")

        # Test failure output
        if validation_result.get("tests") and isinstance(validation_result["tests"], dict):
            tests = validation_result["tests"]
            if tests.get("output"):
                error_parts.append(f"Test output:\n{tests['output']}")

        # Lint failure output
        if validation_result.get("lint") and isinstance(validation_result["lint"], dict):
            lint = validation_result["lint"]
            if lint.get("output"):
                error_parts.append(f"Lint output:\n{lint['output']}")

        return "\n\n".join(error_parts) if error_parts else "Validation failed (no details)"

    async def _validate_in_sandbox(
        self,
        repository: dict,
        fix: FixResult,
        test: TestResult,
        access_token: str | None = None,
    ) -> dict:
        """Validate the fix in a sandbox environment.
        
        SECURITY NOTE:
        - Sandbox runs with network_mode="none" (complete network isolation)
        - Repository is cloned on HOST before sandbox starts
        - Fix and test files are written to host workdir (mounted into sandbox)
        - Sandbox only performs local linting/testing on mounted files
        
        Args:
            repository: Repository dict with clone_url, default_branch, id
            fix: FixResult with file_path and fixed_content
            test: TestResult with test_file_path and test_content
            access_token: GitHub access token for private repositories
            
        Returns:
            Dict with passed, lint, tests, error keys
        """
        # Get repository ID for sandbox naming
        repo_id_str = str(repository.get("id", "unknown"))
        try:
            repo_uuid = UUID(repo_id_str)
        except (ValueError, TypeError):
            repo_uuid = UUID("00000000-0000-0000-0000-000000000000")

        # Create sandbox instance
        sandbox = Sandbox(
            client=self._get_docker_client(),
            repository_id=repo_uuid,
            memory_limit="512m",
            cpu_limit=1.0,
            timeout=300,  # 5 minute timeout for validation
        )

        try:
            # Use async context manager for automatic cleanup
            async with sandbox:
                # STEP 1: Clone repository on HOST (sandbox has no network)
                # This is critical - clone happens BEFORE sandbox starts network isolation
                clone_url = repository.get("clone_url", "")
                default_branch = repository.get("default_branch", "main")

                logger.info("[SECURITY] Cloning repository on HOST (sandbox has network_mode=none)")
                clone_success = sandbox.clone_repository_on_host(
                    clone_url=clone_url,
                    branch=default_branch,
                    depth=1,
                    access_token=access_token,
                )

                if not clone_success:
                    return {
                        "passed": False,
                        "error": "Failed to clone repository on host",
                    }

                # STEP 2: Write fixed file to sandbox's workdir (on host, mounted into sandbox)
                repo_dir = Path(sandbox.workdir) / "repo"

                # Normalize file path (remove leading slashes, handle relative paths)
                normalized_fix_path = fix.file_path.lstrip("/")
                fix_full_path = repo_dir / normalized_fix_path

                logger.info(f"Writing fix to: {fix_full_path}")
                try:
                    fix_full_path.parent.mkdir(parents=True, exist_ok=True)
                    fix_full_path.write_text(fix.fixed_content)
                except Exception as e:
                    return {
                        "passed": False,
                        "error": f"Failed to write fix file: {e}",
                    }

                # STEP 3: Write test file if generated
                if test.success and test.test_content and test.test_file_path:
                    normalized_test_path = test.test_file_path.lstrip("/")
                    test_full_path = repo_dir / normalized_test_path

                    logger.info(f"Writing test to: {test_full_path}")
                    try:
                        test_full_path.parent.mkdir(parents=True, exist_ok=True)
                        test_full_path.write_text(test.test_content)
                    except Exception as e:
                        logger.warning(f"Failed to write test file: {e}")
                        # Continue without tests

                # STEP 4: Run lint check in sandbox
                lint_result = await self._run_lint_check_in_sandbox(
                    sandbox, normalized_fix_path
                )

                if not lint_result["passed"]:
                    return {
                        "passed": False,
                        "error": "Lint check failed",
                        "details": lint_result,
                        "lint": lint_result,
                    }

                # STEP 5: Run tests if available
                test_result_output = None
                if test.success and test.test_file_path:
                    normalized_test_path = test.test_file_path.lstrip("/")
                    test_result_output = await self._run_tests_in_sandbox(
                        sandbox, normalized_test_path, test.test_framework
                    )

                    if not test_result_output["passed"]:
                        return {
                            "passed": False,
                            "error": "Tests failed",
                            "details": test_result_output,
                            "tests": test_result_output,
                        }

                # All checks passed
                return {
                    "passed": True,
                    "lint": lint_result,
                    "tests": test_result_output,
                }

        except Exception as e:
            logger.error(f"Sandbox validation failed: {e}")
            return {"passed": False, "error": str(e)}

    async def _run_lint_check_in_sandbox(
        self, sandbox: Sandbox, file_path: str
    ) -> dict:
        """Run lint check on the fixed file inside sandbox.
        
        Args:
            sandbox: Active Sandbox instance
            file_path: Path to file relative to /workspace/repo
            
        Returns:
            Dict with passed, output, skipped, error keys
        """
        try:
            # Determine lint command based on file extension
            full_path = f"/workspace/repo/{file_path}"

            if file_path.endswith('.py'):
                cmd = f"python -m py_compile {full_path}"
                timeout = 30
            elif file_path.endswith(('.ts', '.tsx')):
                cmd = f"npx tsc --noEmit {full_path}"
                timeout = 60
            elif file_path.endswith(('.js', '.jsx')):
                cmd = f"node --check {full_path}"
                timeout = 30
            else:
                # Skip lint for unknown file types
                return {"passed": True, "skipped": True, "output": ""}

            # Execute lint command in sandbox
            exit_code, output = await sandbox.exec(
                command=cmd,
                workdir="/workspace/repo",
                timeout=timeout,
            )

            return {
                "passed": exit_code == 0,
                "output": output,
                "exit_code": exit_code,
            }

        except Exception as e:
            logger.error(f"Lint check failed: {e}")
            return {"passed": False, "error": str(e), "output": ""}

    async def _run_tests_in_sandbox(
        self, sandbox: Sandbox, test_file_path: str, test_framework: str
    ) -> dict:
        """Run the generated tests inside sandbox.
        
        Args:
            sandbox: Active Sandbox instance
            test_file_path: Path to test file relative to /workspace/repo
            test_framework: Test framework (pytest, jest, vitest)
            
        Returns:
            Dict with passed, output, skipped, error keys
        """
        try:
            full_path = f"/workspace/repo/{test_file_path}"

            if test_framework == "pytest":
                cmd = f"python -m pytest {full_path} -v --tb=short"
                timeout = 120
            elif test_framework in ("jest", "vitest"):
                cmd = f"npx {test_framework} {full_path} --passWithNoTests"
                timeout = 120
            else:
                # Unknown framework - skip tests
                return {"passed": True, "skipped": True, "output": ""}

            # Execute test command in sandbox
            exit_code, output = await sandbox.exec(
                command=cmd,
                workdir="/workspace/repo",
                timeout=timeout,
            )

            return {
                "passed": exit_code == 0,
                "output": output,
                "exit_code": exit_code,
            }

        except Exception as e:
            logger.error(f"Test execution failed: {e}")
            return {"passed": False, "error": str(e), "output": ""}
