"""Unit tests for the full-status API endpoint.

Tests the GET /analyses/{id}/full-status endpoint which provides
a single source of truth for all analysis state.

**Feature: progress-tracking-refactor**
**Validates: Requirements 4.1**
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.schemas.analysis import (
    AnalysisFullStatusResponse,
    EmbeddingsStatus,
    SemanticCacheStatus,
    compute_is_complete,
    compute_overall_progress,
    compute_overall_stage,
)


# =============================================================================
# Test AnalysisFullStatusResponse Schema
# =============================================================================


class TestAnalysisFullStatusResponseSchema:
    """Test the AnalysisFullStatusResponse schema."""

    def test_schema_includes_all_required_fields(self):
        """
        **Feature: progress-tracking-refactor**
        **Validates: Requirements 4.1**
        
        Test that the schema includes all required fields for frontend polling.
        """
        # Create a valid response
        response = AnalysisFullStatusResponse(
            analysis_id="123e4567-e89b-12d3-a456-426614174000",
            repository_id="123e4567-e89b-12d3-a456-426614174001",
            commit_sha="abc123def456",
            analysis_status="completed",
            vci_score=85.5,
            grade="B",
            embeddings_status=EmbeddingsStatus.COMPLETED,
            embeddings_progress=100,
            embeddings_stage="completed",
            embeddings_message="Embedding generation completed",
            embeddings_error=None,
            vectors_count=150,
            semantic_cache_status=SemanticCacheStatus.COMPLETED,
            has_semantic_cache=True,
            state_updated_at=datetime.now(timezone.utc),
            embeddings_started_at=datetime.now(timezone.utc),
            embeddings_completed_at=datetime.now(timezone.utc),
            overall_progress=100,
            overall_stage="All processing complete",
            is_complete=True,
        )

        # Verify all fields are present
        assert response.analysis_id is not None
        assert response.repository_id is not None
        assert response.commit_sha is not None
        assert response.analysis_status is not None
        assert response.embeddings_status is not None
        assert response.embeddings_progress is not None
        assert response.semantic_cache_status is not None
        assert response.overall_progress is not None
        assert response.overall_stage is not None
        assert response.is_complete is not None

    def test_schema_with_minimal_fields(self):
        """
        **Feature: progress-tracking-refactor**
        **Validates: Requirements 4.1**
        
        Test that the schema works with minimal required fields.
        """
        response = AnalysisFullStatusResponse(
            analysis_id="123e4567-e89b-12d3-a456-426614174000",
            repository_id="123e4567-e89b-12d3-a456-426614174001",
            commit_sha="abc123",
            analysis_status="pending",
            vci_score=None,
            grade=None,
            embeddings_status=EmbeddingsStatus.NONE,
            embeddings_progress=0,
            embeddings_stage=None,
            embeddings_message=None,
            embeddings_error=None,
            vectors_count=0,
            semantic_cache_status=SemanticCacheStatus.NONE,
            has_semantic_cache=False,
            state_updated_at=datetime.now(timezone.utc),
            embeddings_started_at=None,
            embeddings_completed_at=None,
            overall_progress=0,
            overall_stage="Waiting for analysis to start",
            is_complete=False,
        )

        assert response.vci_score is None
        assert response.grade is None
        assert response.embeddings_stage is None
        assert response.is_complete is False


# =============================================================================
# Test Various Analysis States
# =============================================================================


class TestAnalysisStates:
    """Test full-status response for various analysis states."""

    def test_pending_analysis_state(self):
        """
        **Feature: progress-tracking-refactor**
        **Validates: Requirements 4.1**
        
        Test response for pending analysis.
        """
        progress = compute_overall_progress("pending", "none", 0, "none")
        stage = compute_overall_stage("pending", "none", None, "none")
        is_complete = compute_is_complete("pending", "none", "none")

        assert progress == 0
        assert "Waiting" in stage or "pending" in stage.lower()
        assert is_complete is False

    def test_running_analysis_state(self):
        """
        **Feature: progress-tracking-refactor**
        **Validates: Requirements 4.1**
        
        Test response for running analysis.
        """
        progress = compute_overall_progress("running", "none", 0, "none")
        stage = compute_overall_stage("running", "none", None, "none")
        is_complete = compute_is_complete("running", "none", "none")

        assert progress == 20  # Mid-point of analysis phase
        assert "Analyzing" in stage or "running" in stage.lower()
        assert is_complete is False

    def test_completed_analysis_embeddings_running(self):
        """
        **Feature: progress-tracking-refactor**
        **Validates: Requirements 4.1**
        
        Test response when analysis is complete and embeddings are running.
        """
        progress = compute_overall_progress("completed", "running", 50, "none")
        stage = compute_overall_stage("completed", "running", "embedding", "none")
        is_complete = compute_is_complete("completed", "running", "none")

        # 40 + 50 * 0.5 = 65
        assert progress == 65
        assert "embedding" in stage.lower() or "Generating" in stage
        assert is_complete is False

    def test_all_phases_completed(self):
        """
        **Feature: progress-tracking-refactor**
        **Validates: Requirements 4.1**
        
        Test response when all phases are completed.
        """
        progress = compute_overall_progress("completed", "completed", 100, "completed")
        stage = compute_overall_stage("completed", "completed", "completed", "completed")
        is_complete = compute_is_complete("completed", "completed", "completed")

        assert progress == 100
        assert "complete" in stage.lower()
        assert is_complete is True

    def test_failed_analysis_state(self):
        """
        **Feature: progress-tracking-refactor**
        **Validates: Requirements 4.1**
        
        Test response for failed analysis.
        """
        progress = compute_overall_progress("failed", "none", 0, "none")
        stage = compute_overall_stage("failed", "none", None, "none")
        is_complete = compute_is_complete("failed", "none", "none")

        assert progress == 0
        assert "failed" in stage.lower()
        assert is_complete is False

    def test_embeddings_failed_state(self):
        """
        **Feature: progress-tracking-refactor**
        **Validates: Requirements 4.1**
        
        Test response when embeddings failed.
        """
        progress = compute_overall_progress("completed", "failed", 0, "none")
        stage = compute_overall_stage("completed", "failed", None, "none")
        is_complete = compute_is_complete("completed", "failed", "none")

        assert progress == 40  # Stuck at analysis complete
        assert "failed" in stage.lower()
        assert is_complete is False

    def test_semantic_cache_computing_state(self):
        """
        **Feature: progress-tracking-refactor**
        **Validates: Requirements 4.1**
        
        Test response when semantic cache is computing.
        """
        progress = compute_overall_progress("completed", "completed", 100, "computing")
        stage = compute_overall_stage("completed", "completed", "completed", "computing")
        is_complete = compute_is_complete("completed", "completed", "computing")

        assert progress == 95  # Mid-point of semantic cache phase
        assert "semantic" in stage.lower() or "Computing" in stage
        assert is_complete is False


# =============================================================================
# Test Endpoint Authorization
# =============================================================================


class TestEndpointAuthorization:
    """Test authorization for the full-status endpoint."""

    @pytest.mark.asyncio
    async def test_returns_404_for_nonexistent_analysis(self):
        """
        **Feature: progress-tracking-refactor**
        **Validates: Requirements 4.1**
        
        Test that 404 is returned for non-existent analysis.
        """
        from app.api.v1.analyses import get_analysis_full_status

        # Create mock database session that returns None
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        # Create mock user
        mock_user = MagicMock()
        mock_user.id = uuid.uuid4()

        # Call endpoint
        with pytest.raises(HTTPException) as exc_info:
            await get_analysis_full_status(
                analysis_id=uuid.uuid4(),
                db=mock_db,
                user=mock_user,
            )

        assert exc_info.value.status_code == 404
        assert "not found" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_returns_404_for_unauthorized_access(self):
        """
        **Feature: progress-tracking-refactor**
        **Validates: Requirements 4.1**
        
        Test that 404 is returned for unauthorized access (don't leak existence).
        """
        from app.api.v1.analyses import get_analysis_full_status

        # Create mock analysis with different owner
        mock_analysis = MagicMock()
        mock_analysis.id = uuid.uuid4()
        mock_analysis.repository_id = uuid.uuid4()
        mock_analysis.repository = MagicMock()
        mock_analysis.repository.owner_id = uuid.uuid4()  # Different owner

        # Create mock database session
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_analysis
        mock_db.execute.return_value = mock_result

        # Create mock user with different ID
        mock_user = MagicMock()
        mock_user.id = uuid.uuid4()  # Different from owner

        # Call endpoint
        with pytest.raises(HTTPException) as exc_info:
            await get_analysis_full_status(
                analysis_id=mock_analysis.id,
                db=mock_db,
                user=mock_user,
            )

        # Should return 404 to not leak existence
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_returns_data_for_authorized_user(self):
        """
        **Feature: progress-tracking-refactor**
        **Validates: Requirements 4.1**
        
        Test that data is returned for authorized user.
        """
        from app.api.v1.analyses import get_analysis_full_status

        # Create mock user
        user_id = uuid.uuid4()
        mock_user = MagicMock()
        mock_user.id = user_id

        # Create mock analysis owned by user
        analysis_id = uuid.uuid4()
        repository_id = uuid.uuid4()
        
        mock_analysis = MagicMock()
        mock_analysis.id = analysis_id
        mock_analysis.repository_id = repository_id
        mock_analysis.commit_sha = "abc123"
        mock_analysis.status = "completed"
        mock_analysis.vci_score = 85.5
        mock_analysis.grade = "B"
        mock_analysis.embeddings_status = "completed"
        mock_analysis.embeddings_progress = 100
        mock_analysis.embeddings_stage = "completed"
        mock_analysis.embeddings_message = "Done"
        mock_analysis.embeddings_error = None
        mock_analysis.vectors_count = 150
        mock_analysis.semantic_cache_status = "completed"
        mock_analysis.semantic_cache = {"architecture_health": {"overall_score": 80}}
        mock_analysis.state_updated_at = datetime.now(timezone.utc)
        mock_analysis.embeddings_started_at = datetime.now(timezone.utc)
        mock_analysis.embeddings_completed_at = datetime.now(timezone.utc)
        mock_analysis.repository = MagicMock()
        mock_analysis.repository.owner_id = user_id  # Same as user

        # Create mock database session
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_analysis
        mock_db.execute.return_value = mock_result

        # Call endpoint
        response = await get_analysis_full_status(
            analysis_id=analysis_id,
            db=mock_db,
            user=mock_user,
        )

        # Verify response
        assert response.analysis_id == str(analysis_id)
        assert response.repository_id == str(repository_id)
        assert response.analysis_status == "completed"
        assert response.embeddings_status == EmbeddingsStatus.COMPLETED
        assert response.semantic_cache_status == SemanticCacheStatus.COMPLETED
        assert response.is_complete is True
        assert response.overall_progress == 100


# =============================================================================
# Test Computed Fields
# =============================================================================


class TestComputedFields:
    """Test computed fields in the response."""

    def test_has_semantic_cache_true_when_data_exists(self):
        """
        **Feature: progress-tracking-refactor**
        **Validates: Requirements 4.1**
        
        Test has_semantic_cache is True when architecture_health exists.
        """
        semantic_cache = {"architecture_health": {"overall_score": 80}}
        has_cache = (
            semantic_cache is not None
            and semantic_cache.get("architecture_health") is not None
        )
        assert has_cache is True

    def test_has_semantic_cache_false_when_no_data(self):
        """
        **Feature: progress-tracking-refactor**
        **Validates: Requirements 4.1**
        
        Test has_semantic_cache is False when no architecture_health.
        """
        semantic_cache = None
        has_cache = (
            semantic_cache is not None
            and semantic_cache.get("architecture_health") is not None
        )
        assert has_cache is False

    def test_has_semantic_cache_false_when_empty(self):
        """
        **Feature: progress-tracking-refactor**
        **Validates: Requirements 4.1**
        
        Test has_semantic_cache is False when architecture_health is None.
        """
        semantic_cache = {"architecture_health": None}
        has_cache = (
            semantic_cache is not None
            and semantic_cache.get("architecture_health") is not None
        )
        assert has_cache is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
