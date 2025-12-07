"""Property-based tests for RepoViewGenerator.

Uses Hypothesis for property-based testing to verify correctness properties
defined in the design document.
"""

import tempfile
from pathlib import Path
from typing import Any

from hypothesis import assume, given, settings
from hypothesis import strategies as st

from app.services.repo_view_generator import (
    CONFIG_PATTERNS,
    ENTRY_POINT_PATTERNS,
    EXCERPT_SIZE,
    MAX_FILE_SIZE,
    RepoViewGenerator,
)

# =============================================================================
# Custom Strategies for Repository Generation
# =============================================================================


def valid_filename() -> st.SearchStrategy[str]:
    """Generate valid filenames."""
    return st.text(
        alphabet=st.characters(
            whitelist_categories=("Lu", "Ll", "Nd"),
            whitelist_characters="_-",
        ),
        min_size=1,
        max_size=20,
    ).filter(lambda s: s.strip() and not s.startswith("-"))


def source_extension() -> st.SearchStrategy[str]:
    """Generate source file extensions."""
    return st.sampled_from([".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".rs", ".java"])


def config_extension() -> st.SearchStrategy[str]:
    """Generate config file extensions."""
    return st.sampled_from([".json", ".yaml", ".yml", ".toml"])


@st.composite
def source_file(draw) -> tuple[str, str]:
    """Generate a source file name and content."""
    name = draw(valid_filename())
    ext = draw(source_extension())
    content_lines = draw(st.integers(min_value=1, max_value=100))
    content = "\n".join([f"# Line {i}" for i in range(content_lines)])
    return f"{name}{ext}", content


@st.composite
def entry_point_file(draw) -> tuple[str, str]:
    """Generate an entry point file."""
    name = draw(st.sampled_from(list(ENTRY_POINT_PATTERNS)))
    content_lines = draw(st.integers(min_value=5, max_value=50))
    content = "\n".join([f"# Entry point line {i}" for i in range(content_lines)])
    return name, content


@st.composite
def config_file(draw) -> tuple[str, str]:
    """Generate a config file."""
    name = draw(st.sampled_from(list(CONFIG_PATTERNS)))
    content = draw(st.text(min_size=10, max_size=500))
    return name, content


@st.composite
def large_file(draw) -> tuple[str, str]:
    """Generate a file larger than MAX_FILE_SIZE."""
    name = draw(valid_filename())
    ext = draw(source_extension())
    # Generate content larger than MAX_FILE_SIZE
    content_size = draw(st.integers(min_value=MAX_FILE_SIZE + 1000, max_value=MAX_FILE_SIZE + 10000))
    content = "x" * content_size
    return f"{name}{ext}", content


@st.composite
def repo_structure(draw) -> dict[str, Any]:
    """Generate a repository structure with files.

    Returns a dict with:
    - files: list of (relative_path, content) tuples
    - has_entry_point: bool
    - has_config: bool
    """
    files = []
    has_entry_point = draw(st.booleans())
    has_config = draw(st.booleans())

    # Add entry point if requested
    if has_entry_point:
        name, content = draw(entry_point_file())
        files.append((name, content))

    # Add config if requested
    if has_config:
        name, content = draw(config_file())
        files.append((name, content))

    # Add some regular source files
    num_source_files = draw(st.integers(min_value=1, max_value=10))
    for _ in range(num_source_files):
        name, content = draw(source_file())
        # Avoid duplicates
        if not any(f[0] == name for f in files):
            files.append((name, content))

    # Optionally add files in subdirectories
    if draw(st.booleans()):
        subdir = draw(st.sampled_from(["src", "lib", "core", "services", "api", "utils"]))
        for _ in range(draw(st.integers(min_value=1, max_value=5))):
            name, content = draw(source_file())
            path = f"{subdir}/{name}"
            if not any(f[0] == path for f in files):
                files.append((path, content))

    return {
        "files": files,
        "has_entry_point": has_entry_point,
        "has_config": has_config,
    }


def create_temp_repo(structure: dict[str, Any]) -> Path:
    """Create a temporary repository from a structure dict."""
    temp_dir = tempfile.mkdtemp(prefix="test_repo_")
    repo_path = Path(temp_dir)

    for rel_path, content in structure["files"]:
        file_path = repo_path / rel_path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content)

    return repo_path


def cleanup_temp_repo(repo_path: Path) -> None:
    """Clean up a temporary repository."""
    import shutil
    if repo_path.exists():
        shutil.rmtree(repo_path)


# =============================================================================
# Property Tests for Token Budget Constraint
# =============================================================================


class TestTokenBudgetConstraint:
    """Property tests for token budget constraint.

    **Feature: ai-scan-integration, Property 4: Repo View Token Budget**
    **Validates: Requirements 2.2**
    """

    @given(repo_structure(), st.integers(min_value=1000, max_value=100000))
    @settings(max_examples=100, deadline=None)
    def test_token_budget_respected(self, structure: dict[str, Any], token_budget: int):
        """
        **Feature: ai-scan-integration, Property 4: Repo View Token Budget**
        **Validates: Requirements 2.2**

        Property: For any generated repo view, the estimated token count
        SHALL NOT exceed the configured token budget.
        """
        # Skip if no files
        assume(len(structure["files"]) > 0)

        repo_path = create_temp_repo(structure)
        try:
            generator = RepoViewGenerator(repo_path, token_budget=token_budget)
            result = generator.generate()

            # Property: Token estimate must not exceed budget
            assert result.token_estimate <= token_budget, (
                f"Token estimate {result.token_estimate} exceeds budget {token_budget}"
            )
        finally:
            cleanup_temp_repo(repo_path)

    @given(repo_structure())
    @settings(max_examples=100)
    def test_token_estimate_accuracy(self, structure: dict[str, Any]):
        """
        **Feature: ai-scan-integration, Property 4: Repo View Token Budget**
        **Validates: Requirements 2.2**

        Property: The token estimate should be approximately len(content) / 4.
        """
        assume(len(structure["files"]) > 0)

        repo_path = create_temp_repo(structure)
        try:
            generator = RepoViewGenerator(repo_path)
            result = generator.generate()

            # Verify token estimate is approximately content length / 4
            expected_tokens = len(result.content) // 4
            assert result.token_estimate == expected_tokens, (
                f"Token estimate {result.token_estimate} != expected {expected_tokens}"
            )
        finally:
            cleanup_temp_repo(repo_path)


# =============================================================================
# Property Tests for File Prioritization
# =============================================================================


class TestFilePrioritization:
    """Property tests for file prioritization.

    **Feature: ai-scan-integration, Property 5: File Prioritization Order**
    **Validates: Requirements 2.3**
    """

    @given(repo_structure())
    @settings(max_examples=100)
    def test_entry_points_before_other_files(self, structure: dict[str, Any]):
        """
        **Feature: ai-scan-integration, Property 5: File Prioritization Order**
        **Validates: Requirements 2.3**

        Property: For any repo view, entry points and config files SHALL
        appear before other source files in the content section.
        """
        assume(len(structure["files"]) > 0)
        assume(structure["has_entry_point"] or structure["has_config"])

        repo_path = create_temp_repo(structure)
        try:
            generator = RepoViewGenerator(repo_path)
            files = generator._prioritize_files()

            # Find indices of entry points, configs, and other files
            entry_point_indices = []
            config_indices = []
            other_indices = []

            for i, file_info in enumerate(files):
                filename = Path(file_info.relative_path).name
                if filename in ENTRY_POINT_PATTERNS:
                    entry_point_indices.append(i)
                elif filename in CONFIG_PATTERNS:
                    config_indices.append(i)
                else:
                    other_indices.append(i)

            # Property: Entry points should come before other files
            if entry_point_indices and other_indices:
                max_entry_point_idx = max(entry_point_indices)
                min_other_idx = min(other_indices)
                assert max_entry_point_idx < min_other_idx, (
                    f"Entry point at index {max_entry_point_idx} comes after "
                    f"other file at index {min_other_idx}"
                )

            # Property: Config files should come before other files
            if config_indices and other_indices:
                max_config_idx = max(config_indices)
                min_other_idx = min(other_indices)
                assert max_config_idx < min_other_idx, (
                    f"Config file at index {max_config_idx} comes after "
                    f"other file at index {min_other_idx}"
                )
        finally:
            cleanup_temp_repo(repo_path)

    @given(repo_structure())
    @settings(max_examples=100)
    def test_priority_ordering_consistent(self, structure: dict[str, Any]):
        """
        **Feature: ai-scan-integration, Property 5: File Prioritization Order**
        **Validates: Requirements 2.3**

        Property: Files should be sorted by priority (ascending), meaning
        lower priority numbers come first.
        """
        assume(len(structure["files"]) > 0)

        repo_path = create_temp_repo(structure)
        try:
            generator = RepoViewGenerator(repo_path)
            files = generator._prioritize_files()

            # Property: Files should be sorted by priority
            priorities = [f.priority for f in files]
            assert priorities == sorted(priorities), (
                f"Files not sorted by priority: {priorities}"
            )
        finally:
            cleanup_temp_repo(repo_path)


# =============================================================================
# Property Tests for Large File Truncation
# =============================================================================


class TestLargeFileTruncation:
    """Property tests for large file truncation.

    **Feature: ai-scan-integration, Property 6: Large File Truncation**
    **Validates: Requirements 2.4**
    """

    @given(large_file())
    @settings(max_examples=50)
    def test_large_files_truncated(self, file_data: tuple[str, str]):
        """
        **Feature: ai-scan-integration, Property 6: Large File Truncation**
        **Validates: Requirements 2.4**

        Property: For any file exceeding the size threshold, the repo view
        SHALL include only excerpts (partial content) rather than full content.
        """
        filename, content = file_data

        # Create temp repo with just this large file
        temp_dir = tempfile.mkdtemp(prefix="test_repo_")
        repo_path = Path(temp_dir)
        try:
            file_path = repo_path / filename
            file_path.write_text(content)

            generator = RepoViewGenerator(repo_path)
            result = generator.generate()

            # Property: Large file should be truncated
            assert result.files_truncated >= 1, (
                f"Large file was not truncated. "
                f"Original size: {len(content)}, MAX_FILE_SIZE: {MAX_FILE_SIZE}"
            )

            # Property: Truncation marker should be present
            assert "[TRUNCATED:" in result.content, (
                "Truncation marker not found in output"
            )
        finally:
            cleanup_temp_repo(repo_path)

    @given(large_file())
    @settings(max_examples=50)
    def test_truncated_content_within_limits(self, file_data: tuple[str, str]):
        """
        **Feature: ai-scan-integration, Property 6: Large File Truncation**
        **Validates: Requirements 2.4**

        Property: Truncated file content should be approximately EXCERPT_SIZE
        characters (plus truncation marker).
        """
        filename, content = file_data

        temp_dir = tempfile.mkdtemp(prefix="test_repo_")
        repo_path = Path(temp_dir)
        try:
            file_path = repo_path / filename
            file_path.write_text(content)

            generator = RepoViewGenerator(repo_path)

            # Read with truncation
            truncated_content, was_truncated = generator._read_file_content(
                file_path, truncate=True
            )

            # Property: Content should be truncated
            assert was_truncated, "Large file should be marked as truncated"

            # Property: Truncated content should be much smaller than original
            # Allow some overhead for the truncation marker
            max_expected_size = EXCERPT_SIZE + 200  # 200 chars for marker
            assert len(truncated_content) < max_expected_size, (
                f"Truncated content ({len(truncated_content)} chars) exceeds "
                f"expected max ({max_expected_size} chars)"
            )
        finally:
            cleanup_temp_repo(repo_path)

    @given(source_file())
    @settings(max_examples=50)
    def test_small_files_not_truncated(self, file_data: tuple[str, str]):
        """
        **Feature: ai-scan-integration, Property 6: Large File Truncation**
        **Validates: Requirements 2.4**

        Property: Files smaller than MAX_FILE_SIZE should NOT be truncated.
        """
        filename, content = file_data
        assume(len(content) < MAX_FILE_SIZE)

        temp_dir = tempfile.mkdtemp(prefix="test_repo_")
        repo_path = Path(temp_dir)
        try:
            file_path = repo_path / filename
            file_path.write_text(content)

            generator = RepoViewGenerator(repo_path)

            # Read without forced truncation
            read_content, was_truncated = generator._read_file_content(
                file_path, truncate=True
            )

            # Property: Small file should not be truncated
            assert not was_truncated, (
                f"Small file ({len(content)} chars) was incorrectly truncated"
            )

            # Property: Content should be preserved exactly
            assert read_content == content, (
                "Small file content was modified"
            )
        finally:
            cleanup_temp_repo(repo_path)
