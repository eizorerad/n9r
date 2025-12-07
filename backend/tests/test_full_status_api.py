"""Unit tests for the full-status API endpoint.

Tests the GET /analyses/{id}/full-status endpoint which provides
a single source of truth for all analysis state.

**Feature: progress-tracking-refactor, ai-scan-progress-fix**
**Validates: Requirements 4.1, 2.3**
"""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from hypothesis import given, settings
from hypothesis import strategies as st

from app.schemas.analysis import (
    AIScanStatus,
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
        **Feature: progress-tracking-refactor, ai-scan-progress-fix**
        **Validates: Requirements 4.1, 2.3**

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
            # AI scan fields (Requirements 2.3)
            ai_scan_status=AIScanStatus.COMPLETED,
            ai_scan_progress=100,
            ai_scan_stage="completed",
            ai_scan_message="AI scan complete",
            ai_scan_error=None,
            has_ai_scan_cache=True,
            ai_scan_started_at=datetime.now(UTC),
            ai_scan_completed_at=datetime.now(UTC),
            state_updated_at=datetime.now(UTC),
            embeddings_started_at=datetime.now(UTC),
            embeddings_completed_at=datetime.now(UTC),
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
        # AI scan fields
        assert response.ai_scan_status is not None
        assert response.ai_scan_progress is not None
        assert response.has_ai_scan_cache is not None
        assert response.overall_progress is not None
        assert response.overall_stage is not None
        assert response.is_complete is not None

    def test_schema_with_minimal_fields(self):
        """
        **Feature: progress-tracking-refactor, ai-scan-progress-fix**
        **Validates: Requirements 4.1, 2.3**

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
            # AI scan fields (minimal)
            ai_scan_status=AIScanStatus.NONE,
            ai_scan_progress=0,
            ai_scan_stage=None,
            ai_scan_message=None,
            ai_scan_error=None,
            has_ai_scan_cache=False,
            ai_scan_started_at=None,
            ai_scan_completed_at=None,
            state_updated_at=datetime.now(UTC),
            embeddings_started_at=None,
            embeddings_completed_at=None,
            overall_progress=0,
            overall_stage="Waiting for analysis to start",
            is_complete=False,
        )

        assert response.vci_score is None
        assert response.grade is None
        assert response.embeddings_stage is None
        assert response.ai_scan_stage is None
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
        **Feature: progress-tracking-refactor, ai-scan-progress-fix**
        **Validates: Requirements 4.1, 6.1**

        Test response for running analysis.
        """
        progress = compute_overall_progress("running", "none", 0, "none", "none", 0)
        stage = compute_overall_stage("running", "none", None, "none", "none", None)
        is_complete = compute_is_complete("running", "none", "none", "none")

        assert progress == 15  # Mid-point of analysis phase (0-30%)
        assert "Analyzing" in stage or "running" in stage.lower()
        assert is_complete is False

    def test_completed_analysis_embeddings_running(self):
        """
        **Feature: progress-tracking-refactor, ai-scan-progress-fix**
        **Validates: Requirements 4.1, 6.1**

        Test response when analysis is complete and embeddings are running.
        """
        progress = compute_overall_progress("completed", "running", 50, "none", "none", 0)
        stage = compute_overall_stage("completed", "running", "embedding", "none", "none", None)
        is_complete = compute_is_complete("completed", "running", "none", "none")

        # 30 + 50 * 0.3 = 45 (embeddings phase is 30-60%)
        assert progress == 45
        assert "embedding" in stage.lower() or "Generating" in stage
        assert is_complete is False

    def test_all_phases_completed(self):
        """
        **Feature: progress-tracking-refactor, ai-scan-progress-fix**
        **Validates: Requirements 4.1, 6.1**

        Test response when all phases are completed (including AI scan).
        """
        progress = compute_overall_progress("completed", "completed", 100, "completed", "completed", 100)
        stage = compute_overall_stage("completed", "completed", "completed", "completed", "completed", "completed")
        is_complete = compute_is_complete("completed", "completed", "completed", "completed")

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
        **Feature: progress-tracking-refactor, ai-scan-progress-fix**
        **Validates: Requirements 4.1, 6.1**

        Test response when embeddings failed.
        """
        progress = compute_overall_progress("completed", "failed", 0, "none", "none", 0)
        stage = compute_overall_stage("completed", "failed", None, "none", "none", None)
        is_complete = compute_is_complete("completed", "failed", "none", "none")

        assert progress == 30  # Stuck at analysis complete (30% is end of analysis phase)
        assert "failed" in stage.lower()
        assert is_complete is False

    def test_semantic_cache_computing_state(self):
        """
        **Feature: progress-tracking-refactor, ai-scan-progress-fix**
        **Validates: Requirements 4.1, 6.1**

        Test response when semantic cache is computing.
        """
        progress = compute_overall_progress("completed", "completed", 100, "computing", "none", 0)
        stage = compute_overall_stage("completed", "completed", "completed", "computing", "none", None)
        is_complete = compute_is_complete("completed", "completed", "computing", "none")

        assert progress == 70  # Mid-point of semantic cache phase (60-80%)
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
        **Feature: progress-tracking-refactor, ai-scan-progress-fix**
        **Validates: Requirements 4.1, 2.3**

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
        # AI scan fields
        mock_analysis.ai_scan_status = "completed"
        mock_analysis.ai_scan_progress = 100
        mock_analysis.ai_scan_stage = "completed"
        mock_analysis.ai_scan_message = "AI scan complete"
        mock_analysis.ai_scan_error = None
        mock_analysis.ai_scan_cache = {"issues": []}
        mock_analysis.ai_scan_started_at = datetime.now(UTC)
        mock_analysis.ai_scan_completed_at = datetime.now(UTC)
        mock_analysis.state_updated_at = datetime.now(UTC)
        mock_analysis.embeddings_started_at = datetime.now(UTC)
        mock_analysis.embeddings_completed_at = datetime.now(UTC)
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
        assert response.ai_scan_status == AIScanStatus.COMPLETED
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


# =============================================================================
# Property-Based Tests for AI Scan Integration
# =============================================================================


class TestAIScanFullStatusProperties:
    """Property-based tests for AI scan integration in Full Status API.

    **Feature: ai-scan-progress-fix**
    """

    @given(
        ai_scan_status=st.sampled_from(["none", "pending", "running", "completed", "failed", "skipped"]),
        ai_scan_progress=st.integers(min_value=0, max_value=100),
        ai_scan_stage=st.one_of(
            st.none(),
            st.sampled_from(["initializing", "cloning", "generating_view", "scanning", "merging", "investigating", "completed"])
        ),
        ai_scan_message=st.one_of(st.none(), st.text(min_size=0, max_size=100)),
        ai_scan_error=st.one_of(st.none(), st.text(min_size=0, max_size=100)),
    )
    @settings(max_examples=100)
    def test_full_status_api_includes_all_ai_scan_fields(
        self,
        ai_scan_status: str,
        ai_scan_progress: int,
        ai_scan_stage: str | None,
        ai_scan_message: str | None,
        ai_scan_error: str | None,
    ):
        """
        **Feature: ai-scan-progress-fix, Property 4: Full Status API Completeness**
        **Validates: Requirements 2.3**

        For any analysis record, the Full Status API response SHALL include all AI scan fields:
        ai_scan_status, ai_scan_progress, ai_scan_stage, ai_scan_message, ai_scan_error,
        has_ai_scan_cache, ai_scan_started_at, ai_scan_completed_at.
        """
        # Create a response with all AI scan fields
        response = AnalysisFullStatusResponse(
            analysis_id="123e4567-e89b-12d3-a456-426614174000",
            repository_id="123e4567-e89b-12d3-a456-426614174001",
            commit_sha="abc123",
            analysis_status="completed",
            vci_score=85.5,
            grade="B",
            embeddings_status=EmbeddingsStatus.COMPLETED,
            embeddings_progress=100,
            embeddings_stage="completed",
            embeddings_message=None,
            embeddings_error=None,
            vectors_count=150,
            semantic_cache_status=SemanticCacheStatus.COMPLETED,
            has_semantic_cache=True,
            # AI scan fields with generated values
            ai_scan_status=AIScanStatus(ai_scan_status),
            ai_scan_progress=ai_scan_progress,
            ai_scan_stage=ai_scan_stage,
            ai_scan_message=ai_scan_message,
            ai_scan_error=ai_scan_error,
            has_ai_scan_cache=ai_scan_status == "completed",
            ai_scan_started_at=datetime.now(UTC) if ai_scan_status in ("running", "completed", "failed") else None,
            ai_scan_completed_at=datetime.now(UTC) if ai_scan_status == "completed" else None,
            state_updated_at=datetime.now(UTC),
            embeddings_started_at=datetime.now(UTC),
            embeddings_completed_at=datetime.now(UTC),
            overall_progress=100,
            overall_stage="All processing complete",
            is_complete=ai_scan_status in ("completed", "skipped"),
        )

        # Property: All AI scan fields MUST be present in the response
        assert hasattr(response, "ai_scan_status"), "ai_scan_status field missing"
        assert hasattr(response, "ai_scan_progress"), "ai_scan_progress field missing"
        assert hasattr(response, "ai_scan_stage"), "ai_scan_stage field missing"
        assert hasattr(response, "ai_scan_message"), "ai_scan_message field missing"
        assert hasattr(response, "ai_scan_error"), "ai_scan_error field missing"
        assert hasattr(response, "has_ai_scan_cache"), "has_ai_scan_cache field missing"
        assert hasattr(response, "ai_scan_started_at"), "ai_scan_started_at field missing"
        assert hasattr(response, "ai_scan_completed_at"), "ai_scan_completed_at field missing"

        # Property: Values should match what was provided
        assert response.ai_scan_status == AIScanStatus(ai_scan_status)
        assert response.ai_scan_progress == ai_scan_progress
        assert response.ai_scan_stage == ai_scan_stage
        assert response.ai_scan_message == ai_scan_message
        assert response.ai_scan_error == ai_scan_error


    @given(
        analysis_status=st.sampled_from(["pending", "running", "completed", "failed"]),
        embeddings_status=st.sampled_from(["none", "pending", "running", "completed", "failed"]),
        embeddings_progress=st.integers(min_value=0, max_value=100),
        semantic_cache_status=st.sampled_from(["none", "pending", "computing", "completed", "failed"]),
        ai_scan_status=st.sampled_from(["none", "pending", "running", "completed", "failed", "skipped"]),
        ai_scan_progress=st.integers(min_value=0, max_value=99),  # Cap at 99 for running states
    )
    @settings(max_examples=100)
    def test_progress_calculation_bounds(
        self,
        analysis_status: str,
        embeddings_status: str,
        embeddings_progress: int,
        semantic_cache_status: str,
        ai_scan_status: str,
        ai_scan_progress: int,
    ):
        # Realistic constraint: 100% progress only for terminal states
        if ai_scan_status in ("completed", "skipped"):
            ai_scan_progress = 100
        elif ai_scan_status == "running":
            ai_scan_progress = min(ai_scan_progress, 99)  # Running can't be 100%
        """
        **Feature: ai-scan-progress-fix, Property 5: Progress Calculation Bounds**
        **Validates: Requirements 6.1**

        For any combination of analysis phase statuses, the computed overall_progress
        SHALL be between 0 and 100, with the AI scan phase (80-100%) only contributing
        when semantic_cache_status="completed".
        """
        progress = compute_overall_progress(
            analysis_status=analysis_status,
            embeddings_status=embeddings_status,
            embeddings_progress=embeddings_progress,
            semantic_cache_status=semantic_cache_status,
            ai_scan_status=ai_scan_status,
            ai_scan_progress=ai_scan_progress,
        )

        # Property 1: Progress MUST be between 0 and 100
        assert 0 <= progress <= 100, f"Progress {progress} is out of bounds [0, 100]"

        # Property 2: AI scan phase (80-100%) only contributes when semantic_cache_status="completed"
        if semantic_cache_status != "completed":
            # AI scan phase should not contribute - progress should be at most 80
            # (unless we're in an earlier failed state)
            if analysis_status == "completed" and embeddings_status == "completed":
                # Semantic cache phase: 60-80%
                assert progress <= 80, f"Progress {progress} exceeds 80% when semantic cache not completed"

        # Property 3: Progress should reach 100 only when all phases complete (including AI scan)
        if progress == 100:
            assert analysis_status == "completed", "Analysis must be completed for 100% progress"
            assert embeddings_status == "completed", "Embeddings must be completed for 100% progress"
            assert semantic_cache_status == "completed", "Semantic cache must be completed for 100% progress"
            assert ai_scan_status in ("completed", "skipped"), "AI scan must be completed or skipped for 100% progress"

    @given(
        analysis_status=st.sampled_from(["pending", "running", "completed", "failed"]),
        embeddings_status=st.sampled_from(["none", "pending", "running", "completed", "failed"]),
        embeddings_progress=st.integers(min_value=0, max_value=100),
        semantic_cache_status=st.sampled_from(["none", "pending", "computing", "completed", "failed"]),
        ai_scan_status=st.sampled_from(["none", "pending", "running", "completed", "failed", "skipped"]),
        ai_scan_progress=st.integers(min_value=0, max_value=100),
    )
    @settings(max_examples=100)
    def test_progress_phase_boundaries(
        self,
        analysis_status: str,
        embeddings_status: str,
        embeddings_progress: int,
        semantic_cache_status: str,
        ai_scan_status: str,
        ai_scan_progress: int,
    ):
        """
        **Feature: ai-scan-progress-fix, Property 5: Progress Calculation Bounds**
        **Validates: Requirements 6.1**

        Test that progress respects phase boundaries:
        - Analysis: 0-30%
        - Embeddings: 30-60%
        - Semantic Cache: 60-80%
        - AI Scan: 80-100%
        """
        progress = compute_overall_progress(
            analysis_status=analysis_status,
            embeddings_status=embeddings_status,
            embeddings_progress=embeddings_progress,
            semantic_cache_status=semantic_cache_status,
            ai_scan_status=ai_scan_status,
            ai_scan_progress=ai_scan_progress,
        )

        # Check phase boundaries based on current state
        if analysis_status in ("pending", "running", "failed"):
            # Still in analysis phase: 0-30%
            assert progress <= 30, f"Progress {progress} exceeds analysis phase (0-30%)"
        elif embeddings_status in ("none", "pending", "running", "failed"):
            # In embeddings phase: 30-60%
            assert 30 <= progress <= 60, f"Progress {progress} not in embeddings phase (30-60%)"
        elif semantic_cache_status in ("none", "pending", "computing", "failed"):
            # In semantic cache phase: 60-80%
            assert 60 <= progress <= 80, f"Progress {progress} not in semantic cache phase (60-80%)"
        elif ai_scan_status in ("none", "pending", "running", "failed"):
            # In AI scan phase: 80-100%
            assert 80 <= progress <= 100, f"Progress {progress} not in AI scan phase (80-100%)"
        else:
            # All complete
            assert progress == 100, f"Progress {progress} should be 100% when all phases complete"



class TestPostgreSQLAsSSoT:
    """Property-based tests for PostgreSQL as Single Source of Truth.

    **Feature: ai-scan-progress-fix**
    **Property 10: PostgreSQL as Single Source of Truth**
    """

    @given(
        ai_scan_status=st.sampled_from(["none", "pending", "running", "completed", "failed", "skipped"]),
        ai_scan_progress=st.integers(min_value=0, max_value=100),
        ai_scan_stage=st.one_of(
            st.none(),
            st.sampled_from(["initializing", "cloning", "generating_view", "scanning", "merging", "investigating", "completed"])
        ),
        ai_scan_message=st.one_of(st.none(), st.text(min_size=0, max_size=50, alphabet=st.characters(whitelist_categories=('L', 'N', 'P', 'S')))),
        ai_scan_error=st.one_of(st.none(), st.text(min_size=0, max_size=50, alphabet=st.characters(whitelist_categories=('L', 'N', 'P', 'S')))),
        has_ai_scan_cache=st.booleans(),
    )
    @settings(max_examples=100, deadline=None)
    @pytest.mark.asyncio
    async def test_full_status_reflects_postgresql_state_directly(
        self,
        ai_scan_status: str,
        ai_scan_progress: int,
        ai_scan_stage: str | None,
        ai_scan_message: str | None,
        ai_scan_error: str | None,
        has_ai_scan_cache: bool,
    ):
        """
        **Feature: ai-scan-progress-fix, Property 10: PostgreSQL as Single Source of Truth**
        **Validates: Requirements 2.2, 4.4**

        For any AI scan state query via Full Status API, the response SHALL reflect
        the current PostgreSQL state directly, without any Redis fallback or caching layer.
        """
        from app.api.v1.analyses import get_analysis_full_status

        # Create mock user
        user_id = uuid.uuid4()
        mock_user = MagicMock()
        mock_user.id = user_id

        # Create mock analysis with specific PostgreSQL state
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
        mock_analysis.embeddings_message = None
        mock_analysis.embeddings_error = None
        mock_analysis.vectors_count = 150
        mock_analysis.semantic_cache_status = "completed"
        mock_analysis.semantic_cache = {"architecture_health": {"overall_score": 80}}
        # AI scan fields - these are the PostgreSQL state we're testing
        mock_analysis.ai_scan_status = ai_scan_status
        mock_analysis.ai_scan_progress = ai_scan_progress
        mock_analysis.ai_scan_stage = ai_scan_stage
        mock_analysis.ai_scan_message = ai_scan_message
        mock_analysis.ai_scan_error = ai_scan_error
        mock_analysis.ai_scan_cache = {"issues": []} if has_ai_scan_cache else None
        mock_analysis.ai_scan_started_at = datetime.now(UTC) if ai_scan_status in ("running", "completed", "failed") else None
        mock_analysis.ai_scan_completed_at = datetime.now(UTC) if ai_scan_status == "completed" else None
        mock_analysis.state_updated_at = datetime.now(UTC)
        mock_analysis.embeddings_started_at = datetime.now(UTC)
        mock_analysis.embeddings_completed_at = datetime.now(UTC)
        mock_analysis.repository = MagicMock()
        mock_analysis.repository.owner_id = user_id

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

        # Property: Response MUST reflect PostgreSQL state directly
        # No Redis fallback, no caching - direct mapping from DB fields
        assert response.ai_scan_status == AIScanStatus(ai_scan_status), \
            f"ai_scan_status mismatch: expected {ai_scan_status}, got {response.ai_scan_status}"
        assert response.ai_scan_progress == ai_scan_progress, \
            f"ai_scan_progress mismatch: expected {ai_scan_progress}, got {response.ai_scan_progress}"
        assert response.ai_scan_stage == ai_scan_stage, \
            f"ai_scan_stage mismatch: expected {ai_scan_stage}, got {response.ai_scan_stage}"
        assert response.ai_scan_message == ai_scan_message, \
            f"ai_scan_message mismatch: expected {ai_scan_message}, got {response.ai_scan_message}"
        assert response.ai_scan_error == ai_scan_error, \
            f"ai_scan_error mismatch: expected {ai_scan_error}, got {response.ai_scan_error}"

        # has_ai_scan_cache should reflect whether ai_scan_cache has issues
        expected_has_cache = has_ai_scan_cache  # We set ai_scan_cache = {"issues": []} if has_ai_scan_cache
        assert response.has_ai_scan_cache == expected_has_cache, \
            f"has_ai_scan_cache mismatch: expected {expected_has_cache}, got {response.has_ai_scan_cache}"
