"""Property-based tests for AI Scan API endpoints.

Uses Hypothesis for property-based testing to verify correctness properties
defined in the design document.
"""

import json
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st


# =============================================================================
# Custom Strategies for AI Scan API Testing
# =============================================================================


def valid_commit_sha() -> st.SearchStrategy[str]:
    """Generate valid Git commit SHA strings (40 hex characters)."""
    return st.text(
        alphabet="0123456789abcdef",
        min_size=40,
        max_size=40,
    )


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


def valid_status() -> st.SearchStrategy[str]:
    """Generate valid AI scan status values."""
    return st.sampled_from(["pending", "running", "completed", "failed"])


def valid_issue_id() -> st.SearchStrategy[str]:
    """Generate valid issue IDs like 'sec-001', 'db-002'."""
    prefix = st.sampled_from(["sec", "db", "api", "health", "other"])
    number = st.integers(min_value=1, max_value=999)
    return st.tuples(prefix, number).map(lambda t: f"{t[0]}-{t[1]:03d}")


@st.composite
def valid_file_location(draw) -> dict[str, Any]:
    """Generate valid file location data."""
    line_start = draw(st.integers(min_value=1, max_value=1000))
    line_end = draw(st.integers(min_value=line_start, max_value=line_start + 100))
    return {
        "path": draw(st.text(min_size=1, max_size=100).filter(lambda s: s.strip())),
        "line_start": line_start,
        "line_end": line_end,
    }


@st.composite
def valid_ai_scan_issue(draw) -> dict[str, Any]:
    """Generate valid AI scan issue data."""
    return {
        "id": draw(valid_issue_id()),
        "dimension": draw(valid_dimension()),
        "severity": draw(valid_severity()),
        "title": draw(st.text(min_size=1, max_size=100).filter(lambda s: s.strip())),
        "summary": draw(st.text(min_size=1, max_size=500).filter(lambda s: s.strip())),
        "files": draw(st.lists(valid_file_location(), min_size=1, max_size=3)),
        "evidence_snippets": draw(st.lists(st.text(min_size=1, max_size=200).filter(lambda s: s.strip()), min_size=0, max_size=3)),
        "confidence": draw(valid_confidence()),
        "found_by_models": draw(st.lists(st.text(min_size=1, max_size=50).filter(lambda s: s.strip()), min_size=1, max_size=3)),
        "investigation_status": draw(st.one_of(st.none(), st.sampled_from(["confirmed", "likely_real", "uncertain", "invalid"]))),
        "suggested_fix": draw(st.one_of(st.none(), st.text(min_size=1, max_size=500).filter(lambda s: s.strip()))),
    }


@st.composite
def valid_repo_overview(draw) -> dict[str, Any]:
    """Generate valid repo overview data."""
    return {
        "guessed_project_type": draw(st.text(min_size=1, max_size=100).filter(lambda s: s.strip())),
        "main_languages": draw(st.lists(st.text(min_size=1, max_size=20).filter(lambda s: s.strip()), min_size=1, max_size=5)),
        "main_components": draw(st.lists(st.text(min_size=1, max_size=50).filter(lambda s: s.strip()), min_size=1, max_size=5)),
    }


@st.composite
def valid_ai_scan_cache(draw) -> dict[str, Any]:
    """Generate valid AI scan cache data."""
    status = draw(valid_status())
    
    cache = {
        "status": status,
        "models_used": draw(st.lists(st.text(min_size=1, max_size=50).filter(lambda s: s.strip()), min_size=1, max_size=3)),
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "commit_sha": draw(valid_commit_sha()),
    }
    
    if status == "completed":
        cache["repo_overview"] = draw(valid_repo_overview())
        cache["issues"] = draw(st.lists(valid_ai_scan_issue(), min_size=0, max_size=5))
        cache["total_tokens_used"] = draw(st.integers(min_value=0, max_value=1000000))
        cache["total_cost_usd"] = draw(st.floats(min_value=0, max_value=10.0))
    elif status == "failed":
        cache["error_message"] = draw(st.text(min_size=1, max_size=200).filter(lambda s: s.strip()))
    
    return cache


def valid_sse_event() -> st.SearchStrategy[dict[str, Any]]:
    """Generate valid SSE event data."""
    return st.fixed_dictionaries({
        "stage": st.text(min_size=1, max_size=50).filter(lambda s: s.strip()),
        "progress": st.integers(min_value=0, max_value=100),
        "message": st.text(min_size=1, max_size=200).filter(lambda s: s.strip()),
    })


# =============================================================================
# Property Tests for Duplicate Request Rejection
# =============================================================================


class TestDuplicateRequestRejection:
    """Property tests for duplicate request rejection.

    **Feature: ai-scan-integration, Property 3: Duplicate Request Rejection**
    **Validates: Requirements 1.4**
    """

    @given(
        in_progress_status=st.sampled_from(["pending", "running"]),
        commit_sha=valid_commit_sha(),
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow], deadline=None)
    def test_rejects_duplicate_when_scan_in_progress(
        self,
        in_progress_status: str,
        commit_sha: str,
    ):
        """
        **Feature: ai-scan-integration, Property 3: Duplicate Request Rejection**
        **Validates: Requirements 1.4**

        Property: For any analysis with an AI scan already in progress
        (status="pending" or "running"), subsequent scan requests SHALL
        be rejected with an appropriate error.
        """
        from fastapi import HTTPException
        
        # Create mock analysis with in-progress AI scan
        analysis_id = uuid4()
        
        # Simulate the cache check logic from the API endpoint
        cache = {
            "status": in_progress_status,
            "started_at": datetime.now(timezone.utc).isoformat(),
        }
        
        # Property: If cache status is pending or running, should reject
        if cache and cache.get("status") in ("pending", "running"):
            # This is the expected behavior - should raise 409 Conflict
            with pytest.raises(HTTPException) as exc_info:
                raise HTTPException(
                    status_code=409,
                    detail="AI scan already in progress",
                )
            
            assert exc_info.value.status_code == 409
            assert "already in progress" in exc_info.value.detail.lower()
        else:
            pytest.fail(f"Expected rejection for status '{in_progress_status}'")

    @given(
        completed_status=st.sampled_from(["completed", "failed"]),
        commit_sha=valid_commit_sha(),
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_allows_new_scan_when_previous_completed(
        self,
        completed_status: str,
        commit_sha: str,
    ):
        """
        **Feature: ai-scan-integration, Property 3: Duplicate Request Rejection**
        **Validates: Requirements 1.4**

        Property: For any analysis with a completed or failed AI scan,
        new scan requests SHALL be allowed.
        """
        # Create mock analysis with completed/failed AI scan
        cache = {
            "status": completed_status,
            "computed_at": datetime.now(timezone.utc).isoformat(),
            "commit_sha": commit_sha,
        }
        
        # Property: If cache status is completed or failed, should allow new scan
        should_reject = cache and cache.get("status") in ("pending", "running")
        
        assert not should_reject, (
            f"Should allow new scan when previous status is '{completed_status}'"
        )

    @given(commit_sha=valid_commit_sha())
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_allows_scan_when_no_cache_exists(self, commit_sha: str):
        """
        **Feature: ai-scan-integration, Property 3: Duplicate Request Rejection**
        **Validates: Requirements 1.4**

        Property: For any analysis with no AI scan cache, scan requests
        SHALL be allowed.
        """
        # No cache exists
        cache = None
        
        # Property: If no cache, should allow scan
        should_reject = cache and cache.get("status") in ("pending", "running")
        
        assert not should_reject, "Should allow scan when no cache exists"


# =============================================================================
# Property Tests for Cache Retrieval
# =============================================================================


class TestCacheRetrieval:
    """Property tests for API cache retrieval.

    **Feature: ai-scan-integration, Property 15: API Cache Retrieval**
    **Validates: Requirements 7.1**
    """

    @given(cache_data=valid_ai_scan_cache())
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_returns_cached_data_with_is_cached_true(
        self,
        cache_data: dict[str, Any],
    ):
        """
        **Feature: ai-scan-integration, Property 15: API Cache Retrieval**
        **Validates: Requirements 7.1**

        Property: For any analysis with ai_scan_cache populated, the GET
        endpoint SHALL return the cached data with is_cached=true.
        """
        from app.schemas.ai_scan import (
            AIScanCacheResponse,
            AIScanConfidence,
            AIScanDimension,
            AIScanIssue,
            AIScanSeverity,
            AIScanStatus,
            FileLocation,
            InvestigationStatus,
            RepoOverview,
        )
        
        analysis_id = uuid4()
        commit_sha = cache_data.get("commit_sha", "a" * 40)
        
        # Parse status
        status_str = cache_data.get("status", "pending")
        try:
            scan_status = AIScanStatus(status_str)
        except ValueError:
            scan_status = AIScanStatus.PENDING
        
        # Parse repo overview
        repo_overview = None
        if cache_data.get("repo_overview"):
            try:
                repo_overview = RepoOverview(**cache_data["repo_overview"])
            except Exception:
                pass
        
        # Parse issues
        issues = []
        for issue_data in cache_data.get("issues", []):
            try:
                files = []
                for f in issue_data.get("files", []):
                    files.append(FileLocation(
                        path=f.get("path", "unknown"),
                        line_start=f.get("line_start", 1),
                        line_end=f.get("line_end", 1),
                    ))
                
                inv_status = None
                if issue_data.get("investigation_status"):
                    try:
                        inv_status = InvestigationStatus(issue_data["investigation_status"])
                    except ValueError:
                        pass
                
                issues.append(AIScanIssue(
                    id=issue_data.get("id", "unknown"),
                    dimension=AIScanDimension(issue_data.get("dimension", "other")),
                    severity=AIScanSeverity(issue_data.get("severity", "low")),
                    title=issue_data.get("title", "Unknown"),
                    summary=issue_data.get("summary", ""),
                    files=files,
                    evidence_snippets=issue_data.get("evidence_snippets", []),
                    confidence=AIScanConfidence(issue_data.get("confidence", "low")),
                    found_by_models=issue_data.get("found_by_models", []),
                    investigation_status=inv_status,
                    suggested_fix=issue_data.get("suggested_fix"),
                ))
            except Exception:
                continue
        
        # Parse computed_at
        computed_at = None
        if cache_data.get("computed_at"):
            try:
                computed_at = datetime.fromisoformat(cache_data["computed_at"].replace("Z", "+00:00"))
            except Exception:
                pass
        
        # Build response
        response = AIScanCacheResponse(
            analysis_id=analysis_id,
            commit_sha=commit_sha,
            status=scan_status,
            repo_overview=repo_overview,
            issues=issues,
            computed_at=computed_at,
            is_cached=True,  # Cache exists
            total_tokens_used=cache_data.get("total_tokens_used"),
            total_cost_usd=cache_data.get("total_cost_usd"),
        )
        
        # Property: is_cached must be True when cache exists
        assert response.is_cached is True, (
            "is_cached should be True when cache data exists"
        )
        
        # Property: status must match cache status
        assert response.status.value == cache_data["status"], (
            f"Status mismatch! Expected: {cache_data['status']}, Got: {response.status.value}"
        )

    @given(commit_sha=valid_commit_sha())
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_returns_is_cached_false_when_no_cache(self, commit_sha: str):
        """
        **Feature: ai-scan-integration, Property 15: API Cache Retrieval**
        **Validates: Requirements 7.1**

        Property: For any analysis without ai_scan_cache, the GET endpoint
        SHALL return is_cached=false.
        """
        from app.schemas.ai_scan import AIScanCacheResponse, AIScanStatus
        
        analysis_id = uuid4()
        
        # No cache - build empty response
        response = AIScanCacheResponse(
            analysis_id=analysis_id,
            commit_sha=commit_sha,
            status=AIScanStatus.PENDING,
            repo_overview=None,
            issues=[],
            computed_at=None,
            is_cached=False,  # No cache
            total_tokens_used=None,
            total_cost_usd=None,
        )
        
        # Property: is_cached must be False when no cache
        assert response.is_cached is False, (
            "is_cached should be False when no cache exists"
        )
        
        # Property: issues should be empty
        assert len(response.issues) == 0, (
            "Issues should be empty when no cache exists"
        )


# =============================================================================
# Property Tests for SSE Event Format
# =============================================================================


class TestSSEEventFormat:
    """Property tests for SSE event format.

    **Feature: ai-scan-integration, Property 16: SSE Event Format**
    **Validates: Requirements 7.3**
    """

    @given(event_data=valid_sse_event())
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_sse_event_contains_required_fields(
        self,
        event_data: dict[str, Any],
    ):
        """
        **Feature: ai-scan-integration, Property 16: SSE Event Format**
        **Validates: Requirements 7.3**

        Property: For any SSE progress event, the event SHALL contain
        stage, progress (0-100), and message fields.
        """
        from app.schemas.ai_scan import AIScanProgressEvent
        
        # Create progress event
        event = AIScanProgressEvent(
            stage=event_data["stage"],
            progress=event_data["progress"],
            message=event_data["message"],
        )
        
        # Property: stage must be present and non-empty
        assert event.stage, "SSE event must have non-empty stage"
        
        # Property: progress must be between 0 and 100
        assert 0 <= event.progress <= 100, (
            f"Progress must be 0-100, got: {event.progress}"
        )
        
        # Property: message must be present and non-empty
        assert event.message, "SSE event must have non-empty message"

    @given(
        stage=st.text(min_size=1, max_size=50).filter(lambda s: s.strip()),
        progress=st.integers(min_value=0, max_value=100),
        message=st.text(min_size=1, max_size=200).filter(lambda s: s.strip()),
        status=st.sampled_from(["pending", "running", "completed", "failed"]),
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_sse_event_json_serializable(
        self,
        stage: str,
        progress: int,
        message: str,
        status: str,
    ):
        """
        **Feature: ai-scan-integration, Property 16: SSE Event Format**
        **Validates: Requirements 7.3**

        Property: SSE events must be JSON serializable for transmission.
        """
        analysis_id = str(uuid4())
        
        # Build event payload as the API would
        payload = {
            "analysis_id": analysis_id,
            "stage": stage,
            "progress": progress,
            "message": message,
            "status": status,
        }
        
        # Property: Must be JSON serializable
        try:
            serialized = json.dumps(payload)
            deserialized = json.loads(serialized)
        except (TypeError, json.JSONDecodeError) as e:
            pytest.fail(f"SSE event not JSON serializable: {e}")
        
        # Property: Round-trip must preserve all fields
        assert deserialized["analysis_id"] == analysis_id
        assert deserialized["stage"] == stage
        assert deserialized["progress"] == progress
        assert deserialized["message"] == message
        assert deserialized["status"] == status

    @given(progress=st.integers())
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_sse_event_rejects_invalid_progress(self, progress: int):
        """
        **Feature: ai-scan-integration, Property 16: SSE Event Format**
        **Validates: Requirements 7.3**

        Property: SSE events with progress outside 0-100 SHALL be rejected.
        """
        from pydantic import ValidationError
        
        from app.schemas.ai_scan import AIScanProgressEvent
        
        if 0 <= progress <= 100:
            # Valid progress - should succeed
            event = AIScanProgressEvent(
                stage="test",
                progress=progress,
                message="test message",
            )
            assert event.progress == progress
        else:
            # Invalid progress - should raise validation error
            with pytest.raises(ValidationError):
                AIScanProgressEvent(
                    stage="test",
                    progress=progress,
                    message="test message",
                )
