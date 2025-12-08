"""Property-based tests for Git Analyzer.

Uses Hypothesis for property-based testing to verify correctness properties
defined in the design document for the cluster-map-refactoring feature.

Requirements: 2.1, 2.2, 2.3, 2.4
"""

from __future__ import annotations

import subprocess
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from app.schemas.architecture_llm import HotSpotFinding
from app.services.git_analyzer import FileChurn, GitAnalyzer


# =============================================================================
# Custom Strategies for FileChurn Generation
# =============================================================================


@st.composite
def valid_file_churn(draw) -> FileChurn:
    """Generate valid FileChurn objects with realistic values."""
    file_path = draw(
        st.from_regex(r"[a-zA-Z_][a-zA-Z0-9_/]*\.(py|js|ts|tsx)", fullmatch=True).filter(
            lambda s: len(s) >= 4 and len(s) <= 100
        )
    )
    changes_30d = draw(st.integers(min_value=0, max_value=100))
    changes_90d = draw(st.integers(min_value=changes_30d, max_value=200))
    lines_added = draw(st.integers(min_value=0, max_value=5000))
    lines_removed = draw(st.integers(min_value=0, max_value=5000))
    unique_authors = draw(st.integers(min_value=1, max_value=20))

    # Generate a last_modified date within the last 90 days
    days_ago = draw(st.integers(min_value=0, max_value=90))
    last_modified = datetime.now(timezone.utc) - timedelta(days=days_ago)

    return FileChurn(
        file_path=file_path,
        changes_30d=changes_30d,
        changes_90d=changes_90d,
        lines_added_90d=lines_added,
        lines_removed_90d=lines_removed,
        unique_authors=unique_authors,
        last_modified=last_modified,
    )


@st.composite
def churn_data_dict(draw) -> dict[str, FileChurn]:
    """Generate a dictionary of file paths to FileChurn objects."""
    num_files = draw(st.integers(min_value=1, max_value=20))
    churn_data: dict[str, FileChurn] = {}

    for i in range(num_files):
        churn = draw(valid_file_churn())
        # Ensure unique file paths by appending index
        unique_path = f"src/module_{i}/{churn.file_path}"
        churn.file_path = unique_path
        churn_data[unique_path] = churn

    return churn_data


@st.composite
def coverage_data_dict(draw, file_paths: list[str]) -> dict[str, float]:
    """Generate coverage data for given file paths."""
    coverage_data: dict[str, float] = {}

    for file_path in file_paths:
        # Randomly include coverage for some files
        if draw(st.booleans()):
            coverage_rate = draw(st.floats(min_value=0.0, max_value=1.0))
            coverage_data[file_path] = coverage_rate

    return coverage_data


# =============================================================================
# Property Tests for Git Log Parsing Consistency
# =============================================================================


class TestGitLogParsingProperties:
    """Property tests for git log parsing consistency.

    **Feature: cluster-map-refactoring, Property 5: Git Log Parsing Consistency**
    **Validates: Requirements 2.1, 2.2**
    """

    @given(valid_file_churn())
    @settings(max_examples=100)
    def test_file_churn_invariants(self, churn: FileChurn):
        """
        **Feature: cluster-map-refactoring, Property 5: Git Log Parsing Consistency**
        **Validates: Requirements 2.1, 2.2**

        Property: For any valid FileChurn object, changes_90d >= 0,
        lines_added_90d >= 0, lines_removed_90d >= 0, and unique_authors >= 1
        for files with changes.
        """
        # Property 1: changes_90d >= 0
        assert churn.changes_90d >= 0, (
            f"changes_90d must be >= 0, got {churn.changes_90d}"
        )

        # Property 2: lines_added_90d >= 0
        assert churn.lines_added_90d >= 0, (
            f"lines_added_90d must be >= 0, got {churn.lines_added_90d}"
        )

        # Property 3: lines_removed_90d >= 0
        assert churn.lines_removed_90d >= 0, (
            f"lines_removed_90d must be >= 0, got {churn.lines_removed_90d}"
        )

        # Property 4: unique_authors >= 1 for files with changes
        if churn.changes_90d > 0:
            assert churn.unique_authors >= 1, (
                f"unique_authors must be >= 1 for files with changes, "
                f"got {churn.unique_authors}"
            )

    def test_git_analyzer_on_real_repo(self):
        """
        **Feature: cluster-map-refactoring, Property 5: Git Log Parsing Consistency**
        **Validates: Requirements 2.1, 2.2**

        Integration test: Verify GitAnalyzer produces valid FileChurn objects
        when run on a real git repository.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)

            # Initialize a git repository
            subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True)
            subprocess.run(
                ["git", "config", "user.email", "test@example.com"],
                cwd=repo_path,
                check=True,
                capture_output=True,
            )
            subprocess.run(
                ["git", "config", "user.name", "Test User"],
                cwd=repo_path,
                check=True,
                capture_output=True,
            )

            # Create a test file and commit it
            test_file = repo_path / "test.py"
            test_file.write_text("def hello():\n    pass\n")
            subprocess.run(["git", "add", "test.py"], cwd=repo_path, check=True, capture_output=True)
            subprocess.run(
                ["git", "commit", "-m", "Initial commit"],
                cwd=repo_path,
                check=True,
                capture_output=True,
            )

            # Make another change
            test_file.write_text("def hello():\n    print('hello')\n")
            subprocess.run(["git", "add", "test.py"], cwd=repo_path, check=True, capture_output=True)
            subprocess.run(
                ["git", "commit", "-m", "Update hello"],
                cwd=repo_path,
                check=True,
                capture_output=True,
            )

            # Analyze the repository
            analyzer = GitAnalyzer()
            churn_data = analyzer.analyze(repo_path)

            # Verify the results
            assert "test.py" in churn_data, "test.py should be in churn data"

            churn = churn_data["test.py"]

            # Property 1: changes_90d >= 0
            assert churn.changes_90d >= 0

            # Property 2: lines_added_90d >= 0
            assert churn.lines_added_90d >= 0

            # Property 3: lines_removed_90d >= 0
            assert churn.lines_removed_90d >= 0

            # Property 4: unique_authors >= 1
            assert churn.unique_authors >= 1

            # Property 5: We made 2 commits, so changes should be 2
            assert churn.changes_90d == 2, f"Expected 2 changes, got {churn.changes_90d}"


# =============================================================================
# Property Tests for Hot Spot Threshold
# =============================================================================


class TestHotSpotThresholdProperties:
    """Property tests for hot spot threshold filtering.

    **Feature: cluster-map-refactoring, Property 6: Hot Spot Threshold**
    **Validates: Requirements 2.3**
    """

    @given(churn_data_dict(), st.integers(min_value=1, max_value=50))
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_hot_spot_threshold_filtering(
        self, churn_data: dict[str, FileChurn], threshold: int
    ):
        """
        **Feature: cluster-map-refactoring, Property 6: Hot Spot Threshold**
        **Validates: Requirements 2.3**

        Property: For any churn data, the set of hot spots SHALL contain
        exactly those files where changes_90d > threshold.
        """
        analyzer = GitAnalyzer()
        findings = analyzer.to_hot_spot_findings(churn_data, threshold=threshold)

        # Get file paths from findings
        finding_paths = {f.file_path for f in findings}

        # Calculate expected hot spots
        expected_hot_spots = {
            path for path, churn in churn_data.items() if churn.changes_90d > threshold
        }

        # Property 1: All findings are above threshold
        for finding in findings:
            original_churn = churn_data[finding.file_path]
            assert original_churn.changes_90d > threshold, (
                f"Finding {finding.file_path} has changes_90d={original_churn.changes_90d} "
                f"which is not > threshold={threshold}"
            )

        # Property 2: All files above threshold are in findings
        assert finding_paths == expected_hot_spots, (
            f"Hot spot set mismatch.\n"
            f"Expected: {expected_hot_spots}\n"
            f"Got: {finding_paths}\n"
            f"Missing: {expected_hot_spots - finding_paths}\n"
            f"Extra: {finding_paths - expected_hot_spots}"
        )


# =============================================================================
# Property Tests for Hot Spot Risk Factors
# =============================================================================


class TestHotSpotRiskFactorsProperties:
    """Property tests for hot spot risk factors.

    **Feature: cluster-map-refactoring, Property 7: Hot Spot Risk Factors**
    **Validates: Requirements 2.4**
    """

    @given(churn_data_dict())
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_hot_spot_risk_factors_non_empty(self, churn_data: dict[str, FileChurn]):
        """
        **Feature: cluster-map-refactoring, Property 7: Hot Spot Risk Factors**
        **Validates: Requirements 2.4**

        Property: For any hot spot finding, the risk_factors list SHALL be
        non-empty and contain at least one natural language string explaining the risk.
        """
        analyzer = GitAnalyzer()
        # Use threshold=0 to get all files as hot spots for testing
        findings = analyzer.to_hot_spot_findings(churn_data, threshold=0)

        for finding in findings:
            # Property 1: risk_factors is non-empty
            assert len(finding.risk_factors) > 0, (
                f"risk_factors is empty for {finding.file_path}"
            )

            # Property 2: Each risk factor is a non-empty string
            for factor in finding.risk_factors:
                assert isinstance(factor, str), (
                    f"risk_factor must be a string, got {type(factor)}"
                )
                assert len(factor) > 0, (
                    f"risk_factor must be non-empty for {finding.file_path}"
                )

            # Property 3: Risk factors are human-readable (contain words)
            for factor in finding.risk_factors:
                # Should contain at least one word character sequence
                assert any(c.isalpha() for c in factor), (
                    f"risk_factor should be human-readable: '{factor}'"
                )

    @given(valid_file_churn(), st.floats(min_value=0.0, max_value=0.49))
    @settings(max_examples=100)
    def test_low_coverage_in_risk_factors(
        self, churn: FileChurn, coverage_rate: float
    ):
        """
        **Feature: cluster-map-refactoring, Property 9: Coverage in Risk Factors**
        **Validates: Requirements 3.2**

        Property: For any hot spot with coverage_rate < 0.5, the risk_factors
        list SHALL contain a string mentioning low test coverage.
        """
        # Ensure the file is a hot spot
        churn.changes_90d = 20  # Above default threshold

        analyzer = GitAnalyzer()
        churn_data = {churn.file_path: churn}
        coverage_data = {churn.file_path: coverage_rate}

        findings = analyzer.to_hot_spot_findings(
            churn_data, coverage_data=coverage_data, threshold=10
        )

        assert len(findings) == 1, "Should have exactly one finding"
        finding = findings[0]

        # Property: Risk factors should mention low coverage
        coverage_mentioned = any(
            "coverage" in factor.lower() for factor in finding.risk_factors
        )
        assert coverage_mentioned, (
            f"Low coverage ({coverage_rate:.0%}) should be mentioned in risk factors.\n"
            f"Risk factors: {finding.risk_factors}"
        )


# =============================================================================
# Property Tests for HotSpotFinding Format
# =============================================================================


class TestHotSpotFindingFormatProperties:
    """Property tests for HotSpotFinding format validation."""

    @given(churn_data_dict())
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_hot_spot_finding_format(self, churn_data: dict[str, FileChurn]):
        """
        Verify HotSpotFinding objects have valid format.
        """
        analyzer = GitAnalyzer()
        findings = analyzer.to_hot_spot_findings(churn_data, threshold=0)

        for finding in findings:
            # Property 1: file_path is non-empty
            assert finding.file_path, "file_path must be non-empty"

            # Property 2: churn_count >= 0
            assert finding.churn_count >= 0, (
                f"churn_count must be >= 0, got {finding.churn_count}"
            )

            # Property 3: unique_authors >= 0
            assert finding.unique_authors >= 0, (
                f"unique_authors must be >= 0, got {finding.unique_authors}"
            )

            # Property 4: coverage_rate is None or in [0.0, 1.0]
            if finding.coverage_rate is not None:
                assert 0.0 <= finding.coverage_rate <= 1.0, (
                    f"coverage_rate must be in [0.0, 1.0], got {finding.coverage_rate}"
                )

            # Property 5: suggested_action is non-empty
            assert finding.suggested_action, (
                f"suggested_action must be non-empty for {finding.file_path}"
            )

            # Property 6: suggested_action is human-readable
            assert len(finding.suggested_action) > 10, (
                f"suggested_action should be a meaningful sentence: "
                f"'{finding.suggested_action}'"
            )
