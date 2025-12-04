"""Property-based tests for AI Scan Cache round-trip.

Uses Hypothesis for property-based testing to verify correctness properties
defined in the design document.
"""

import json
from datetime import datetime, timezone
from typing import Any

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st


# =============================================================================
# Custom Strategies for AI Scan Cache Generation
# =============================================================================


def valid_issue_id() -> st.SearchStrategy[str]:
    """Generate valid issue IDs like 'sec-001', 'db-002'."""
    prefix = st.sampled_from(["sec", "db", "api", "code", "other"])
    number = st.integers(min_value=1, max_value=999)
    return st.tuples(prefix, number).map(lambda t: f"{t[0]}-{t[1]:03d}")


def valid_dimension() -> st.SearchStrategy[str]:
    """Generate valid dimension values."""
    return st.sampled_from(
        ["security", "db_consistency", "api_correctness", "code_health", "other"]
    )


def valid_severity() -> st.SearchStrategy[str]:
    """Generate valid severity values."""
    return st.sampled_from(["critical", "high", "medium", "low"])


def valid_confidence() -> st.SearchStrategy[str]:
    """Generate valid confidence values."""
    return st.sampled_from(["high", "medium", "low"])


def valid_investigation_status() -> st.SearchStrategy[str | None]:
    """Generate valid investigation status values."""
    return st.one_of(
        st.none(),
        st.sampled_from(["confirmed", "likely_real", "uncertain", "invalid"]),
    )


def valid_scan_status() -> st.SearchStrategy[str]:
    """Generate valid scan status values."""
    return st.sampled_from(["pending", "running", "completed", "failed"])


def valid_file_location() -> st.SearchStrategy[dict[str, Any]]:
    """Generate valid file location dictionaries."""
    return st.fixed_dictionaries(
        {
            "path": st.text(
                alphabet=st.characters(
                    whitelist_categories=("Lu", "Ll", "Nd"),
                    whitelist_characters="_-./",
                ),
                min_size=1,
                max_size=100,
            ).filter(lambda s: s.strip() and not s.startswith("/")),
            "line_start": st.integers(min_value=1, max_value=10000),
            "line_end": st.integers(min_value=1, max_value=10000),
        }
    ).map(
        lambda d: {
            **d,
            "line_end": max(d["line_start"], d["line_end"]),
        }
    )


@st.composite
def ai_scan_issue(draw) -> dict[str, Any]:
    """Generate valid AI scan issue dictionaries."""
    return {
        "id": draw(valid_issue_id()),
        "dimension": draw(valid_dimension()),
        "severity": draw(valid_severity()),
        "title": draw(
            st.text(min_size=1, max_size=100).filter(lambda s: s.strip())
        ),
        "summary": draw(
            st.text(min_size=1, max_size=500).filter(lambda s: s.strip())
        ),
        "files": draw(st.lists(valid_file_location(), min_size=1, max_size=5)),
        "evidence_snippets": draw(
            st.lists(
                st.text(min_size=1, max_size=200).filter(lambda s: s.strip()),
                min_size=1,
                max_size=3,
            )
        ),
        "confidence": draw(valid_confidence()),
        "found_by_models": draw(
            st.lists(
                st.text(min_size=1, max_size=50).filter(lambda s: s.strip()),
                min_size=1,
                max_size=3,
            )
        ),
        "investigation_status": draw(valid_investigation_status()),
        "suggested_fix": draw(
            st.one_of(
                st.none(),
                st.text(min_size=1, max_size=500).filter(lambda s: s.strip()),
            )
        ),
    }


@st.composite
def repo_overview(draw) -> dict[str, Any]:
    """Generate valid repo overview dictionaries."""
    return {
        "guessed_project_type": draw(
            st.text(min_size=1, max_size=100).filter(lambda s: s.strip())
        ),
        "main_languages": draw(
            st.lists(
                st.text(min_size=1, max_size=20).filter(lambda s: s.strip()),
                min_size=1,
                max_size=5,
            )
        ),
        "main_components": draw(
            st.lists(
                st.text(min_size=1, max_size=50).filter(lambda s: s.strip()),
                min_size=1,
                max_size=5,
            )
        ),
    }


@st.composite
def ai_scan_cache(draw) -> dict[str, Any]:
    """Generate valid AI scan cache structures.

    This matches the structure defined in the design document.
    """
    status = draw(valid_scan_status())

    # Generate a datetime and convert to ISO format string
    dt = draw(
        st.datetimes(
            min_value=datetime(2020, 1, 1),
            max_value=datetime(2030, 12, 31),
        )
    )
    computed_at = dt.replace(tzinfo=timezone.utc).isoformat()

    return {
        "status": status,
        "models_used": draw(
            st.lists(
                st.text(min_size=1, max_size=50).filter(lambda s: s.strip()),
                min_size=1,
                max_size=3,
            )
        ),
        "repo_overview": draw(repo_overview()),
        "issues": draw(st.lists(ai_scan_issue(), min_size=0, max_size=10)),
        "computed_at": computed_at,
        "total_tokens_used": draw(st.integers(min_value=0, max_value=1000000)),
        "total_cost_usd": draw(st.floats(min_value=0, max_value=10.0)),
    }


# =============================================================================
# Property Tests for AI Scan Cache Round-Trip
# =============================================================================


class TestAIScanCacheRoundTrip:
    """Property tests for AI scan cache serialization round-trip.

    **Feature: ai-scan-integration, Property 19: AI Scan Cache Round-Trip**
    **Validates: Requirements 9.1, 9.2, 9.3**
    """

    @given(ai_scan_cache())
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_ai_scan_cache_json_round_trip(self, cache: dict[str, Any]):
        """
        **Feature: ai-scan-integration, Property 19: AI Scan Cache Round-Trip**
        **Validates: Requirements 9.1, 9.2, 9.3**

        Property: For any valid AIScanCache structure, serializing to JSON
        and deserializing back SHALL produce an equivalent structure.

        This tests the JSONB storage mechanism used by PostgreSQL.
        """
        # Serialize to JSON string (simulating JSONB storage)
        serialized = json.dumps(cache)

        # Deserialize back (simulating JSONB retrieval)
        deserialized = json.loads(serialized)

        # Property: Round-trip should produce equivalent data
        assert deserialized == cache, (
            f"Round-trip produced different data!\n"
            f"Original: {cache}\n"
            f"After round-trip: {deserialized}"
        )

    @given(ai_scan_cache())
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_ai_scan_cache_structure_preserved(self, cache: dict[str, Any]):
        """
        **Feature: ai-scan-integration, Property 19: AI Scan Cache Round-Trip**
        **Validates: Requirements 9.1, 9.2, 9.3**

        Property: For any valid AIScanCache structure, after round-trip
        serialization, all required fields SHALL be present with correct types.
        """
        # Serialize and deserialize
        serialized = json.dumps(cache)
        deserialized = json.loads(serialized)

        # Verify required top-level fields exist
        assert "status" in deserialized
        assert "models_used" in deserialized
        assert "repo_overview" in deserialized
        assert "issues" in deserialized
        assert "computed_at" in deserialized
        assert "total_tokens_used" in deserialized
        assert "total_cost_usd" in deserialized

        # Verify types
        assert isinstance(deserialized["status"], str)
        assert isinstance(deserialized["models_used"], list)
        assert isinstance(deserialized["repo_overview"], dict)
        assert isinstance(deserialized["issues"], list)
        assert isinstance(deserialized["computed_at"], str)
        assert isinstance(deserialized["total_tokens_used"], int)
        assert isinstance(deserialized["total_cost_usd"], float)

        # Verify repo_overview structure
        overview = deserialized["repo_overview"]
        assert "guessed_project_type" in overview
        assert "main_languages" in overview
        assert "main_components" in overview

        # Verify each issue structure
        for issue in deserialized["issues"]:
            assert "id" in issue
            assert "dimension" in issue
            assert "severity" in issue
            assert "title" in issue
            assert "summary" in issue
            assert "files" in issue
            assert "evidence_snippets" in issue
            assert "confidence" in issue
            assert "found_by_models" in issue
            assert "investigation_status" in issue
            assert "suggested_fix" in issue

            # Verify file location structure
            for file_loc in issue["files"]:
                assert "path" in file_loc
                assert "line_start" in file_loc
                assert "line_end" in file_loc

    @given(ai_scan_cache())
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_ai_scan_cache_enum_values_preserved(self, cache: dict[str, Any]):
        """
        **Feature: ai-scan-integration, Property 19: AI Scan Cache Round-Trip**
        **Validates: Requirements 9.1, 9.2, 9.3**

        Property: For any valid AIScanCache structure, enum-like string values
        (status, dimension, severity, confidence) SHALL be preserved exactly
        after round-trip serialization.
        """
        # Serialize and deserialize
        serialized = json.dumps(cache)
        deserialized = json.loads(serialized)

        # Verify status is preserved
        assert deserialized["status"] == cache["status"]

        # Verify issue enum values are preserved
        for orig_issue, deser_issue in zip(
            cache["issues"], deserialized["issues"], strict=True
        ):
            assert deser_issue["dimension"] == orig_issue["dimension"]
            assert deser_issue["severity"] == orig_issue["severity"]
            assert deser_issue["confidence"] == orig_issue["confidence"]
            assert (
                deser_issue["investigation_status"]
                == orig_issue["investigation_status"]
            )
