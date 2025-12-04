"""Integration tests for embeddings workflow with AnalysisStateService.

Tests the full workflow from pending to completed, verifying state transitions
and final state through the AnalysisStateService.

**Feature: progress-tracking-refactor**
**Validates: Requirements 2.1, 2.2, 2.3, 2.5**
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.services.analysis_state import (
    AnalysisStateService,
    InvalidStateTransitionError,
)


# =============================================================================
# Test Fixtures
# =============================================================================


def create_mock_analysis(
    analysis_id: uuid.UUID | None = None,
    embeddings_status: str = "none",
    embeddings_progress: int = 0,
    embeddings_stage: str | None = None,
    embeddings_message: str | None = None,
    embeddings_error: str | None = None,
    embeddings_started_at: datetime | None = None,
    embeddings_completed_at: datetime | None = None,
    vectors_count: int = 0,
    semantic_cache_status: str = "none",
    semantic_cache: dict | None = None,
) -> MagicMock:
    """Create a mock Analysis object for testing."""
    mock = MagicMock()
    mock.id = analysis_id or uuid.uuid4()
    mock.embeddings_status = embeddings_status
    mock.embeddings_progress = embeddings_progress
    mock.embeddings_stage = embeddings_stage
    mock.embeddings_message = embeddings_message
    mock.embeddings_error = embeddings_error
    mock.embeddings_started_at = embeddings_started_at
    mock.embeddings_completed_at = embeddings_completed_at
    mock.vectors_count = vectors_count
    mock.semantic_cache_status = semantic_cache_status
    mock.semantic_cache = semantic_cache
    mock.state_updated_at = datetime.now(timezone.utc)
    return mock


def create_mock_session(mock_analysis: MagicMock) -> MagicMock:
    """Create a mock SQLAlchemy session."""
    mock_session = MagicMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_analysis
    mock_session.execute.return_value = mock_result
    return mock_session


# =============================================================================
# Integration Tests: Full Embeddings Workflow
# =============================================================================


class TestEmbeddingsWorkflowIntegration:
    """
    Integration tests for the full embeddings workflow.
    
    **Feature: progress-tracking-refactor**
    **Validates: Requirements 2.1, 2.2, 2.3, 2.5**
    """

    def test_full_workflow_pending_to_completed(self):
        """
        Test full workflow from pending to completed.
        
        **Validates: Requirements 2.1, 2.2, 2.3, 2.5**
        
        Workflow:
        1. none -> pending (mark_embeddings_pending)
        2. pending -> running (start_embeddings)
        3. Progress updates during running
        4. running -> completed (complete_embeddings)
        5. Verify semantic_cache_status -> pending (auto-triggered)
        """
        analysis_id = uuid.uuid4()
        
        # Step 1: Create analysis in 'none' state
        mock_analysis = create_mock_analysis(
            analysis_id=analysis_id,
            embeddings_status="none",
        )
        mock_session = create_mock_session(mock_analysis)
        
        with patch('app.core.redis.publish_analysis_event'):
            service = AnalysisStateService(mock_session, publish_events=True)
            
            # Step 1: none -> pending
            service.mark_embeddings_pending(analysis_id)
            assert mock_analysis.embeddings_status == "pending"
            assert mock_analysis.embeddings_progress == 0
            
            # Step 2: pending -> running
            service.start_embeddings(analysis_id)
            assert mock_analysis.embeddings_status == "running"
            assert mock_analysis.embeddings_stage == "initializing"
            assert mock_analysis.embeddings_started_at is not None
            
            # Step 3: Progress updates
            service.update_embeddings_progress(analysis_id, 25, "chunking", "Chunking files...")
            assert mock_analysis.embeddings_progress == 25
            assert mock_analysis.embeddings_stage == "chunking"
            
            service.update_embeddings_progress(analysis_id, 50, "embedding", "Generating embeddings...")
            assert mock_analysis.embeddings_progress == 50
            assert mock_analysis.embeddings_stage == "embedding"
            
            service.update_embeddings_progress(analysis_id, 85, "indexing", "Storing vectors...")
            assert mock_analysis.embeddings_progress == 85
            assert mock_analysis.embeddings_stage == "indexing"
            
            # Step 4: running -> completed
            vectors_count = 150
            service.complete_embeddings(analysis_id, vectors_count)
            assert mock_analysis.embeddings_status == "completed"
            assert mock_analysis.embeddings_progress == 100
            assert mock_analysis.vectors_count == vectors_count
            assert mock_analysis.embeddings_completed_at is not None
            
            # Step 5: Verify semantic_cache_status auto-triggered to pending
            assert mock_analysis.semantic_cache_status == "pending"

    def test_workflow_with_failure_and_retry(self):
        """
        Test workflow with failure and retry mechanism.
        
        **Validates: Requirements 2.4**
        
        Workflow:
        1. none -> pending
        2. pending -> running
        3. running -> failed (error occurs)
        4. failed -> pending (retry)
        5. pending -> running
        6. running -> completed
        """
        analysis_id = uuid.uuid4()
        
        mock_analysis = create_mock_analysis(
            analysis_id=analysis_id,
            embeddings_status="none",
        )
        mock_session = create_mock_session(mock_analysis)
        
        with patch('app.core.redis.publish_analysis_event'):
            service = AnalysisStateService(mock_session, publish_events=True)
            
            # Step 1-2: none -> pending -> running
            service.mark_embeddings_pending(analysis_id)
            service.start_embeddings(analysis_id)
            assert mock_analysis.embeddings_status == "running"
            
            # Step 3: running -> failed
            error_message = "Connection timeout to embedding API"
            service.fail_embeddings(analysis_id, error_message)
            assert mock_analysis.embeddings_status == "failed"
            assert mock_analysis.embeddings_error == error_message
            
            # Step 4: failed -> pending (retry)
            service.mark_embeddings_pending(analysis_id)
            assert mock_analysis.embeddings_status == "pending"
            
            # Step 5-6: pending -> running -> completed
            service.start_embeddings(analysis_id)
            assert mock_analysis.embeddings_status == "running"
            
            service.complete_embeddings(analysis_id, 100)
            assert mock_analysis.embeddings_status == "completed"

    @given(vectors_count=st.integers(min_value=0, max_value=100000))
    @settings(max_examples=50)
    def test_state_transitions_are_validated(self, vectors_count: int):
        """
        Test that invalid state transitions are rejected.
        
        **Validates: Requirements 5.1, 5.2**
        
        Property: Invalid state transitions SHALL be rejected with
        InvalidStateTransitionError.
        """
        analysis_id = uuid.uuid4()
        
        # Create analysis in 'none' state
        mock_analysis = create_mock_analysis(
            analysis_id=analysis_id,
            embeddings_status="none",
        )
        mock_session = create_mock_session(mock_analysis)
        
        with patch('app.core.redis.publish_analysis_event'):
            service = AnalysisStateService(mock_session, publish_events=True)
            
            # Invalid: none -> running (should be none -> pending -> running)
            with pytest.raises(InvalidStateTransitionError):
                service.start_embeddings(analysis_id)
            
            # Invalid: none -> completed
            with pytest.raises(InvalidStateTransitionError):
                service.complete_embeddings(analysis_id, vectors_count)

    def test_completed_is_terminal_state(self):
        """
        Test that 'completed' is a terminal state.
        
        **Validates: Requirements 5.2**
        
        Property: When embeddings_status is 'completed', no transitions
        SHALL be allowed.
        """
        analysis_id = uuid.uuid4()
        
        # Create analysis in 'completed' state
        mock_analysis = create_mock_analysis(
            analysis_id=analysis_id,
            embeddings_status="completed",
            embeddings_progress=100,
            vectors_count=100,
        )
        mock_session = create_mock_session(mock_analysis)
        
        with patch('app.core.redis.publish_analysis_event'):
            service = AnalysisStateService(mock_session, publish_events=True)
            
            # All transitions from 'completed' should fail
            with pytest.raises(InvalidStateTransitionError):
                service.mark_embeddings_pending(analysis_id)
            
            with pytest.raises(InvalidStateTransitionError):
                service.start_embeddings(analysis_id)
            
            with pytest.raises(InvalidStateTransitionError):
                service.fail_embeddings(analysis_id, "error")

    @given(
        progress_values=st.lists(
            st.integers(min_value=0, max_value=100),
            min_size=1,
            max_size=10,
        )
    )
    @settings(max_examples=50)
    def test_progress_updates_during_running(self, progress_values: list[int]):
        """
        Test that progress updates work correctly during 'running' state.
        
        **Validates: Requirements 2.2**
        
        Property: Progress updates SHALL only be allowed when status is 'running'.
        """
        analysis_id = uuid.uuid4()
        
        # Create analysis in 'running' state
        mock_analysis = create_mock_analysis(
            analysis_id=analysis_id,
            embeddings_status="running",
            embeddings_progress=0,
        )
        mock_session = create_mock_session(mock_analysis)
        
        with patch('app.core.redis.publish_analysis_event'):
            service = AnalysisStateService(mock_session, publish_events=True)
            
            # All progress updates should succeed
            for progress in progress_values:
                service.update_embeddings_progress(
                    analysis_id, progress, "processing", f"Progress: {progress}%"
                )
                assert mock_analysis.embeddings_progress == progress


# =============================================================================
# Integration Tests: Semantic Cache Workflow
# =============================================================================


class TestSemanticCacheWorkflowIntegration:
    """
    Integration tests for the semantic cache workflow.
    
    **Feature: progress-tracking-refactor**
    **Validates: Requirements 3.1, 3.2, 3.3**
    """

    def test_semantic_cache_workflow(self):
        """
        Test full semantic cache workflow.
        
        **Validates: Requirements 3.1, 3.2, 3.3**
        
        Workflow:
        1. pending -> computing (start_semantic_cache)
        2. computing -> completed (complete_semantic_cache)
        """
        analysis_id = uuid.uuid4()
        
        # Create analysis with semantic_cache_status='pending'
        mock_analysis = create_mock_analysis(
            analysis_id=analysis_id,
            embeddings_status="completed",
            semantic_cache_status="pending",
        )
        mock_session = create_mock_session(mock_analysis)
        
        with patch('app.core.redis.publish_analysis_event'):
            service = AnalysisStateService(mock_session, publish_events=True)
            
            # Step 1: pending -> computing
            service.start_semantic_cache(analysis_id)
            assert mock_analysis.semantic_cache_status == "computing"
            
            # Step 2: computing -> completed
            cache_data = {
                "clusters": [{"id": 1, "name": "test"}],
                "health_score": 85,
            }
            service.complete_semantic_cache(analysis_id, cache_data)
            assert mock_analysis.semantic_cache_status == "completed"
            assert mock_analysis.semantic_cache == cache_data

    def test_semantic_cache_failure_and_retry(self):
        """
        Test semantic cache failure and retry.
        
        **Validates: Requirements 3.3**
        """
        analysis_id = uuid.uuid4()
        
        mock_analysis = create_mock_analysis(
            analysis_id=analysis_id,
            embeddings_status="completed",
            semantic_cache_status="pending",
        )
        mock_session = create_mock_session(mock_analysis)
        
        with patch('app.core.redis.publish_analysis_event'):
            service = AnalysisStateService(mock_session, publish_events=True)
            
            # Start computing
            service.start_semantic_cache(analysis_id)
            assert mock_analysis.semantic_cache_status == "computing"
            
            # Fail
            service.fail_semantic_cache(analysis_id, "Cluster analysis failed")
            assert mock_analysis.semantic_cache_status == "failed"
            
            # Retry: failed -> pending
            # Note: This requires updating the mock to reflect the new state
            mock_analysis.semantic_cache_status = "failed"
            service.update_semantic_cache_status(analysis_id, "pending")
            assert mock_analysis.semantic_cache_status == "pending"


# =============================================================================
# Integration Tests: Worker State Updates
# =============================================================================


class TestWorkerStateUpdates:
    """
    Tests for worker state update helper function.
    
    **Feature: progress-tracking-refactor**
    **Validates: Requirements 2.1, 2.2, 2.3, 2.4**
    """

    def test_update_embeddings_state_function_exists(self):
        """Test that _update_embeddings_state function is importable."""
        from app.workers.embeddings import _update_embeddings_state
        assert callable(_update_embeddings_state)

    def test_compute_semantic_cache_task_exists(self):
        """Test that compute_semantic_cache task is registered."""
        from app.workers.embeddings import compute_semantic_cache
        assert compute_semantic_cache is not None
        assert hasattr(compute_semantic_cache, 'delay')

    def test_generate_embeddings_task_exists(self):
        """Test that generate_embeddings task is registered."""
        from app.workers.embeddings import generate_embeddings
        assert generate_embeddings is not None
        assert hasattr(generate_embeddings, 'delay')
