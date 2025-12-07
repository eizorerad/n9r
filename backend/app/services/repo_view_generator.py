"""Repository view generator for AI scan.

Generates an LLM-friendly markdown representation of a repository,
respecting token budgets and prioritizing important files.
"""

import logging
import os
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

# Directories to exclude from analysis
EXCLUDED_DIRS = {
    ".git",
    ".svn",
    ".hg",
    ".bzr",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".tox",
    ".nox",
    ".venv",
    "venv",
    "env",
    ".env",
    "dist",
    "build",
    "target",
    "out",
    ".next",
    ".nuxt",
    "coverage",
    ".coverage",
    "htmlcov",
    ".hypothesis",
    ".eggs",
    "*.egg-info",
    "vendor",
    "bower_components",
    ".gradle",
    ".idea",
    ".vscode",
    ".DS_Store",
}

# File extensions to include
SOURCE_EXTENSIONS = {
    ".py",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".java",
    ".go",
    ".rs",
    ".rb",
    ".php",
    ".c",
    ".cpp",
    ".h",
    ".hpp",
    ".cs",
    ".swift",
    ".kt",
    ".scala",
    ".vue",
    ".svelte",
}

CONFIG_EXTENSIONS = {
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".ini",
    ".cfg",
    ".conf",
    ".env.example",
}

DOC_EXTENSIONS = {
    ".md",
    ".rst",
    ".txt",
}

# Entry point file patterns (high priority)
ENTRY_POINT_PATTERNS = {
    "main.py",
    "app.py",
    "index.py",
    "__main__.py",
    "manage.py",
    "wsgi.py",
    "asgi.py",
    "index.js",
    "index.ts",
    "main.js",
    "main.ts",
    "app.js",
    "app.ts",
    "server.js",
    "server.ts",
    "index.jsx",
    "index.tsx",
    "App.jsx",
    "App.tsx",
    "main.go",
    "Main.java",
    "Program.cs",
    "main.rs",
    "lib.rs",
}

# Config file patterns (high priority)
CONFIG_PATTERNS = {
    "pyproject.toml",
    "setup.py",
    "setup.cfg",
    "requirements.txt",
    "Pipfile",
    "package.json",
    "tsconfig.json",
    "webpack.config.js",
    "vite.config.ts",
    "next.config.js",
    "next.config.ts",
    "tailwind.config.js",
    "tailwind.config.ts",
    "Cargo.toml",
    "go.mod",
    "pom.xml",
    "build.gradle",
    "Gemfile",
    "composer.json",
    "Dockerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
    ".env.example",
    "alembic.ini",
}

# Core logic directory patterns (medium-high priority)
CORE_DIR_PATTERNS = {
    "src",
    "lib",
    "core",
    "services",
    "domain",
    "models",
    "entities",
    "utils",
    "helpers",
    "common",
}

# API directory patterns (medium priority)
API_DIR_PATTERNS = {
    "api",
    "routes",
    "controllers",
    "handlers",
    "endpoints",
    "views",
    "resources",
}

# Default token budget (800K tokens)
DEFAULT_TOKEN_BUDGET = 800_000

# Maximum file size to include fully (in characters)
MAX_FILE_SIZE = 50_000  # ~12.5K tokens

# Excerpt size for large files
EXCERPT_SIZE = 4_000  # ~1K tokens


@dataclass
class FileInfo:
    """Information about a file for prioritization."""

    path: Path
    relative_path: str
    size: int
    priority: int  # Lower is higher priority


@dataclass
class RepoViewResult:
    """Result of repo view generation."""

    content: str
    token_estimate: int
    files_included: int
    files_truncated: int
    total_files: int


class RepoViewGenerator:
    """Generates LLM-friendly markdown view of repository."""

    def __init__(self, repo_path: Path, token_budget: int = DEFAULT_TOKEN_BUDGET):
        """Initialize the generator.

        Args:
            repo_path: Path to the repository root
            token_budget: Maximum tokens to include (default 800K)
        """
        self.repo_path = Path(repo_path)
        self.token_budget = token_budget

    def _estimate_tokens(self, text: str) -> int:
        """Estimate token count for text.

        Uses approximation of ~4 characters per token.

        Args:
            text: Text to estimate tokens for

        Returns:
            Estimated token count
        """
        return len(text) // 4

    def _should_exclude_dir(self, dir_name: str) -> bool:
        """Check if a directory should be excluded.

        Args:
            dir_name: Name of the directory

        Returns:
            True if directory should be excluded
        """
        if dir_name.startswith("."):
            return True
        if dir_name in EXCLUDED_DIRS:
            return True
        if dir_name.endswith(".egg-info"):
            return True
        return False

    def _should_include_file(self, file_path: Path) -> bool:
        """Check if a file should be included in the view.

        Args:
            file_path: Path to the file

        Returns:
            True if file should be included
        """
        name = file_path.name
        suffix = file_path.suffix.lower()

        # Include source files
        if suffix in SOURCE_EXTENSIONS:
            return True

        # Include config files
        if suffix in CONFIG_EXTENSIONS:
            return True

        # Include specific config files by name
        if name in CONFIG_PATTERNS:
            return True

        # Include documentation
        if suffix in DOC_EXTENSIONS:
            return True

        # Include Dockerfile and similar
        if name.startswith("Dockerfile"):
            return True

        return False

    def _build_file_tree(self) -> str:
        """Build ASCII file tree representation of repository.

        Excludes common non-source directories like node_modules, .git, etc.

        Returns:
            ASCII tree string representation
        """
        lines = []
        lines.append(f"{self.repo_path.name}/")

        def walk_dir(dir_path: Path, prefix: str = "") -> None:
            """Recursively walk directory and build tree."""
            try:
                entries = sorted(dir_path.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
            except PermissionError:
                return

            # Filter entries
            filtered_entries = []
            for entry in entries:
                if entry.is_dir():
                    if not self._should_exclude_dir(entry.name):
                        filtered_entries.append(entry)
                else:
                    if self._should_include_file(entry):
                        filtered_entries.append(entry)

            for i, entry in enumerate(filtered_entries):
                is_last = i == len(filtered_entries) - 1
                connector = "└── " if is_last else "├── "

                if entry.is_dir():
                    lines.append(f"{prefix}{connector}{entry.name}/")
                    extension = "    " if is_last else "│   "
                    walk_dir(entry, prefix + extension)
                else:
                    lines.append(f"{prefix}{connector}{entry.name}")

        walk_dir(self.repo_path)
        return "\n".join(lines)

    def _get_file_priority(self, file_path: Path) -> int:
        """Calculate priority for a file (lower = higher priority).

        Priority levels:
        1. Entry points (main.py, index.ts, etc.)
        2. Config files (pyproject.toml, package.json, etc.)
        3. Core business logic (services/, core/, lib/)
        4. API routes (api/, routes/, controllers/)
        5. Other source files

        Args:
            file_path: Path to the file

        Returns:
            Priority score (1-5, lower is higher priority)
        """
        name = file_path.name
        relative_path = file_path.relative_to(self.repo_path)
        parts = relative_path.parts

        # Priority 1: Entry points
        if name in ENTRY_POINT_PATTERNS:
            return 1

        # Priority 2: Config files
        if name in CONFIG_PATTERNS:
            return 2
        if file_path.suffix.lower() in CONFIG_EXTENSIONS:
            # Config files in root get higher priority
            if len(parts) == 1:
                return 2
            return 3

        # Priority 3: Core logic directories
        for part in parts:
            if part.lower() in CORE_DIR_PATTERNS:
                return 3

        # Priority 4: API directories
        for part in parts:
            if part.lower() in API_DIR_PATTERNS:
                return 4

        # Priority 5: Other files
        return 5

    def _prioritize_files(self) -> list[FileInfo]:
        """Return files sorted by importance.

        Scans the repository and returns a list of FileInfo objects
        sorted by priority (entry points first, then configs, etc.)

        Returns:
            List of FileInfo objects sorted by priority
        """
        files: list[FileInfo] = []

        for root, dirs, filenames in os.walk(self.repo_path):
            # Filter out excluded directories in-place
            dirs[:] = [d for d in dirs if not self._should_exclude_dir(d)]

            root_path = Path(root)

            for filename in filenames:
                file_path = root_path / filename

                if not self._should_include_file(file_path):
                    continue

                try:
                    size = file_path.stat().st_size
                except OSError:
                    continue

                relative_path = str(file_path.relative_to(self.repo_path))
                priority = self._get_file_priority(file_path)

                files.append(FileInfo(
                    path=file_path,
                    relative_path=relative_path,
                    size=size,
                    priority=priority,
                ))

        # Sort by priority (ascending), then by path for consistency
        files.sort(key=lambda f: (f.priority, f.relative_path))

        return files

    def _read_file_content(self, file_path: Path, truncate: bool = False) -> tuple[str, bool]:
        """Read file content, optionally truncating large files.

        Args:
            file_path: Path to the file
            truncate: If True, truncate files larger than MAX_FILE_SIZE

        Returns:
            Tuple of (content, was_truncated)
        """
        try:
            with open(file_path, encoding="utf-8", errors="ignore") as f:
                content = f.read()

            if truncate and len(content) > MAX_FILE_SIZE:
                # Take beginning and end excerpts
                half_excerpt = EXCERPT_SIZE // 2
                beginning = content[:half_excerpt]
                ending = content[-half_excerpt:]

                # Find clean break points (newlines)
                begin_break = beginning.rfind("\n")
                if begin_break > half_excerpt // 2:
                    beginning = beginning[:begin_break]

                end_break = ending.find("\n")
                if end_break > 0 and end_break < half_excerpt // 2:
                    ending = ending[end_break + 1:]

                truncated_content = (
                    f"{beginning}\n\n"
                    f"... [TRUNCATED: {len(content) - EXCERPT_SIZE} characters omitted] ...\n\n"
                    f"{ending}"
                )
                return truncated_content, True

            return content, False

        except Exception as e:
            logger.warning(f"Failed to read {file_path}: {e}")
            return f"[Error reading file: {e}]", False

    def _generate_file_content_section(
        self,
        files: list[FileInfo],
        remaining_budget: int
    ) -> tuple[str, int, int]:
        """Generate the file contents section within token budget.

        Args:
            files: List of FileInfo objects sorted by priority
            remaining_budget: Remaining token budget

        Returns:
            Tuple of (content_section, files_included, files_truncated)
        """
        sections = []
        current_tokens = 0
        files_included = 0
        files_truncated = 0

        # Reserve a small buffer for token estimation variance (1% or minimum 10 tokens)
        safety_buffer = max(10, remaining_budget // 100)
        effective_budget = remaining_budget - safety_buffer

        for file_info in files:
            # Check if we have budget for at least a small file
            if current_tokens >= effective_budget:
                break

            # Determine if we should truncate based on file size
            should_truncate = file_info.size > MAX_FILE_SIZE

            content, was_truncated = self._read_file_content(
                file_info.path,
                truncate=should_truncate
            )

            # Build file section
            file_section = f"\n### {file_info.relative_path}\n\n```\n{content}\n```\n"
            section_tokens = self._estimate_tokens(file_section)

            # Check if adding this file would exceed budget
            if current_tokens + section_tokens > effective_budget:
                # Try with truncation if not already truncated
                if not was_truncated and file_info.size > EXCERPT_SIZE:
                    content, was_truncated = self._read_file_content(
                        file_info.path,
                        truncate=True
                    )
                    file_section = f"\n### {file_info.relative_path}\n\n```\n{content}\n```\n"
                    section_tokens = self._estimate_tokens(file_section)

                    if current_tokens + section_tokens > effective_budget:
                        # Still too large, skip this file
                        continue
                else:
                    # Skip this file
                    continue

            sections.append(file_section)
            current_tokens += section_tokens
            files_included += 1

            if was_truncated:
                files_truncated += 1

        return "".join(sections), files_included, files_truncated

    def generate(self) -> RepoViewResult:
        """Generate markdown view within token budget.

        Creates a markdown document containing:
        1. Repository file tree
        2. Prioritized file contents (entry points, configs, core logic, etc.)

        Returns:
            RepoViewResult with content and metadata
        """
        # Build file tree
        file_tree = self._build_file_tree()

        # Get prioritized files
        files = self._prioritize_files()
        total_files = len(files)

        # Build header section
        header = f"""# Repository Analysis View

## File Structure

```
{file_tree}
```

## File Contents

The following files are included in priority order:
1. Entry points (main.py, index.ts, etc.)
2. Configuration files (pyproject.toml, package.json, etc.)
3. Core business logic (services/, core/, lib/)
4. API routes (api/, routes/, controllers/)
5. Other source files

"""

        header_tokens = self._estimate_tokens(header)
        remaining_budget = self.token_budget - header_tokens

        # Generate file content section
        content_section, files_included, files_truncated = self._generate_file_content_section(
            files,
            remaining_budget
        )

        # Combine sections
        full_content = header + content_section
        total_tokens = self._estimate_tokens(full_content)

        logger.info(
            f"Generated repo view: {total_tokens} tokens, "
            f"{files_included}/{total_files} files included, "
            f"{files_truncated} truncated"
        )

        return RepoViewResult(
            content=full_content,
            token_estimate=total_tokens,
            files_included=files_included,
            files_truncated=files_truncated,
            total_files=total_files,
        )


# Convenience function
def generate_repo_view(repo_path: Path, token_budget: int = DEFAULT_TOKEN_BUDGET) -> RepoViewResult:
    """Generate an LLM-friendly view of a repository.

    Args:
        repo_path: Path to the repository root
        token_budget: Maximum tokens to include

    Returns:
        RepoViewResult with content and metadata
    """
    generator = RepoViewGenerator(repo_path, token_budget)
    return generator.generate()
