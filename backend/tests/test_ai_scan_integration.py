"""Integration tests for AI scan pipeline integration.

Tests the full pipeline from analyze_repository → embeddings → semantic_cache → ai_scan,
verifying automatic chaining works end-to-end and the Full Status API returns correct state.

**Feature: ai-scan-progress-fix**
**Validates: Requirements 1.1, 2.3, 6.1**
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
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
from app.services.analysis_state import (
    AI_SCAN_TRANSITIONS,
    AnalysisStateService,
    InvalidStateTransitionError,
    is_valid_ai_scan_transition,
)


# =============================================================================
# Test Fixtures
# =============================================================================


def create_mock_analysis(
    analysis_id: uuid.UUID | None = None,
    status: str = "completed",
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
    ai_scan_status: str = "none",
    ai_scan_progress: int = 0,
    ai_scan_stage: str | None = None,
    ai_scan_message: str | None = None,
    ai_scan_error: str | None = None,
    ai_scan_cache: dict | None = None,
    ai_scan_started_at: datetime | None = None,
    ai_scan_completed_at: datetime | None = None,
) -> MagicMock:
    """Create a mock Analysis object for testing."""
    mock = MagicMock()
    mock.id = analysis_id or uuid.uuid4()
    mock.status = status
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
    mock.ai_scan_status = ai_scan_status
    mock.ai_scan_progress = ai_scan_progress
    mock.ai_scan_stage = ai_scan_stage
    mock.ai_scan_message = ai_scan_message
    mock.ai_scan_error = ai_scan_error
    mock.ai_scan_cache = ai_scan_cache
    mock.ai_scan_started_at = ai_scan_started_at
    mock.ai_scan_completed_at = ai_scan_completed_at
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
# Integration Tests: Full Pipeline (Task 19.1)
# =============================================================================


class TestFullPipelineIntegration:
    """
    Integration tests for the full analysis pipeline.
    
    Tests: analyze_repository → embeddings → semantic_cache → ai_scan
    Verifies automatic chaining works end-to-end.
    
    **Feature: ai-scan-progress-fix**
    **Validates: Requirements 1.1**
    """

    def test_full_pipeline_chaining_with_ai_scan_enabled(self):
        """
        Test full pipeline from analysis to AI scan with ai_scan_enabled=True.
        
        **Validates: Requirements 1.1**
        
        Workflow:
        1. Analysis completes → embeddings_status = pending
        2. Embeddings complete → semantic_cache_status = pending
        3. Semantic cache completes → ai_scan_status = pending (auto-triggered)
        4. AI scan completes → ai_scan_status = completed
        """
        analysis_id = uuid.uuid4()
        
        # Step 1: Create analysis in 'completed' state with embeddings 'none'
        mock_analysis = create_mock_analysis(
            analysis_id=analysis_id,
            status="completed",
            embeddings_status="none",
            semantic_cache_status="none",
            ai_scan_status="none",
        )
        mock_session = create_mock_session(mock_analysis)
        
        with patch('app.core.redis.publish_analysis_event'):
            with patch('app.core.config.settings') as mock_settings:
                mock_settings.ai_scan_enabled = True
                
                service = AnalysisStateService(mock_session, publish_events=True)
                
                # Step 1: Mark embeddings pending (simulating analyze_repository completion)
                service.mark_embeddings_pending(analysis_id)
                assert mock_analysis.embeddings_status == "pending"
                
                # Step 2: Start and complete embeddings
                service.start_embeddings(analysis_id)
                assert mock_analysis.embeddings_status == "running"
                
                service.complete_embeddings(analysis_id, vectors_count=100)
                assert mock_analysis.embeddings_status == "completed"
                # Verify semantic_cache_status auto-triggered to pending
                assert mock_analysis.semantic_cache_status == "pending"
                
                # Step 3: Start and complete semantic cache
                service.start_semantic_cache(analysis_id)
                assert mock_analysis.semantic_cache_status == "computing"
                
                cache_data = {"clusters": [], "architecture_health": {"overall_score": 80}}
                service.complete_semantic_cache(analysis_id, cache_data)
                assert mock_analysis.semantic_cache_status == "completed"
                # Verify ai_scan_status auto-triggered to pending (Requirements 1.1)
                assert mock_analysis.ai_scan_status == "pending"
                
                # Step 4: Start and complete AI scan
                service.start_ai_scan(analysis_id)
                assert mock_analysis.ai_scan_status == "running"
                assert mock_analysis.ai_scan_started_at is not None
                
                ai_scan_cache = {"issues": [], "status": "completed"}
                service.complete_ai_scan(analysis_id, ai_scan_cache)
                assert mock_analysis.ai_scan_status == "completed"
                assert mock_analysis.ai_scan_completed_at is not None
                assert mock_analysis.ai_scan_cache == ai_scan_cache

    def test_full_pipeline_chaining_with_ai_scan_disabled(self):
        """
        Test full pipeline with ai_scan_enabled=False.
        
        **Validates: Requirements 5.1**
        
        When AI scan is disabled, semantic cache completion should set
        ai_scan_status to 'skipped' instead of 'pending'.
        """
        analysis_id = uuid.uuid4()
        
        mock_analysis = create_mock_analysis(
            analysis_id=analysis_id,
            status="completed",
            embeddings_status="completed",
            semantic_cache_status="computing",
            ai_scan_status="none",
        )
        mock_session = create_mock_session(mock_analysis)
        
        with patch('app.core.redis.publish_analysis_event'):
            with patch('app.core.config.settings') as mock_settings:
                mock_settings.ai_scan_enabled = False
                
                service = AnalysisStateService(mock_session, publish_events=True)
                
                # Complete semantic cache with AI scan disabled
                cache_data = {"clusters": [], "architecture_health": {"overall_score": 80}}
                service.complete_semantic_cache(analysis_id, cache_data)
                
                # Verify ai_scan_status is 'skipped' (not 'pending')
                assert mock_analysis.ai_scan_status == "skipped"

    def test_ai_scan_state_transitions_are_validated(self):
        """
        Test that AI scan state transitions are validated.
        
        **Validates: Requirements 1.2, 1.3, 1.4**
        
        Property: Invalid state transitions SHALL be rejected with
        InvalidStateTransitionError.
        """
        analysis_id = uuid.uuid4()
        
        # Create analysis with ai_scan_status='none'
        mock_analysis = create_mock_analysis(
            analysis_id=analysis_id,
            ai_scan_status="none",
        )
        mock_session = create_mock_session(mock_analysis)
        
        with patch('app.core.redis.publish_analysis_event'):
            service = AnalysisStateService(mock_session, publish_events=True)
            
            # Invalid: none -> running (should be none -> pending -> running)
            with pytest.raises(InvalidStateTransitionError):
                service.start_ai_scan(analysis_id)
            
            # Invalid: none -> completed
            with pytest.raises(InvalidStateTransitionError):
                service.complete_ai_scan(analysis_id, {"issues": []})

    def test_ai_scan_failure_and_retry(self):
        """
        Test AI scan failure and retry mechanism.
        
        **Validates: Requirements 5.2, 5.3**
        
        Workflow:
        1. pending -> running
        2. running -> failed (error occurs)
        3. failed -> pending (retry)
        4. pending -> running
        5. running -> completed
        """
        analysis_id = uuid.uuid4()
        
        mock_analysis = create_mock_analysis(
            analysis_id=analysis_id,
            ai_scan_status="pending",
        )
        mock_session = create_mock_session(mock_analysis)
        
        with patch('app.core.redis.publish_analysis_event'):
            service = AnalysisStateService(mock_session, publish_events=True)
            
            # Step 1: pending -> running
            service.start_ai_scan(analysis_id)
            assert mock_analysis.ai_scan_status == "running"
            
            # Step 2: running -> failed
            error_message = "LLM API timeout"
            service.fail_ai_scan(analysis_id, error_message)
            assert mock_analysis.ai_scan_status == "failed"
            assert mock_analysis.ai_scan_error == error_message
            
            # Step 3: failed -> pending (retry)
            service.mark_ai_scan_pending(analysis_id)
            assert mock_analysis.ai_scan_status == "pending"
            
            # Step 4-5: pending -> running -> completed
            service.start_ai_scan(analysis_id)
            assert mock_analysis.ai_scan_status == "running"
            
            service.complete_ai_scan(analysis_id, {"issues": []})
            assert mock_analysis.ai_scan_status == "completed"

    def test_ai_scan_progress_updates_during_running(self):
        """
        Test that progress updates work correctly during 'running' state.
        
        **Validates: Requirements 4.3**
        
        Property: Progress updates SHALL only be allowed when status is 'running'.
        """
        analysis_id = uuid.uuid4()
        
        mock_analysis = create_mock_analysis(
            analysis_id=analysis_id,
            ai_scan_status="running",
            ai_scan_progress=0,
        )
        mock_session = create_mock_session(mock_analysis)
        
        with patch('app.core.redis.publish_analysis_event'):
            service = AnalysisStateService(mock_session, publish_events=True)
            
            # Progress updates should succeed
            service.update_ai_scan_progress(analysis_id, 25, "cloning", "Cloning repository...")
            assert mock_analysis.ai_scan_progress == 25
            assert mock_analysis.ai_scan_stage == "cloning"
            
            service.update_ai_scan_progress(analysis_id, 50, "scanning", "Running AI scan...")
            assert mock_analysis.ai_scan_progress == 50
            assert mock_analysis.ai_scan_stage == "scanning"
            
            service.update_ai_scan_progress(analysis_id, 90, "merging", "Merging issues...")
            assert mock_analysis.ai_scan_progress == 90
            assert mock_analysis.ai_scan_stage == "merging"

    def test_failure_isolation_preserves_other_states(self):
        """
        Test that AI scan failure doesn't affect other analysis states.
        
        **Validates: Requirements 5.2**
        
        Property: For any AI scan failure, the analysis_status, embeddings_status,
        semantic_cache_status, and their associated data SHALL remain unchanged.
        """
        analysis_id = uuid.uuid4()
        
        # Create analysis with all phases completed except AI scan
        mock_analysis = create_mock_analysis(
            analysis_id=analysis_id,
            status="completed",
            embeddings_status="completed",
            embeddings_progress=100,
            vectors_count=150,
            semantic_cache_status="completed",
            semantic_cache={"clusters": [{"id": 1}], "architecture_health": {"overall_score": 85}},
            ai_scan_status="running",
            ai_scan_progress=50,
        )
        mock_session = create_mock_session(mock_analysis)
        
        # Store original values
        original_status = mock_analysis.status
        original_embeddings_status = mock_analysis.embeddings_status
        original_vectors_count = mock_analysis.vectors_count
        original_semantic_cache_status = mock_analysis.semantic_cache_status
        original_semantic_cache = mock_analysis.semantic_cache
        
        with patch('app.core.redis.publish_analysis_event'):
            service = AnalysisStateService(mock_session, publish_events=True)
            
            # Fail AI scan
            service.fail_ai_scan(analysis_id, "Cost limit exceeded")
            
            # Verify AI scan is failed
            assert mock_analysis.ai_scan_status == "failed"
            
            # Verify other states are unchanged (failure isolation)
            assert mock_analysis.status == original_status
            assert mock_analysis.embeddings_status == original_embeddings_status
            assert mock_analysis.vectors_count == original_vectors_count
            assert mock_analysis.semantic_cache_status == original_semantic_cache_status
            assert mock_analysis.semantic_cache == original_semantic_cache


# =============================================================================
# Integration Tests: Full Status API (Task 19.2)
# =============================================================================


class TestFullStatusAPIIntegration:
    """
    Integration tests for the Full Status API.
    
    Tests: All phases return correct state from PostgreSQL
    Verifies progress calculation at each phase.
    
    **Feature: ai-scan-progress-fix**
    **Validates: Requirements 2.3, 6.1**
    """

    def test_full_status_at_analysis_phase(self):
        """
        Test Full Status API response during analysis phase.
        
        **Validates: Requirements 2.3, 6.1**
        """
        # Analysis running: 0-30% progress
        progress = compute_overall_progress("running", "none", 0, "none", "none", 0)
        stage = compute_overall_stage("running", "none", None, "none", "none", None)
        is_complete = compute_is_complete("running", "none", "none", "none")
        
        assert progress == 15  # Mid-point of analysis phase
        assert "Analyzing" in stage or "running" in stage.lower()
        assert is_complete is False

    def test_full_status_at_embeddings_phase(self):
        """
        Test Full Status API response during embeddings phase.
        
        **Validates: Requirements 2.3, 6.1**
        """
        # Embeddings running at 50%: 30 + 50*0.3 = 45%
        progress = compute_overall_progress("completed", "running", 50, "none", "none", 0)
        stage = compute_overall_stage("completed", "running", "embedding", "none", "none", None)
        is_complete = compute_is_complete("completed", "running", "none", "none")
        
        assert progress == 45
        assert "embedding" in stage.lower() or "Generating" in stage
        assert is_complete is False

    def test_full_status_at_semantic_cache_phase(self):
        """
        Test Full Status API response during semantic cache phase.
        
        **Validates: Requirements 2.3, 6.1**
        """
        # Semantic cache computing: 60-80% progress
        progress = compute_overall_progress("completed", "completed", 100, "computing", "none", 0)
        stage = compute_overall_stage("completed", "completed", "completed", "computing", "none", None)
        is_complete = compute_is_complete("completed", "completed", "computing", "none")
        
        assert progress == 70  # Mid-point of semantic cache phase
        assert "semantic" in stage.lower() or "Computing" in stage
        assert is_complete is False

    def test_full_status_at_ai_scan_phase(self):
        """
        Test Full Status API response during AI scan phase.
        
        **Validates: Requirements 2.3, 6.1**
        """
        # AI scan running at 50%: 80 + 50*0.2 = 90%
        progress = compute_overall_progress("completed", "completed", 100, "completed", "running", 50)
        stage = compute_overall_stage("completed", "completed", "completed", "completed", "running", "scanning")
        is_complete = compute_is_complete("completed", "completed", "completed", "running")
        
        assert progress == 90
        assert "scanning" in stage.lower() or "AI" in stage
        assert is_complete is False

    def test_full_status_all_phases_completed(self):
        """
        Test Full Status API response when all phases are completed.
        
        **Validates: Requirements 2.3, 6.1**
        """
        progress = compute_overall_progress("completed", "completed", 100, "completed", "completed", 100)
        stage = compute_overall_stage("completed", "completed", "completed", "completed", "completed", "completed")
        is_complete = compute_is_complete("completed", "completed", "completed", "completed")
        
        assert progress == 100
        assert "complete" in stage.lower()
        assert is_complete is True

    def test_full_status_with_ai_scan_skipped(self):
        """
        Test Full Status API response when AI scan is skipped.
        
        **Validates: Requirements 2.3, 5.1, 6.1**
        """
        progress = compute_overall_progress("completed", "completed", 100, "completed", "skipped", 0)
        stage = compute_overall_stage("completed", "completed", "completed", "completed", "skipped", "skipped")
        is_complete = compute_is_complete("completed", "completed", "completed", "skipped")
        
        assert progress == 100  # Skipped counts as complete
        assert is_complete is True

    def test_full_status_with_ai_scan_failed(self):
        """
        Test Full Status API response when AI scan failed.
        
        **Validates: Requirements 2.3, 5.2, 6.1**
        """
        progress = compute_overall_progress("completed", "completed", 100, "completed", "failed", 0)
        stage = compute_overall_stage("completed", "completed", "completed", "completed", "failed", "error")
        is_complete = compute_is_complete("completed", "completed", "completed", "failed")
        
        assert progress == 80  # Stuck at AI scan phase start
        assert "failed" in stage.lower() or "error" in stage.lower()
        assert is_complete is False

    @given(
        embeddings_progress=st.integers(min_value=0, max_value=100),
        ai_scan_progress=st.integers(min_value=0, max_value=100),
    )
    @settings(max_examples=100)
    def test_progress_calculation_is_monotonic_within_phases(
        self,
        embeddings_progress: int,
        ai_scan_progress: int,
    ):
        """
        Test that progress calculation is monotonic within each phase.
        
        **Validates: Requirements 6.1**
        
        Property: For any phase, higher internal progress should result in
        higher overall progress.
        """
        # Test embeddings phase monotonicity
        progress_low = compute_overall_progress("completed", "running", 0, "none", "none", 0)
        progress_mid = compute_overall_progress("completed", "running", embeddings_progress, "none", "none", 0)
        progress_high = compute_overall_progress("completed", "running", 100, "none", "none", 0)
        
        assert progress_low <= progress_mid <= progress_high
        
        # Test AI scan phase monotonicity
        progress_ai_low = compute_overall_progress("completed", "completed", 100, "completed", "running", 0)
        progress_ai_mid = compute_overall_progress("completed", "completed", 100, "completed", "running", ai_scan_progress)
        progress_ai_high = compute_overall_progress("completed", "completed", 100, "completed", "running", 100)
        
        assert progress_ai_low <= progress_ai_mid <= progress_ai_high

    @given(
        analysis_status=st.sampled_from(["pending", "running", "completed", "failed"]),
        embeddings_status=st.sampled_from(["none", "pending", "running", "completed", "failed"]),
        embeddings_progress=st.integers(min_value=0, max_value=100),
        semantic_cache_status=st.sampled_from(["none", "pending", "computing", "completed", "failed"]),
        ai_scan_status=st.sampled_from(["none", "pending", "running", "completed", "failed", "skipped"]),
        ai_scan_progress=st.integers(min_value=0, max_value=100),
    )
    @settings(max_examples=100)
    def test_is_complete_only_when_all_phases_done(
        self,
        analysis_status: str,
        embeddings_status: str,
        embeddings_progress: int,
        semantic_cache_status: str,
        ai_scan_status: str,
        ai_scan_progress: int,
    ):
        """
        Test that is_complete is True only when all phases are done.
        
        **Validates: Requirements 6.1**
        
        Property: is_complete SHALL be True only when:
        - analysis_status = "completed"
        - embeddings_status = "completed"
        - semantic_cache_status = "completed"
        - ai_scan_status in ("completed", "skipped")
        """
        is_complete = compute_is_complete(
            analysis_status,
            embeddings_status,
            semantic_cache_status,
            ai_scan_status,
        )
        
        if is_complete:
            assert analysis_status == "completed", "Analysis must be completed"
            assert embeddings_status == "completed", "Embeddings must be completed"
            assert semantic_cache_status == "completed", "Semantic cache must be completed"
            assert ai_scan_status in ("completed", "skipped"), "AI scan must be completed or skipped"


# =============================================================================
# Property-Based Tests for AI Scan State Transitions
# =============================================================================


class TestAIScanStateTransitionProperties:
    """
    Property-based tests for AI scan state transitions.
    
    **Feature: ai-scan-progress-fix**
    **Validates: Requirements 1.2, 1.3, 1.4**
    """

    @given(
        current_status=st.sampled_from(list(AI_SCAN_TRANSITIONS.keys())),
        new_status=st.sampled_from(["none", "pending", "running", "completed", "failed", "skipped"]),
    )
    @settings(max_examples=100)
    def test_transition_validation_matches_transition_map(
        self,
        current_status: str,
        new_status: str,
    ):
        """
        Test that is_valid_ai_scan_transition matches AI_SCAN_TRANSITIONS map.
        
        **Validates: Requirements 1.2, 1.3, 1.4**
        
        Property: is_valid_ai_scan_transition(current, new) SHALL return True
        if and only if new is in AI_SCAN_TRANSITIONS[current].
        """
        expected = new_status in AI_SCAN_TRANSITIONS.get(current_status, set())
        actual = is_valid_ai_scan_transition(current_status, new_status)
        
        assert actual == expected, (
            f"Transition {current_status} -> {new_status}: "
            f"expected {expected}, got {actual}"
        )

    def test_terminal_states_have_no_transitions(self):
        """
        Test that terminal states have no valid transitions.
        
        **Validates: Requirements 1.4**
        
        Property: 'completed' and 'skipped' are terminal states with no
        valid outgoing transitions.
        """
        terminal_states = ["completed", "skipped"]
        all_statuses = ["none", "pending", "running", "completed", "failed", "skipped"]
        
        for terminal in terminal_states:
            for target in all_statuses:
                assert not is_valid_ai_scan_transition(terminal, target), (
                    f"Terminal state '{terminal}' should not allow transition to '{target}'"
                )

    def test_failed_state_allows_retry(self):
        """
        Test that failed state allows retry via pending.
        
        **Validates: Requirements 5.3**
        
        Property: 'failed' state SHALL allow transition to 'pending' for retry.
        """
        assert is_valid_ai_scan_transition("failed", "pending"), (
            "Failed state should allow transition to pending for retry"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
