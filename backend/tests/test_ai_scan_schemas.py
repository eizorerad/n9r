"""Property-based tests for AI Scan schema validation.

Uses Hypothesis for property-based testing to verify that Pydantic schemas
correctly validate AI scan data structures.

**Feature: ai-scan-integration, Property: Schema Validation**
**Validates: Requirements 9.2**
"""

from typing import Any

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st
from pydantic import ValidationError

from app.schemas.ai_scan import (
    AIScanConfidence,
    AIScanDimension,
    AIScanIssue,
    AIScanRequest,
    AIScanSeverity,
    AIScanStatus,
    FileLocation,
    InvestigationStatus,
    RepoOverview,
)

# =============================================================================
# Custom Strategies for Valid Data Generation
# =============================================================================


def valid_dimension() -> st.SearchStrategy[str]:
    """Generate valid dimension values."""
    return st.sampled_from([d.value for d in AIScanDimension])


def valid_severity() -> st.SearchStrategy[str]:
    """Generate valid severity values."""
    return st.sampled_from([s.value for s in AIScanSeverity])


def valid_confidence() -> st.SearchStrategy[str]:
    """Generate valid confidence values."""
    return st.sampled_from([c.value for c in AIScanConfidence])


def valid_status() -> st.SearchStrategy[str]:
    """Generate valid scan status values."""
    return st.sampled_from([s.value for s in AIScanStatus])


def valid_investigation_status() -> st.SearchStrategy[str | None]:
    """Generate valid investigation status values."""
    return st.one_of(
        st.none(),
        st.sampled_from([s.value for s in InvestigationStatus]),
    )


def valid_issue_id() -> st.SearchStrategy[str]:
    """Generate valid issue IDs like 'sec-001', 'db-002'."""
    prefix = st.sampled_from(["sec", "db", "api", "code", "other"])
    number = st.integers(min_value=1, max_value=999)
    return st.tuples(prefix, number).map(lambda t: f"{t[0]}-{t[1]:03d}")


def non_empty_text(max_size: int = 100) -> st.SearchStrategy[str]:
    """Generate non-empty text strings."""
    return st.text(min_size=1, max_size=max_size).filter(lambda s: s.strip())


@st.composite
def valid_file_location(draw) -> dict[str, Any]:
    """Generate valid file location data."""
    line_start = draw(st.integers(min_value=1, max_value=10000))
    line_end = draw(st.integers(min_value=line_start, max_value=10000))
    return {
        "path": draw(non_empty_text(100)),
        "line_start": line_start,
        "line_end": line_end,
    }


@st.composite
def valid_ai_scan_issue_data(draw) -> dict[str, Any]:
    """Generate valid AI scan issue data."""
    return {
        "id": draw(valid_issue_id()),
        "dimension": draw(valid_dimension()),
        "severity": draw(valid_severity()),
        "title": draw(non_empty_text(200)),
        "summary": draw(non_empty_text(500)),
        "files": draw(st.lists(valid_file_location(), min_size=1, max_size=5)),
        "evidence_snippets": draw(st.lists(non_empty_text(200), min_size=0, max_size=3)),
        "confidence": draw(valid_confidence()),
        "found_by_models": draw(st.lists(non_empty_text(50), min_size=1, max_size=3)),
        "investigation_status": draw(valid_investigation_status()),
        "suggested_fix": draw(st.one_of(st.none(), non_empty_text(500))),
    }


@st.composite
def valid_repo_overview_data(draw) -> dict[str, Any]:
    """Generate valid repo overview data."""
    return {
        "guessed_project_type": draw(non_empty_text(100)),
        "main_languages": draw(st.lists(non_empty_text(20), min_size=0, max_size=5)),
        "main_components": draw(st.lists(non_empty_text(50), min_size=0, max_size=5)),
    }


@st.composite
def valid_ai_scan_request_data(draw) -> dict[str, Any]:
    """Generate valid AI scan request data."""
    return {
        "models": draw(st.lists(non_empty_text(50), min_size=1, max_size=3)),
        "investigate_severity": draw(
            st.lists(
                st.sampled_from([s.value for s in AIScanSeverity]),
                min_size=0,
                max_size=4,
            )
        ),
        "max_issues_to_investigate": draw(st.integers(min_value=0, max_value=50)),
    }


# =============================================================================
# Property Tests for Valid Structure Validation
# =============================================================================


class TestValidStructuresPassValidation:
    """Property tests verifying valid structures pass Pydantic validation.

    **Feature: ai-scan-integration, Property: Schema Validation**
    **Validates: Requirements 9.2**
    """

    @given(valid_file_location())
    @settings(max_examples=100)
    def test_valid_file_location_passes_validation(self, data: dict[str, Any]):
        """
        **Feature: ai-scan-integration, Property: Schema Validation**
        **Validates: Requirements 9.2**

        Property: For any valid file location data, Pydantic validation SHALL succeed.
        """
        location = FileLocation(**data)
        assert location.path == data["path"]
        assert location.line_start == data["line_start"]
        assert location.line_end == data["line_end"]

    @given(valid_ai_scan_issue_data())
    @settings(max_examples=100)
    def test_valid_ai_scan_issue_passes_validation(self, data: dict[str, Any]):
        """
        **Feature: ai-scan-integration, Property: Schema Validation**
        **Validates: Requirements 9.2**

        Property: For any valid AI scan issue data, Pydantic validation SHALL succeed.
        """
        issue = AIScanIssue(**data)
        assert issue.id == data["id"]
        assert issue.dimension.value == data["dimension"]
        assert issue.severity.value == data["severity"]
        assert issue.confidence.value == data["confidence"]
        assert len(issue.files) == len(data["files"])
        assert len(issue.found_by_models) == len(data["found_by_models"])

    @given(valid_repo_overview_data())
    @settings(max_examples=100)
    def test_valid_repo_overview_passes_validation(self, data: dict[str, Any]):
        """
        **Feature: ai-scan-integration, Property: Schema Validation**
        **Validates: Requirements 9.2**

        Property: For any valid repo overview data, Pydantic validation SHALL succeed.
        """
        overview = RepoOverview(**data)
        assert overview.guessed_project_type == data["guessed_project_type"]
        assert overview.main_languages == data["main_languages"]
        assert overview.main_components == data["main_components"]

    @given(valid_ai_scan_request_data())
    @settings(max_examples=100)
    def test_valid_ai_scan_request_passes_validation(self, data: dict[str, Any]):
        """
        **Feature: ai-scan-integration, Property: Schema Validation**
        **Validates: Requirements 9.2**

        Property: For any valid AI scan request data, Pydantic validation SHALL succeed.
        """
        request = AIScanRequest(**data)
        assert request.models == data["models"]
        assert request.max_issues_to_investigate == data["max_issues_to_investigate"]


# =============================================================================
# Property Tests for Invalid Structure Rejection
# =============================================================================


class TestInvalidStructuresAreRejected:
    """Property tests verifying invalid structures are rejected by Pydantic.

    **Feature: ai-scan-integration, Property: Schema Validation**
    **Validates: Requirements 9.2**
    """

    @given(st.text(min_size=1, max_size=50).filter(
        lambda s: s not in [d.value for d in AIScanDimension]
    ))
    @settings(max_examples=100)
    def test_invalid_dimension_rejected(self, invalid_dimension: str):
        """
        **Feature: ai-scan-integration, Property: Schema Validation**
        **Validates: Requirements 9.2**

        Property: For any string not in the valid dimension enum,
        AIScanIssue validation SHALL fail.
        """
        # Skip if the generated string happens to match a valid dimension
        assume(invalid_dimension not in [d.value for d in AIScanDimension])

        data = {
            "id": "sec-001",
            "dimension": invalid_dimension,
            "severity": "high",
            "title": "Test Issue",
            "summary": "Test summary",
            "files": [{"path": "test.py", "line_start": 1, "line_end": 10}],
            "confidence": "high",
            "found_by_models": ["model1"],
        }
        with pytest.raises(ValidationError):
            AIScanIssue(**data)

    @given(st.text(min_size=1, max_size=50).filter(
        lambda s: s not in [s.value for s in AIScanSeverity]
    ))
    @settings(max_examples=100)
    def test_invalid_severity_rejected(self, invalid_severity: str):
        """
        **Feature: ai-scan-integration, Property: Schema Validation**
        **Validates: Requirements 9.2**

        Property: For any string not in the valid severity enum,
        AIScanIssue validation SHALL fail.
        """
        assume(invalid_severity not in [s.value for s in AIScanSeverity])

        data = {
            "id": "sec-001",
            "dimension": "security",
            "severity": invalid_severity,
            "title": "Test Issue",
            "summary": "Test summary",
            "files": [{"path": "test.py", "line_start": 1, "line_end": 10}],
            "confidence": "high",
            "found_by_models": ["model1"],
        }
        with pytest.raises(ValidationError):
            AIScanIssue(**data)

    @given(st.text(min_size=1, max_size=50).filter(
        lambda s: s not in [c.value for c in AIScanConfidence]
    ))
    @settings(max_examples=100)
    def test_invalid_confidence_rejected(self, invalid_confidence: str):
        """
        **Feature: ai-scan-integration, Property: Schema Validation**
        **Validates: Requirements 9.2**

        Property: For any string not in the valid confidence enum,
        AIScanIssue validation SHALL fail.
        """
        assume(invalid_confidence not in [c.value for c in AIScanConfidence])

        data = {
            "id": "sec-001",
            "dimension": "security",
            "severity": "high",
            "title": "Test Issue",
            "summary": "Test summary",
            "files": [{"path": "test.py", "line_start": 1, "line_end": 10}],
            "confidence": invalid_confidence,
            "found_by_models": ["model1"],
        }
        with pytest.raises(ValidationError):
            AIScanIssue(**data)

    @given(st.integers(min_value=2, max_value=10000))
    @settings(max_examples=100)
    def test_line_end_less_than_line_start_rejected(self, line_start: int):
        """
        **Feature: ai-scan-integration, Property: Schema Validation**
        **Validates: Requirements 9.2**

        Property: For any file location where line_end < line_start,
        validation SHALL fail.
        """
        line_end = line_start - 1  # Always less than line_start

        with pytest.raises(ValidationError):
            FileLocation(path="test.py", line_start=line_start, line_end=line_end)

    @given(st.integers(max_value=0))
    @settings(max_examples=100)
    def test_non_positive_line_numbers_rejected(self, invalid_line: int):
        """
        **Feature: ai-scan-integration, Property: Schema Validation**
        **Validates: Requirements 9.2**

        Property: For any line number <= 0, validation SHALL fail.
        """
        with pytest.raises(ValidationError):
            FileLocation(path="test.py", line_start=invalid_line, line_end=10)

        with pytest.raises(ValidationError):
            FileLocation(path="test.py", line_start=1, line_end=invalid_line)

    def test_empty_models_list_rejected(self):
        """
        **Feature: ai-scan-integration, Property: Schema Validation**
        **Validates: Requirements 9.2**

        Property: An empty models list SHALL be rejected.
        """
        with pytest.raises(ValidationError):
            AIScanRequest(models=[])

    def test_empty_found_by_models_rejected(self):
        """
        **Feature: ai-scan-integration, Property: Schema Validation**
        **Validates: Requirements 9.2**

        Property: An empty found_by_models list SHALL be rejected.
        """
        data = {
            "id": "sec-001",
            "dimension": "security",
            "severity": "high",
            "title": "Test Issue",
            "summary": "Test summary",
            "files": [{"path": "test.py", "line_start": 1, "line_end": 10}],
            "confidence": "high",
            "found_by_models": [],  # Empty - should fail
        }
        with pytest.raises(ValidationError):
            AIScanIssue(**data)

    def test_empty_files_list_rejected(self):
        """
        **Feature: ai-scan-integration, Property: Schema Validation**
        **Validates: Requirements 9.2**

        Property: An empty files list SHALL be rejected.
        """
        data = {
            "id": "sec-001",
            "dimension": "security",
            "severity": "high",
            "title": "Test Issue",
            "summary": "Test summary",
            "files": [],  # Empty - should fail
            "confidence": "high",
            "found_by_models": ["model1"],
        }
        with pytest.raises(ValidationError):
            AIScanIssue(**data)

    @given(st.integers(min_value=51, max_value=1000))
    @settings(max_examples=100)
    def test_max_issues_to_investigate_exceeds_limit_rejected(self, value: int):
        """
        **Feature: ai-scan-integration, Property: Schema Validation**
        **Validates: Requirements 9.2**

        Property: max_issues_to_investigate > 50 SHALL be rejected.
        """
        with pytest.raises(ValidationError):
            AIScanRequest(
                models=["model1"],
                max_issues_to_investigate=value,
            )

    @given(st.integers(max_value=-1))
    @settings(max_examples=100)
    def test_negative_max_issues_to_investigate_rejected(self, value: int):
        """
        **Feature: ai-scan-integration, Property: Schema Validation**
        **Validates: Requirements 9.2**

        Property: Negative max_issues_to_investigate SHALL be rejected.
        """
        with pytest.raises(ValidationError):
            AIScanRequest(
                models=["model1"],
                max_issues_to_investigate=value,
            )
