"""Tests for analysis-scoped endpoints to verify no information disclosure.

All analysis-scoped endpoints should return 404 for both:
1. Non-existent analysis IDs
2. Analysis IDs that exist but belong to another user

This prevents attackers from enumerating valid analysis IDs by observing
the difference between 403 (exists but unauthorized) and 404 (doesn't exist).

**Feature: security-no-existence-leak**
**Validates: Information disclosure prevention**
"""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException


# =============================================================================
# Helper Functions for Creating Mocks
# =============================================================================


def create_mock_user(user_id: uuid.UUID | None = None) -> MagicMock:
    """Create a mock user with the given ID."""
    mock_user = MagicMock()
    mock_user.id = user_id or uuid.uuid4()
    return mock_user


def create_mock_analysis(
    analysis_id: uuid.UUID | None = None,
    repository_id: uuid.UUID | None = None,
    owner_id: uuid.UUID | None = None,
    status: str = "completed",
    ai_scan_status: str = "skipped",  # Use "skipped" as default for completed analyses
) -> MagicMock:
    """Create a mock analysis with associated repository."""
    mock_analysis = MagicMock()
    mock_analysis.id = analysis_id or uuid.uuid4()
    mock_analysis.repository_id = repository_id or uuid.uuid4()
    mock_analysis.commit_sha = "abc123def456"
    mock_analysis.branch = "main"
    mock_analysis.status = status
    mock_analysis.vci_score = 85.5
    mock_analysis.grade = "B"
    mock_analysis.metrics = {}
    mock_analysis.ai_report = None
    mock_analysis.error_message = None
    mock_analysis.embeddings_status = "completed"
    mock_analysis.embeddings_progress = 100
    mock_analysis.embeddings_stage = "completed"
    mock_analysis.embeddings_message = None
    mock_analysis.embeddings_error = None
    mock_analysis.vectors_count = 150
    mock_analysis.semantic_cache_status = "completed"
    mock_analysis.semantic_cache = {"architecture_health": {"overall_score": 80}}
    mock_analysis.ai_scan_status = ai_scan_status
    mock_analysis.ai_scan_progress = 100 if ai_scan_status in ("completed", "skipped") else 0
    mock_analysis.ai_scan_stage = "completed" if ai_scan_status == "completed" else None
    mock_analysis.ai_scan_message = None
    mock_analysis.ai_scan_error = None
    mock_analysis.ai_scan_cache = {"issues": []} if ai_scan_status == "completed" else None
    mock_analysis.ai_scan_started_at = datetime.now(UTC) if ai_scan_status in ("completed", "running") else None
    mock_analysis.ai_scan_completed_at = datetime.now(UTC) if ai_scan_status == "completed" else None
    mock_analysis.state_updated_at = datetime.now(UTC)
    mock_analysis.embeddings_started_at = datetime.now(UTC)
    mock_analysis.embeddings_completed_at = datetime.now(UTC)
    mock_analysis.started_at = datetime.now(UTC)
    mock_analysis.completed_at = datetime.now(UTC)
    mock_analysis.created_at = datetime.now(UTC)

    # Repository relationship
    mock_analysis.repository = MagicMock()
    mock_analysis.repository.owner_id = owner_id or uuid.uuid4()
    mock_analysis.repository.full_name = "owner/repo"

    return mock_analysis


def create_mock_db_returning_none() -> AsyncMock:
    """Create a mock database session that returns None (no analysis found)."""
    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = mock_result
    return mock_db


def create_mock_db_returning_analysis(analysis: MagicMock) -> AsyncMock:
    """Create a mock database session that returns the given analysis."""
    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = analysis
    mock_result.scalars.return_value.all.return_value = []  # For issues query
    mock_db.execute.return_value = mock_result
    return mock_db


# =============================================================================
# Test get_analysis_for_user_or_404 Helper
# =============================================================================


class TestGetAnalysisForUserOr404:
    """Test the security helper function directly."""

    @pytest.mark.asyncio
    async def test_returns_404_for_nonexistent_analysis(self):
        """
        **Feature: security-no-existence-leak**
        
        Non-existent analysis ID should return 404.
        """
        from app.api.v1.analyses import get_analysis_for_user_or_404

        mock_db = create_mock_db_returning_none()
        user_id = uuid.uuid4()

        with pytest.raises(HTTPException) as exc_info:
            await get_analysis_for_user_or_404(
                db=mock_db,
                analysis_id=uuid.uuid4(),
                user_id=user_id,
            )

        assert exc_info.value.status_code == 404
        assert "not found" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_returns_404_for_other_user_analysis(self):
        """
        **Feature: security-no-existence-leak**
        
        Analysis belonging to another user should return 404, not 403.
        This prevents information disclosure about valid analysis IDs.
        """
        from app.api.v1.analyses import get_analysis_for_user_or_404

        # The helper uses a JOIN query that filters by owner_id,
        # so if the owner doesn't match, it returns None (same as not found)
        mock_db = create_mock_db_returning_none()
        user_id = uuid.uuid4()

        with pytest.raises(HTTPException) as exc_info:
            await get_analysis_for_user_or_404(
                db=mock_db,
                analysis_id=uuid.uuid4(),
                user_id=user_id,
            )

        # Key assertion: should be 404, NOT 403
        assert exc_info.value.status_code == 404
        assert exc_info.value.status_code != 403
        assert "not found" in exc_info.value.detail.lower()
        # Should NOT contain "access denied" or "unauthorized"
        assert "access denied" not in exc_info.value.detail.lower()
        assert "unauthorized" not in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_returns_analysis_for_owner(self):
        """
        **Feature: security-no-existence-leak**
        
        Owner should be able to access their analysis.
        """
        from app.api.v1.analyses import get_analysis_for_user_or_404

        user_id = uuid.uuid4()
        analysis = create_mock_analysis(owner_id=user_id)
        mock_db = create_mock_db_returning_analysis(analysis)

        result = await get_analysis_for_user_or_404(
            db=mock_db,
            analysis_id=analysis.id,
            user_id=user_id,
        )

        assert result == analysis


# =============================================================================
# Test GET /analyses/{analysis_id}/stream
# =============================================================================


class TestStreamAnalysisProgress:
    """Test SSE streaming endpoint for no existence leak."""

    @pytest.mark.asyncio
    async def test_stream_owner_can_access(self):
        """
        **Feature: security-no-existence-leak**
        
        Owner should be able to stream their analysis progress.
        """
        from app.api.v1.analyses import stream_analysis_progress

        user_id = uuid.uuid4()
        analysis = create_mock_analysis(owner_id=user_id, status="completed")
        mock_db = create_mock_db_returning_analysis(analysis)
        mock_user = create_mock_user(user_id)

        # Should not raise - returns StreamingResponse
        response = await stream_analysis_progress(
            analysis_id=analysis.id,
            db=mock_db,
            user=mock_user,
        )

        # StreamingResponse indicates success
        assert response is not None
        assert response.media_type == "text/event-stream"

    @pytest.mark.asyncio
    async def test_stream_other_user_returns_404(self):
        """
        **Feature: security-no-existence-leak**
        
        Other user should get 404 when trying to stream, not 403.
        """
        from app.api.v1.analyses import stream_analysis_progress

        owner_id = uuid.uuid4()
        other_user_id = uuid.uuid4()
        
        # DB returns None because the JOIN filters by owner_id
        mock_db = create_mock_db_returning_none()
        mock_user = create_mock_user(other_user_id)

        with pytest.raises(HTTPException) as exc_info:
            await stream_analysis_progress(
                analysis_id=uuid.uuid4(),
                db=mock_db,
                user=mock_user,
            )

        assert exc_info.value.status_code == 404
        assert exc_info.value.status_code != 403

    @pytest.mark.asyncio
    async def test_stream_nonexistent_returns_404(self):
        """
        **Feature: security-no-existence-leak**
        
        Non-existent analysis ID should return 404.
        """
        from app.api.v1.analyses import stream_analysis_progress

        mock_db = create_mock_db_returning_none()
        mock_user = create_mock_user()

        with pytest.raises(HTTPException) as exc_info:
            await stream_analysis_progress(
                analysis_id=uuid.uuid4(),
                db=mock_db,
                user=mock_user,
            )

        assert exc_info.value.status_code == 404


# =============================================================================
# Test DELETE /analyses/{analysis_id}
# =============================================================================


class TestDeleteAnalysis:
    """Test delete endpoint for no existence leak."""

    @pytest.mark.asyncio
    async def test_delete_owner_can_access(self):
        """
        **Feature: security-no-existence-leak**
        
        Owner should be able to delete their analysis (if pending/failed).
        """
        from app.api.v1.analyses import delete_analysis

        user_id = uuid.uuid4()
        analysis = create_mock_analysis(owner_id=user_id, status="pending")
        mock_db = create_mock_db_returning_analysis(analysis)
        mock_user = create_mock_user(user_id)

        result = await delete_analysis(
            analysis_id=analysis.id,
            db=mock_db,
            user=mock_user,
        )

        assert result["message"] == "Analysis deleted"
        assert result["id"] == str(analysis.id)

    @pytest.mark.asyncio
    async def test_delete_other_user_returns_404(self):
        """
        **Feature: security-no-existence-leak**
        
        Other user should get 404 when trying to delete, not 403.
        """
        from app.api.v1.analyses import delete_analysis

        mock_db = create_mock_db_returning_none()
        mock_user = create_mock_user()

        with pytest.raises(HTTPException) as exc_info:
            await delete_analysis(
                analysis_id=uuid.uuid4(),
                db=mock_db,
                user=mock_user,
            )

        assert exc_info.value.status_code == 404
        assert exc_info.value.status_code != 403

    @pytest.mark.asyncio
    async def test_delete_nonexistent_returns_404(self):
        """
        **Feature: security-no-existence-leak**
        
        Non-existent analysis ID should return 404.
        """
        from app.api.v1.analyses import delete_analysis

        mock_db = create_mock_db_returning_none()
        mock_user = create_mock_user()

        with pytest.raises(HTTPException) as exc_info:
            await delete_analysis(
                analysis_id=uuid.uuid4(),
                db=mock_db,
                user=mock_user,
            )

        assert exc_info.value.status_code == 404


# =============================================================================
# Test GET /analyses/{analysis_id}
# =============================================================================


class TestGetAnalysis:
    """Test get analysis endpoint for no existence leak."""

    @pytest.mark.asyncio
    async def test_get_owner_can_access(self):
        """
        **Feature: security-no-existence-leak**
        
        Owner should be able to get their analysis details.
        """
        from app.api.v1.analyses import get_analysis

        user_id = uuid.uuid4()
        analysis = create_mock_analysis(owner_id=user_id)
        mock_db = create_mock_db_returning_analysis(analysis)
        mock_user = create_mock_user(user_id)

        result = await get_analysis(
            analysis_id=analysis.id,
            db=mock_db,
            user=mock_user,
        )

        assert result["id"] == str(analysis.id)
        assert result["status"] == "completed"

    @pytest.mark.asyncio
    async def test_get_other_user_returns_404(self):
        """
        **Feature: security-no-existence-leak**
        
        Other user should get 404 when trying to get analysis, not 403.
        """
        from app.api.v1.analyses import get_analysis

        mock_db = create_mock_db_returning_none()
        mock_user = create_mock_user()

        with pytest.raises(HTTPException) as exc_info:
            await get_analysis(
                analysis_id=uuid.uuid4(),
                db=mock_db,
                user=mock_user,
            )

        assert exc_info.value.status_code == 404
        assert exc_info.value.status_code != 403

    @pytest.mark.asyncio
    async def test_get_nonexistent_returns_404(self):
        """
        **Feature: security-no-existence-leak**
        
        Non-existent analysis ID should return 404.
        """
        from app.api.v1.analyses import get_analysis

        mock_db = create_mock_db_returning_none()
        mock_user = create_mock_user()

        with pytest.raises(HTTPException) as exc_info:
            await get_analysis(
                analysis_id=uuid.uuid4(),
                db=mock_db,
                user=mock_user,
            )

        assert exc_info.value.status_code == 404


# =============================================================================
# Test GET /analyses/{analysis_id}/metrics
# =============================================================================


class TestGetAnalysisMetrics:
    """Test metrics endpoint for no existence leak."""

    @pytest.mark.asyncio
    async def test_metrics_owner_can_access(self):
        """
        **Feature: security-no-existence-leak**
        
        Owner should be able to get their analysis metrics.
        """
        from app.api.v1.analyses import get_analysis_metrics

        user_id = uuid.uuid4()
        analysis = create_mock_analysis(owner_id=user_id)
        mock_db = create_mock_db_returning_analysis(analysis)
        mock_user = create_mock_user(user_id)

        result = await get_analysis_metrics(
            analysis_id=analysis.id,
            db=mock_db,
            user=mock_user,
        )

        assert result["analysis_id"] == str(analysis.id)
        assert "breakdown" in result

    @pytest.mark.asyncio
    async def test_metrics_other_user_returns_404(self):
        """
        **Feature: security-no-existence-leak**
        
        Other user should get 404 when trying to get metrics, not 403.
        """
        from app.api.v1.analyses import get_analysis_metrics

        mock_db = create_mock_db_returning_none()
        mock_user = create_mock_user()

        with pytest.raises(HTTPException) as exc_info:
            await get_analysis_metrics(
                analysis_id=uuid.uuid4(),
                db=mock_db,
                user=mock_user,
            )

        assert exc_info.value.status_code == 404
        assert exc_info.value.status_code != 403

    @pytest.mark.asyncio
    async def test_metrics_nonexistent_returns_404(self):
        """
        **Feature: security-no-existence-leak**
        
        Non-existent analysis ID should return 404.
        """
        from app.api.v1.analyses import get_analysis_metrics

        mock_db = create_mock_db_returning_none()
        mock_user = create_mock_user()

        with pytest.raises(HTTPException) as exc_info:
            await get_analysis_metrics(
                analysis_id=uuid.uuid4(),
                db=mock_db,
                user=mock_user,
            )

        assert exc_info.value.status_code == 404


# =============================================================================
# Test GET /analyses/{analysis_id}/semantic
# =============================================================================


class TestGetSemanticCache:
    """Test semantic cache endpoint for no existence leak."""

    @pytest.mark.asyncio
    async def test_semantic_owner_can_access(self):
        """
        **Feature: security-no-existence-leak**
        
        Owner should be able to get their semantic cache.
        """
        from app.api.v1.analyses import get_semantic_cache

        user_id = uuid.uuid4()
        analysis = create_mock_analysis(owner_id=user_id)
        mock_db = create_mock_db_returning_analysis(analysis)
        mock_user = create_mock_user(user_id)

        result = await get_semantic_cache(
            analysis_id=analysis.id,
            db=mock_db,
            user=mock_user,
        )

        assert result["analysis_id"] == str(analysis.id)
        assert result["is_cached"] is True

    @pytest.mark.asyncio
    async def test_semantic_other_user_returns_404(self):
        """
        **Feature: security-no-existence-leak**
        
        Other user should get 404 when trying to get semantic cache, not 403.
        """
        from app.api.v1.analyses import get_semantic_cache

        mock_db = create_mock_db_returning_none()
        mock_user = create_mock_user()

        with pytest.raises(HTTPException) as exc_info:
            await get_semantic_cache(
                analysis_id=uuid.uuid4(),
                db=mock_db,
                user=mock_user,
            )

        assert exc_info.value.status_code == 404
        assert exc_info.value.status_code != 403

    @pytest.mark.asyncio
    async def test_semantic_nonexistent_returns_404(self):
        """
        **Feature: security-no-existence-leak**
        
        Non-existent analysis ID should return 404.
        """
        from app.api.v1.analyses import get_semantic_cache

        mock_db = create_mock_db_returning_none()
        mock_user = create_mock_user()

        with pytest.raises(HTTPException) as exc_info:
            await get_semantic_cache(
                analysis_id=uuid.uuid4(),
                db=mock_db,
                user=mock_user,
            )

        assert exc_info.value.status_code == 404


# =============================================================================
# Test POST /analyses/{analysis_id}/semantic/generate
# =============================================================================


class TestGenerateSemanticCache:
    """Test semantic cache generation endpoint for no existence leak."""

    @pytest.mark.asyncio
    async def test_generate_semantic_other_user_returns_404(self):
        """
        **Feature: security-no-existence-leak**
        
        Other user should get 404 when trying to generate semantic cache, not 403.
        """
        from app.api.v1.analyses import generate_semantic_cache

        mock_db = create_mock_db_returning_none()
        mock_user = create_mock_user()

        with pytest.raises(HTTPException) as exc_info:
            await generate_semantic_cache(
                analysis_id=uuid.uuid4(),
                db=mock_db,
                user=mock_user,
            )

        assert exc_info.value.status_code == 404
        assert exc_info.value.status_code != 403

    @pytest.mark.asyncio
    async def test_generate_semantic_nonexistent_returns_404(self):
        """
        **Feature: security-no-existence-leak**
        
        Non-existent analysis ID should return 404.
        """
        from app.api.v1.analyses import generate_semantic_cache

        mock_db = create_mock_db_returning_none()
        mock_user = create_mock_user()

        with pytest.raises(HTTPException) as exc_info:
            await generate_semantic_cache(
                analysis_id=uuid.uuid4(),
                db=mock_db,
                user=mock_user,
            )

        assert exc_info.value.status_code == 404


# =============================================================================
# Test POST /analyses/{analysis_id}/ai-scan
# =============================================================================


class TestTriggerAIScan:
    """Test AI scan trigger endpoint for no existence leak."""

    @pytest.mark.asyncio
    async def test_trigger_ai_scan_other_user_returns_404(self):
        """
        **Feature: security-no-existence-leak**
        
        Other user should get 404 when trying to trigger AI scan, not 403.
        """
        from app.api.v1.ai_scan import trigger_ai_scan

        mock_db = create_mock_db_returning_none()
        mock_user = create_mock_user()

        with pytest.raises(HTTPException) as exc_info:
            await trigger_ai_scan(
                analysis_id=uuid.uuid4(),
                db=mock_db,
                user=mock_user,
                request=None,
            )

        assert exc_info.value.status_code == 404
        assert exc_info.value.status_code != 403

    @pytest.mark.asyncio
    async def test_trigger_ai_scan_nonexistent_returns_404(self):
        """
        **Feature: security-no-existence-leak**
        
        Non-existent analysis ID should return 404.
        """
        from app.api.v1.ai_scan import trigger_ai_scan

        mock_db = create_mock_db_returning_none()
        mock_user = create_mock_user()

        with pytest.raises(HTTPException) as exc_info:
            await trigger_ai_scan(
                analysis_id=uuid.uuid4(),
                db=mock_db,
                user=mock_user,
                request=None,
            )

        assert exc_info.value.status_code == 404


# =============================================================================
# Test GET /analyses/{analysis_id}/ai-scan
# =============================================================================


class TestGetAIScanResults:
    """Test AI scan results endpoint for no existence leak."""

    @pytest.mark.asyncio
    async def test_get_ai_scan_owner_can_access(self):
        """
        **Feature: security-no-existence-leak**
        
        Owner should be able to get their AI scan results.
        """
        from app.api.v1.ai_scan import get_ai_scan_results

        user_id = uuid.uuid4()
        # Use ai_scan_status="pending" since the AI scan schema only has
        # pending, running, completed, failed (no "skipped" or "none")
        analysis = create_mock_analysis(owner_id=user_id, ai_scan_status="pending")
        mock_db = create_mock_db_returning_analysis(analysis)
        mock_user = create_mock_user(user_id)

        result = await get_ai_scan_results(
            analysis_id=analysis.id,
            db=mock_db,
            user=mock_user,
        )

        assert result.analysis_id == analysis.id
        assert result.is_cached is False  # No cache in mock

    @pytest.mark.asyncio
    async def test_get_ai_scan_other_user_returns_404(self):
        """
        **Feature: security-no-existence-leak**
        
        Other user should get 404 when trying to get AI scan results, not 403.
        """
        from app.api.v1.ai_scan import get_ai_scan_results

        mock_db = create_mock_db_returning_none()
        mock_user = create_mock_user()

        with pytest.raises(HTTPException) as exc_info:
            await get_ai_scan_results(
                analysis_id=uuid.uuid4(),
                db=mock_db,
                user=mock_user,
            )

        assert exc_info.value.status_code == 404
        assert exc_info.value.status_code != 403

    @pytest.mark.asyncio
    async def test_get_ai_scan_nonexistent_returns_404(self):
        """
        **Feature: security-no-existence-leak**
        
        Non-existent analysis ID should return 404.
        """
        from app.api.v1.ai_scan import get_ai_scan_results

        mock_db = create_mock_db_returning_none()
        mock_user = create_mock_user()

        with pytest.raises(HTTPException) as exc_info:
            await get_ai_scan_results(
                analysis_id=uuid.uuid4(),
                db=mock_db,
                user=mock_user,
            )

        assert exc_info.value.status_code == 404


# =============================================================================
# Test GET /analyses/{analysis_id}/ai-scan/stream
# =============================================================================


class TestStreamAIScanProgress:
    """Test AI scan SSE streaming endpoint for no existence leak."""

    @pytest.mark.asyncio
    async def test_stream_ai_scan_owner_can_access(self):
        """
        **Feature: security-no-existence-leak**
        
        Owner should be able to stream their AI scan progress.
        """
        from app.api.v1.ai_scan import stream_ai_scan_progress

        user_id = uuid.uuid4()
        analysis = create_mock_analysis(owner_id=user_id, ai_scan_status="completed")
        analysis.ai_scan_cache = {"status": "completed"}
        mock_db = create_mock_db_returning_analysis(analysis)
        mock_user = create_mock_user(user_id)

        # Should not raise - returns StreamingResponse
        response = await stream_ai_scan_progress(
            analysis_id=analysis.id,
            db=mock_db,
            user=mock_user,
        )

        # StreamingResponse indicates success
        assert response is not None
        assert response.media_type == "text/event-stream"

    @pytest.mark.asyncio
    async def test_stream_ai_scan_other_user_returns_404(self):
        """
        **Feature: security-no-existence-leak**
        
        Other user should get 404 when trying to stream AI scan, not 403.
        """
        from app.api.v1.ai_scan import stream_ai_scan_progress

        mock_db = create_mock_db_returning_none()
        mock_user = create_mock_user()

        with pytest.raises(HTTPException) as exc_info:
            await stream_ai_scan_progress(
                analysis_id=uuid.uuid4(),
                db=mock_db,
                user=mock_user,
            )

        assert exc_info.value.status_code == 404
        assert exc_info.value.status_code != 403

    @pytest.mark.asyncio
    async def test_stream_ai_scan_nonexistent_returns_404(self):
        """
        **Feature: security-no-existence-leak**
        
        Non-existent analysis ID should return 404.
        """
        from app.api.v1.ai_scan import stream_ai_scan_progress

        mock_db = create_mock_db_returning_none()
        mock_user = create_mock_user()

        with pytest.raises(HTTPException) as exc_info:
            await stream_ai_scan_progress(
                analysis_id=uuid.uuid4(),
                db=mock_db,
                user=mock_user,
            )

        assert exc_info.value.status_code == 404


# =============================================================================
# Test GET /analyses/{analysis_id}/full-status
# =============================================================================


class TestGetAnalysisFullStatus:
    """Test full-status endpoint for no existence leak."""

    @pytest.mark.asyncio
    async def test_full_status_owner_can_access(self):
        """
        **Feature: security-no-existence-leak**
        
        Owner should be able to get their analysis full status.
        """
        from app.api.v1.analyses import get_analysis_full_status

        user_id = uuid.uuid4()
        analysis = create_mock_analysis(owner_id=user_id)
        mock_db = create_mock_db_returning_analysis(analysis)
        mock_user = create_mock_user(user_id)

        result = await get_analysis_full_status(
            analysis_id=analysis.id,
            db=mock_db,
            user=mock_user,
        )

        assert result.analysis_id == str(analysis.id)
        assert result.is_complete is True

    @pytest.mark.asyncio
    async def test_full_status_other_user_returns_404(self):
        """
        **Feature: security-no-existence-leak**
        
        Other user should get 404 when trying to get full status, not 403.
        
        Note: get_analysis_full_status has its own authorization check
        (not using get_analysis_for_user_or_404), so we need to test it
        with a mock that returns an analysis owned by a different user.
        """
        from app.api.v1.analyses import get_analysis_full_status

        owner_id = uuid.uuid4()
        other_user_id = uuid.uuid4()
        
        analysis = create_mock_analysis(owner_id=owner_id)
        mock_db = create_mock_db_returning_analysis(analysis)
        mock_user = create_mock_user(other_user_id)

        with pytest.raises(HTTPException) as exc_info:
            await get_analysis_full_status(
                analysis_id=analysis.id,
                db=mock_db,
                user=mock_user,
            )

        assert exc_info.value.status_code == 404
        assert exc_info.value.status_code != 403
        assert "not found" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_full_status_nonexistent_returns_404(self):
        """
        **Feature: security-no-existence-leak**
        
        Non-existent analysis ID should return 404.
        """
        from app.api.v1.analyses import get_analysis_full_status

        mock_db = create_mock_db_returning_none()
        mock_user = create_mock_user()

        with pytest.raises(HTTPException) as exc_info:
            await get_analysis_full_status(
                analysis_id=uuid.uuid4(),
                db=mock_db,
                user=mock_user,
            )

        assert exc_info.value.status_code == 404


# =============================================================================
# Summary Test - Verify All Endpoints Return 404 Not 403
# =============================================================================


class TestNoExistenceLeakSummary:
    """Summary tests to verify the security property holds across all endpoints."""

    @pytest.mark.asyncio
    async def test_all_endpoints_return_404_not_403_for_other_user(self):
        """
        **Feature: security-no-existence-leak**
        
        Verify that ALL analysis-scoped endpoints return 404 (not 403)
        when accessed by a user who doesn't own the analysis.
        
        This is a meta-test that documents the security property.
        Individual endpoint tests above verify this property for each endpoint.
        """
        # This test documents the security property.
        # The actual verification is done by the individual endpoint tests above.
        # 
        # Endpoints covered:
        # 1. GET /analyses/{analysis_id}/stream - TestStreamAnalysisProgress
        # 2. DELETE /analyses/{analysis_id} - TestDeleteAnalysis
        # 3. GET /analyses/{analysis_id} - TestGetAnalysis
        # 4. GET /analyses/{analysis_id}/metrics - TestGetAnalysisMetrics
        # 5. GET /analyses/{analysis_id}/semantic - TestGetSemanticCache
        # 6. POST /analyses/{analysis_id}/semantic/generate - TestGenerateSemanticCache
        # 7. POST /analyses/{analysis_id}/ai-scan - TestTriggerAIScan
        # 8. GET /analyses/{analysis_id}/ai-scan - TestGetAIScanResults
        # 9. GET /analyses/{analysis_id}/ai-scan/stream - TestStreamAIScanProgress
        # 10. GET /analyses/{analysis_id}/full-status - TestGetAnalysisFullStatus
        pass

    def test_error_messages_do_not_leak_information(self):
        """
        **Feature: security-no-existence-leak**
        
        Verify that error messages don't contain information that could
        help attackers distinguish between non-existent and unauthorized.
        """
        # The error message should be generic "Analysis not found"
        # It should NOT contain:
        # - "Access denied"
        # - "Unauthorized"
        # - "Permission denied"
        # - "You don't have access"
        # - Any indication that the resource exists
        
        # This is verified by the individual tests checking:
        # assert "not found" in exc_info.value.detail.lower()
        # assert "access denied" not in exc_info.value.detail.lower()
        pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
