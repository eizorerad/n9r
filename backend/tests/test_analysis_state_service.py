"""Property-based tests for AnalysisStateService.

Uses Hypothesis for property-based testing to verify correctness properties
defined in the design document for the progress-tracking-refactor feature.

Tests cover:
- Property 3: Timestamp Update on State Change
- Property 4: Valid State Transitions
- Property 5: Progress Value Bounds
- Property 6: Completion Triggers Semantic Cache Pending
"""

import uuid
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.services.analysis_state import (
    EMBEDDINGS_TRANSITIONS,
    SEMANTIC_CACHE_TRANSITIONS,
    VALID_EMBEDDINGS_STATUS,
    VALID_SEMANTIC_CACHE_STATUS,
    AnalysisStateService,
    InvalidProgressValueError,
    is_valid_embeddings_transition,
    is_valid_semantic_cache_transition,
    validate_progress,
)

# =============================================================================
# Custom Strategies
# =============================================================================


def valid_embeddings_status() -> st.SearchStrategy[str]:
    """Generate valid embeddings_status values."""
    return st.sampled_from(list(VALID_EMBEDDINGS_STATUS))


def valid_semantic_cache_status() -> st.SearchStrategy[str]:
    """Generate valid semantic_cache_status values."""
    return st.sampled_from(list(VALID_SEMANTIC_CACHE_STATUS))


def valid_progress() -> st.SearchStrategy[int]:
    """Generate valid progress values (0-100)."""
    return st.integers(min_value=0, max_value=100)


def invalid_progress() -> st.SearchStrategy[int]:
    """Generate invalid progress values (outside 0-100)."""
    return st.one_of(
        st.integers(max_value=-1),
        st.integers(min_value=101),
    )


def embeddings_transition_pair() -> st.SearchStrategy[tuple[str, str]]:
    """Generate pairs of (current_status, new_status) for embeddings."""
    return st.tuples(valid_embeddings_status(), valid_embeddings_status())


def semantic_cache_transition_pair() -> st.SearchStrategy[tuple[str, str]]:
    """Generate pairs of (current_status, new_status) for semantic cache."""
    return st.tuples(valid_semantic_cache_status(), valid_semantic_cache_status())


# =============================================================================
# Property 4: Valid State Transitions
# =============================================================================


class TestValidStateTransitions:
    """
    Property tests for valid state transitions.

    **Feature: progress-tracking-refactor, Property 4: Valid State Transitions**
    **Validates: Requirements 2.1, 2.3, 2.4, 2.5, 3.1, 3.2, 3.3, 5.1, 5.2**
    """

    @given(embeddings_transition_pair())
    @settings(max_examples=100)
    def test_embeddings_transition_validation_consistency(
        self, transition: tuple[str, str]
    ):
        """
        **Feature: progress-tracking-refactor, Property 4: Valid State Transitions**
        **Validates: Requirements 2.1, 2.3, 2.4, 5.1, 5.2**

        Property: For any embeddings_status transition, the validation function
        SHALL return True if and only if the new status is in the allowed
        transitions set for the current status.
        """
        current_status, new_status = transition

        # Get expected result from transition definition
        allowed_transitions = EMBEDDINGS_TRANSITIONS.get(current_status, set())
        expected_valid = new_status in allowed_transitions

        # Validate using the function
        actual_valid = is_valid_embeddings_transition(current_status, new_status)

        assert actual_valid == expected_valid, (
            f"Transition validation mismatch for '{current_status}' -> '{new_status}'\n"
            f"Expected valid: {expected_valid}, Got: {actual_valid}\n"
            f"Allowed transitions from '{current_status}': {allowed_transitions}"
        )

    @given(semantic_cache_transition_pair())
    @settings(max_examples=100)
    def test_semantic_cache_transition_validation_consistency(
        self, transition: tuple[str, str]
    ):
        """
        **Feature: progress-tracking-refactor, Property 4: Valid State Transitions**
        **Validates: Requirements 3.1, 3.2, 3.3, 5.1, 5.2**

        Property: For any semantic_cache_status transition, the validation function
        SHALL return True if and only if the new status is in the allowed
        transitions set for the current status.
        """
        current_status, new_status = transition

        # Get expected result from transition definition
        allowed_transitions = SEMANTIC_CACHE_TRANSITIONS.get(current_status, set())
        expected_valid = new_status in allowed_transitions

        # Validate using the function
        actual_valid = is_valid_semantic_cache_transition(current_status, new_status)

        assert actual_valid == expected_valid, (
            f"Transition validation mismatch for '{current_status}' -> '{new_status}'\n"
            f"Expected valid: {expected_valid}, Got: {actual_valid}\n"
            f"Allowed transitions from '{current_status}': {allowed_transitions}"
        )

    @given(valid_embeddings_status())
    @settings(max_examples=100)
    def test_completed_embeddings_is_terminal(self, status: str):
        """
        **Feature: progress-tracking-refactor, Property 4: Valid State Transitions**
        **Validates: Requirements 5.2**

        Property: When embeddings_status is 'completed', no transitions SHALL be
        allowed (terminal state).
        """
        # Check that 'completed' has no allowed transitions
        allowed = EMBEDDINGS_TRANSITIONS.get("completed", set())
        assert len(allowed) == 0, (
            f"'completed' should be terminal state with no transitions, "
            f"but has: {allowed}"
        )

        # Verify no transition from 'completed' to any status is valid
        is_valid = is_valid_embeddings_transition("completed", status)
        assert not is_valid, (
            f"Transition from 'completed' to '{status}' should be invalid"
        )

    @given(valid_semantic_cache_status())
    @settings(max_examples=100)
    def test_completed_semantic_cache_is_terminal(self, status: str):
        """
        **Feature: progress-tracking-refactor, Property 4: Valid State Transitions**
        **Validates: Requirements 5.2**

        Property: When semantic_cache_status is 'completed', no transitions SHALL be
        allowed (terminal state).
        """
        # Check that 'completed' has no allowed transitions
        allowed = SEMANTIC_CACHE_TRANSITIONS.get("completed", set())
        assert len(allowed) == 0, (
            f"'completed' should be terminal state with no transitions, "
            f"but has: {allowed}"
        )

        # Verify no transition from 'completed' to any status is valid
        is_valid = is_valid_semantic_cache_transition("completed", status)
        assert not is_valid, (
            f"Transition from 'completed' to '{status}' should be invalid"
        )

    def test_failed_can_retry_to_pending(self):
        """
        **Feature: progress-tracking-refactor, Property 4: Valid State Transitions**
        **Validates: Requirements 5.1**

        Property: When status is 'failed', transition to 'pending' SHALL be
        allowed (retry mechanism).
        """
        # Embeddings
        assert is_valid_embeddings_transition("failed", "pending"), (
            "Embeddings: 'failed' -> 'pending' should be valid for retry"
        )

        # Semantic cache
        assert is_valid_semantic_cache_transition("failed", "pending"), (
            "Semantic cache: 'failed' -> 'pending' should be valid for retry"
        )


# =============================================================================
# Property 5: Progress Value Bounds
# =============================================================================


class TestProgressValueBounds:
    """
    Property tests for progress value bounds.

    **Feature: progress-tracking-refactor, Property 5: Progress Value Bounds**
    **Validates: Requirements 2.2, 5.3, 6.3**
    """

    @given(valid_progress())
    @settings(max_examples=100)
    def test_valid_progress_accepted(self, progress: int):
        """
        **Feature: progress-tracking-refactor, Property 5: Progress Value Bounds**
        **Validates: Requirements 2.2, 5.3, 6.3**

        Property: For any progress value between 0 and 100 inclusive,
        the validation SHALL accept the value without raising an exception.
        """
        # Should not raise
        validate_progress(progress)

    @given(invalid_progress())
    @settings(max_examples=100)
    def test_invalid_progress_rejected(self, progress: int):
        """
        **Feature: progress-tracking-refactor, Property 5: Progress Value Bounds**
        **Validates: Requirements 2.2, 5.3, 6.3**

        Property: For any progress value outside 0-100,
        the validation SHALL reject the value with InvalidProgressValueError.
        """
        with pytest.raises(InvalidProgressValueError) as exc_info:
            validate_progress(progress)

        assert exc_info.value.progress == progress, (
            f"Exception should contain the invalid progress value {progress}"
        )

    @given(st.integers())
    @settings(max_examples=200)
    def test_progress_validation_boundary(self, progress: int):
        """
        **Feature: progress-tracking-refactor, Property 5: Progress Value Bounds**
        **Validates: Requirements 2.2, 5.3, 6.3**

        Property: For any integer, the validation SHALL accept if and only if
        the value is between 0 and 100 inclusive.
        """
        is_valid = 0 <= progress <= 100

        if is_valid:
            # Should not raise
            validate_progress(progress)
        else:
            # Should raise
            with pytest.raises(InvalidProgressValueError):
                validate_progress(progress)


# =============================================================================
# Property 3: Timestamp Update on State Change (with mock)
# =============================================================================


class TestTimestampUpdateOnStateChange:
    """
    Property tests for timestamp updates on state changes.

    **Feature: progress-tracking-refactor, Property 3: Timestamp Update on State Change**
    **Validates: Requirements 1.4, 2.2**
    """

    @given(
        initial_status=st.sampled_from(["none", "pending", "running", "failed"]),
        progress=valid_progress(),
    )
    @settings(max_examples=100)
    def test_timestamp_updated_on_embeddings_status_change(
        self, initial_status: str, progress: int
    ):
        """
        **Feature: progress-tracking-refactor, Property 3: Timestamp Update on State Change**
        **Validates: Requirements 1.4, 2.2**

        Property: For any state update to embeddings_status, the state_updated_at
        timestamp SHALL be updated to a value greater than or equal to the
        previous timestamp.
        """
        # Create mock analysis
        analysis_id = uuid.uuid4()
        initial_timestamp = datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC)

        mock_analysis = MagicMock()
        mock_analysis.id = analysis_id
        mock_analysis.embeddings_status = initial_status
        mock_analysis.embeddings_progress = 0
        mock_analysis.embeddings_stage = None
        mock_analysis.embeddings_message = None
        mock_analysis.embeddings_error = None
        mock_analysis.vectors_count = 0
        mock_analysis.state_updated_at = initial_timestamp

        # Create mock session
        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_analysis
        mock_session.execute.return_value = mock_result

        # Create service with events disabled
        service = AnalysisStateService(mock_session, publish_events=False)

        # Determine valid next status
        allowed = EMBEDDINGS_TRANSITIONS.get(initial_status, set())
        if not allowed:
            return  # Skip if no valid transitions

        new_status = list(allowed)[0]

        # Perform update
        service.update_embeddings_status(
            analysis_id=analysis_id,
            status=new_status,
            progress=progress,
        )

        # Verify timestamp was updated
        assert mock_analysis.state_updated_at >= initial_timestamp, (
            f"state_updated_at should be >= initial timestamp\n"
            f"Initial: {initial_timestamp}\n"
            f"Updated: {mock_analysis.state_updated_at}"
        )

    @given(
        initial_status=st.sampled_from(["none", "pending", "computing", "failed"]),
    )
    @settings(max_examples=100)
    def test_timestamp_updated_on_semantic_cache_status_change(
        self, initial_status: str
    ):
        """
        **Feature: progress-tracking-refactor, Property 3: Timestamp Update on State Change**
        **Validates: Requirements 1.4**

        Property: For any state update to semantic_cache_status, the state_updated_at
        timestamp SHALL be updated to a value greater than or equal to the
        previous timestamp.
        """
        # Create mock analysis
        analysis_id = uuid.uuid4()
        initial_timestamp = datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC)

        mock_analysis = MagicMock()
        mock_analysis.id = analysis_id
        mock_analysis.semantic_cache_status = initial_status
        mock_analysis.semantic_cache = None
        mock_analysis.state_updated_at = initial_timestamp

        # Create mock session
        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_analysis
        mock_session.execute.return_value = mock_result

        # Create service with events disabled
        service = AnalysisStateService(mock_session, publish_events=False)

        # Determine valid next status
        allowed = SEMANTIC_CACHE_TRANSITIONS.get(initial_status, set())
        if not allowed:
            return  # Skip if no valid transitions

        new_status = list(allowed)[0]

        # Perform update
        service.update_semantic_cache_status(
            analysis_id=analysis_id,
            status=new_status,
        )

        # Verify timestamp was updated
        assert mock_analysis.state_updated_at >= initial_timestamp, (
            f"state_updated_at should be >= initial timestamp\n"
            f"Initial: {initial_timestamp}\n"
            f"Updated: {mock_analysis.state_updated_at}"
        )


# =============================================================================
# Property 6: Completion Triggers Semantic Cache Pending
# =============================================================================


class TestCompletionTriggersSemanticCachePending:
    """
    Property tests for completion triggering semantic cache pending.

    **Feature: progress-tracking-refactor, Property 6: Completion Triggers Semantic Cache Pending**
    **Validates: Requirements 2.5**
    """

    @given(vectors_count=st.integers(min_value=0, max_value=100000))
    @settings(max_examples=100)
    def test_embeddings_completion_triggers_semantic_cache_pending(
        self, vectors_count: int
    ):
        """
        **Feature: progress-tracking-refactor, Property 6: Completion Triggers Semantic Cache Pending**
        **Validates: Requirements 2.5**

        Property: For any analysis where embeddings_status transitions to 'completed',
        the semantic_cache_status SHALL automatically transition to 'pending'
        (if currently 'none').
        """
        # Create mock analysis in 'running' state with semantic_cache_status='none'
        analysis_id = uuid.uuid4()
        initial_timestamp = datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC)

        mock_analysis = MagicMock()
        mock_analysis.id = analysis_id
        mock_analysis.embeddings_status = "running"
        mock_analysis.embeddings_progress = 50
        mock_analysis.embeddings_stage = "embedding"
        mock_analysis.embeddings_message = "Processing..."
        mock_analysis.embeddings_error = None
        mock_analysis.embeddings_started_at = initial_timestamp
        mock_analysis.embeddings_completed_at = None
        mock_analysis.vectors_count = 0
        mock_analysis.semantic_cache_status = "none"
        mock_analysis.state_updated_at = initial_timestamp

        # Create mock session
        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_analysis
        mock_session.execute.return_value = mock_result

        # Create service with events disabled
        service = AnalysisStateService(mock_session, publish_events=False)

        # Complete embeddings
        service.complete_embeddings(analysis_id, vectors_count)

        # Verify semantic_cache_status was set to 'pending'
        assert mock_analysis.semantic_cache_status == "pending", (
            f"semantic_cache_status should be 'pending' after embeddings completion, "
            f"got: '{mock_analysis.semantic_cache_status}'"
        )

        # Verify embeddings fields were updated correctly
        assert mock_analysis.embeddings_status == "completed"
        assert mock_analysis.embeddings_progress == 100
        assert mock_analysis.vectors_count == vectors_count

    @given(
        initial_semantic_status=st.sampled_from(["pending", "computing", "completed", "failed"]),
        vectors_count=st.integers(min_value=0, max_value=100000),
    )
    @settings(max_examples=100)
    def test_embeddings_completion_preserves_non_none_semantic_status(
        self, initial_semantic_status: str, vectors_count: int
    ):
        """
        **Feature: progress-tracking-refactor, Property 6: Completion Triggers Semantic Cache Pending**
        **Validates: Requirements 2.5**

        Property: When embeddings complete and semantic_cache_status is NOT 'none',
        the semantic_cache_status SHALL NOT be changed.
        """
        # Create mock analysis in 'running' state with non-'none' semantic_cache_status
        analysis_id = uuid.uuid4()
        initial_timestamp = datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC)

        mock_analysis = MagicMock()
        mock_analysis.id = analysis_id
        mock_analysis.embeddings_status = "running"
        mock_analysis.embeddings_progress = 50
        mock_analysis.embeddings_stage = "embedding"
        mock_analysis.embeddings_message = "Processing..."
        mock_analysis.embeddings_error = None
        mock_analysis.embeddings_started_at = initial_timestamp
        mock_analysis.embeddings_completed_at = None
        mock_analysis.vectors_count = 0
        mock_analysis.semantic_cache_status = initial_semantic_status
        mock_analysis.state_updated_at = initial_timestamp

        # Create mock session
        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_analysis
        mock_session.execute.return_value = mock_result

        # Create service with events disabled
        service = AnalysisStateService(mock_session, publish_events=False)

        # Complete embeddings
        service.complete_embeddings(analysis_id, vectors_count)

        # Verify semantic_cache_status was NOT changed
        assert mock_analysis.semantic_cache_status == initial_semantic_status, (
            f"semantic_cache_status should remain '{initial_semantic_status}' "
            f"when not 'none', got: '{mock_analysis.semantic_cache_status}'"
        )


# =============================================================================
# Property 9: Event Publishing on State Change
# =============================================================================


class TestEventPublishingOnStateChange:
    """
    Property tests for event publishing on state changes.

    **Feature: progress-tracking-refactor, Property 9: Event Publishing on State Change**
    **Validates: Requirements 7.1, 7.4**
    """

    @given(
        initial_status=st.sampled_from(["none", "pending", "running", "failed"]),
        progress=valid_progress(),
        stage=st.text(min_size=1, max_size=20, alphabet=st.characters(whitelist_categories=('L', 'N'))),
    )
    @settings(max_examples=100)
    def test_event_published_on_embeddings_status_change(
        self, initial_status: str, progress: int, stage: str
    ):
        """
        **Feature: progress-tracking-refactor, Property 9: Event Publishing on State Change**
        **Validates: Requirements 7.1, 7.4**

        Property: For any state update through AnalysisStateService, a Redis pub/sub
        event SHALL be published containing analysis_id, event_type, and the
        updated status data.
        """
        # Determine valid next status
        allowed = EMBEDDINGS_TRANSITIONS.get(initial_status, set())
        if not allowed:
            return  # Skip if no valid transitions

        new_status = list(allowed)[0]

        # Create mock analysis
        analysis_id = uuid.uuid4()
        initial_timestamp = datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC)

        mock_analysis = MagicMock()
        mock_analysis.id = analysis_id
        mock_analysis.embeddings_status = initial_status
        mock_analysis.embeddings_progress = 0
        mock_analysis.embeddings_stage = None
        mock_analysis.embeddings_message = None
        mock_analysis.embeddings_error = None
        mock_analysis.vectors_count = 0
        mock_analysis.state_updated_at = initial_timestamp

        # Create mock session
        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_analysis
        mock_session.execute.return_value = mock_result

        # Create service with events ENABLED
        service = AnalysisStateService(mock_session, publish_events=True)

        # Mock the publish_analysis_event function at the import location
        with patch('app.core.redis.publish_analysis_event') as mock_publish:
            mock_publish.return_value = True

            # Perform update
            service.update_embeddings_status(
                analysis_id=analysis_id,
                status=new_status,
                progress=progress,
                stage=stage,
            )

            # Verify event was published
            mock_publish.assert_called_once()

            # Verify call arguments
            call_args = mock_publish.call_args
            assert call_args is not None, "publish_analysis_event should have been called"

            # Check analysis_id (Requirements 7.4)
            assert call_args.kwargs.get('analysis_id') == str(analysis_id), (
                f"Event should contain analysis_id={analysis_id}"
            )

            # Check event_type (Requirements 7.4)
            assert call_args.kwargs.get('event_type') == "embeddings_status_changed", (
                "Event type should be 'embeddings_status_changed'"
            )

            # Check status_data contains relevant fields (Requirements 7.4)
            status_data = call_args.kwargs.get('status_data', {})
            assert 'embeddings_status' in status_data, (
                "status_data should contain embeddings_status"
            )
            assert status_data['embeddings_status'] == new_status, (
                f"embeddings_status should be '{new_status}'"
            )

    @given(
        initial_status=st.sampled_from(["none", "pending", "computing", "failed"]),
    )
    @settings(max_examples=100)
    def test_event_published_on_semantic_cache_status_change(
        self, initial_status: str
    ):
        """
        **Feature: progress-tracking-refactor, Property 9: Event Publishing on State Change**
        **Validates: Requirements 7.1, 7.4**

        Property: For any semantic_cache_status update through AnalysisStateService,
        a Redis pub/sub event SHALL be published containing analysis_id, event_type,
        and the updated status data.
        """
        # Determine valid next status
        allowed = SEMANTIC_CACHE_TRANSITIONS.get(initial_status, set())
        if not allowed:
            return  # Skip if no valid transitions

        new_status = list(allowed)[0]

        # Create mock analysis
        analysis_id = uuid.uuid4()
        initial_timestamp = datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC)

        mock_analysis = MagicMock()
        mock_analysis.id = analysis_id
        mock_analysis.semantic_cache_status = initial_status
        mock_analysis.semantic_cache = None
        mock_analysis.state_updated_at = initial_timestamp

        # Create mock session
        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_analysis
        mock_session.execute.return_value = mock_result

        # Create service with events ENABLED
        service = AnalysisStateService(mock_session, publish_events=True)

        # Mock the publish_analysis_event function at the import location
        with patch('app.core.redis.publish_analysis_event') as mock_publish:
            mock_publish.return_value = True

            # Perform update
            service.update_semantic_cache_status(
                analysis_id=analysis_id,
                status=new_status,
            )

            # Verify event was published
            mock_publish.assert_called_once()

            # Verify call arguments
            call_args = mock_publish.call_args
            assert call_args is not None, "publish_analysis_event should have been called"

            # Check analysis_id (Requirements 7.4)
            assert call_args.kwargs.get('analysis_id') == str(analysis_id), (
                f"Event should contain analysis_id={analysis_id}"
            )

            # Check event_type (Requirements 7.4)
            assert call_args.kwargs.get('event_type') == "semantic_cache_status_changed", (
                "Event type should be 'semantic_cache_status_changed'"
            )

            # Check status_data contains relevant fields (Requirements 7.4)
            status_data = call_args.kwargs.get('status_data', {})
            assert 'semantic_cache_status' in status_data, (
                "status_data should contain semantic_cache_status"
            )
            assert status_data['semantic_cache_status'] == new_status, (
                f"semantic_cache_status should be '{new_status}'"
            )

    @given(
        progress=valid_progress(),
        stage=st.text(min_size=1, max_size=20, alphabet=st.characters(whitelist_categories=('L', 'N'))),
    )
    @settings(max_examples=100)
    def test_event_published_on_progress_update(
        self, progress: int, stage: str
    ):
        """
        **Feature: progress-tracking-refactor, Property 9: Event Publishing on State Change**
        **Validates: Requirements 7.1, 7.4**

        Property: For any embeddings progress update through AnalysisStateService,
        a Redis pub/sub event SHALL be published containing analysis_id, event_type,
        and the updated progress data.
        """
        # Create mock analysis in 'running' state
        analysis_id = uuid.uuid4()
        initial_timestamp = datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC)

        mock_analysis = MagicMock()
        mock_analysis.id = analysis_id
        mock_analysis.embeddings_status = "running"
        mock_analysis.embeddings_progress = 0
        mock_analysis.embeddings_stage = "initializing"
        mock_analysis.embeddings_message = None
        mock_analysis.state_updated_at = initial_timestamp

        # Create mock session
        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_analysis
        mock_session.execute.return_value = mock_result

        # Create service with events ENABLED
        service = AnalysisStateService(mock_session, publish_events=True)

        # Mock the publish_analysis_event function at the import location
        with patch('app.core.redis.publish_analysis_event') as mock_publish:
            mock_publish.return_value = True

            # Perform progress update
            service.update_embeddings_progress(
                analysis_id=analysis_id,
                progress=progress,
                stage=stage,
            )

            # Verify event was published
            mock_publish.assert_called_once()

            # Verify call arguments
            call_args = mock_publish.call_args
            assert call_args is not None, "publish_analysis_event should have been called"

            # Check analysis_id (Requirements 7.4)
            assert call_args.kwargs.get('analysis_id') == str(analysis_id), (
                f"Event should contain analysis_id={analysis_id}"
            )

            # Check event_type (Requirements 7.4)
            assert call_args.kwargs.get('event_type') == "embeddings_progress_updated", (
                "Event type should be 'embeddings_progress_updated'"
            )

            # Check status_data contains progress (Requirements 7.4)
            status_data = call_args.kwargs.get('status_data', {})
            assert 'embeddings_progress' in status_data, (
                "status_data should contain embeddings_progress"
            )
            assert status_data['embeddings_progress'] == progress, (
                f"embeddings_progress should be {progress}"
            )

    def test_event_not_published_when_disabled(self):
        """
        **Feature: progress-tracking-refactor, Property 9: Event Publishing on State Change**
        **Validates: Requirements 7.1**

        Property: When publish_events=False, no events SHALL be published.
        """
        # Create mock analysis
        analysis_id = uuid.uuid4()
        initial_timestamp = datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC)

        mock_analysis = MagicMock()
        mock_analysis.id = analysis_id
        mock_analysis.embeddings_status = "none"
        mock_analysis.embeddings_progress = 0
        mock_analysis.embeddings_stage = None
        mock_analysis.embeddings_message = None
        mock_analysis.embeddings_error = None
        mock_analysis.vectors_count = 0
        mock_analysis.state_updated_at = initial_timestamp

        # Create mock session
        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_analysis
        mock_session.execute.return_value = mock_result

        # Create service with events DISABLED
        service = AnalysisStateService(mock_session, publish_events=False)

        # Mock the publish_analysis_event function at the import location
        with patch('app.core.redis.publish_analysis_event') as mock_publish:
            # Perform update
            service.update_embeddings_status(
                analysis_id=analysis_id,
                status="pending",
            )

            # Verify event was NOT published
            mock_publish.assert_not_called()

    def test_event_publishing_failure_is_non_blocking(self):
        """
        **Feature: progress-tracking-refactor, Property 9: Event Publishing on State Change**
        **Validates: Requirements 7.2**

        Property: When Redis pub/sub fails, the state update SHALL still succeed
        (non-blocking).
        """
        # Create mock analysis
        analysis_id = uuid.uuid4()
        initial_timestamp = datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC)

        mock_analysis = MagicMock()
        mock_analysis.id = analysis_id
        mock_analysis.embeddings_status = "none"
        mock_analysis.embeddings_progress = 0
        mock_analysis.embeddings_stage = None
        mock_analysis.embeddings_message = None
        mock_analysis.embeddings_error = None
        mock_analysis.vectors_count = 0
        mock_analysis.state_updated_at = initial_timestamp

        # Create mock session
        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_analysis
        mock_session.execute.return_value = mock_result

        # Create service with events ENABLED
        service = AnalysisStateService(mock_session, publish_events=True)

        # Mock the publish_analysis_event function to raise an exception
        with patch('app.core.redis.publish_analysis_event') as mock_publish:
            mock_publish.side_effect = Exception("Redis connection failed")

            # Perform update - should NOT raise despite Redis failure
            service.update_embeddings_status(
                analysis_id=analysis_id,
                status="pending",
            )

            # Verify state was still updated
            assert mock_analysis.embeddings_status == "pending", (
                "State should be updated even when event publishing fails"
            )

            # Verify session.commit was called
            mock_session.commit.assert_called()


# =============================================================================
# Property 7: Overall Progress Computation
# =============================================================================


class TestOverallProgressComputation:
    """
    Property tests for overall progress computation.

    **Feature: progress-tracking-refactor, Property 7: Overall Progress Computation**
    **Validates: Requirements 3.4, 4.2, 4.3**
    """

    @given(
        analysis_status=st.sampled_from(["pending", "running", "completed", "failed"]),
        embeddings_status=st.sampled_from(["none", "pending", "running", "completed", "failed"]),
        embeddings_progress=st.integers(min_value=0, max_value=100),
        semantic_cache_status=st.sampled_from(["none", "pending", "computing", "completed", "failed"]),
    )
    @settings(max_examples=200)
    def test_overall_progress_within_bounds(
        self,
        analysis_status: str,
        embeddings_status: str,
        embeddings_progress: int,
        semantic_cache_status: str,
    ):
        """
        **Feature: progress-tracking-refactor, Property 7: Overall Progress Computation**
        **Validates: Requirements 3.4, 4.2**

        Property: For any combination of analysis states, the computed overall_progress
        SHALL be between 0 and 100 inclusive.
        """
        from app.schemas.analysis import compute_overall_progress

        progress = compute_overall_progress(
            analysis_status=analysis_status,
            embeddings_status=embeddings_status,
            embeddings_progress=embeddings_progress,
            semantic_cache_status=semantic_cache_status,
        )

        assert 0 <= progress <= 100, (
            f"overall_progress should be between 0 and 100, got: {progress}\n"
            f"Inputs: analysis={analysis_status}, embeddings={embeddings_status}, "
            f"emb_progress={embeddings_progress}, semantic={semantic_cache_status}"
        )

    @given(embeddings_progress=st.integers(min_value=0, max_value=100))
    @settings(max_examples=100)
    def test_analysis_pending_returns_zero(self, embeddings_progress: int):
        """
        **Feature: progress-tracking-refactor, Property 7: Overall Progress Computation**
        **Validates: Requirements 3.4, 4.2**

        Property: When analysis_status is 'pending', overall_progress SHALL be 0.
        """
        from app.schemas.analysis import compute_overall_progress

        progress = compute_overall_progress(
            analysis_status="pending",
            embeddings_status="none",
            embeddings_progress=embeddings_progress,
            semantic_cache_status="none",
        )

        assert progress == 0, (
            f"overall_progress should be 0 when analysis is pending, got: {progress}"
        )

    @given(embeddings_progress=st.integers(min_value=0, max_value=100))
    @settings(max_examples=100)
    def test_analysis_running_returns_midpoint(self, embeddings_progress: int):
        """
        **Feature: progress-tracking-refactor, ai-scan-progress-fix, Property 7: Overall Progress Computation**
        **Validates: Requirements 3.4, 4.2, 6.1**

        Property: When analysis_status is 'running', overall_progress SHALL be 15
        (mid-point of analysis phase 0-30%).
        """
        from app.schemas.analysis import compute_overall_progress

        progress = compute_overall_progress(
            analysis_status="running",
            embeddings_status="none",
            embeddings_progress=embeddings_progress,
            semantic_cache_status="none",
            ai_scan_status="none",
            ai_scan_progress=0,
        )

        assert progress == 15, (
            f"overall_progress should be 15 when analysis is running, got: {progress}"
        )

    @given(embeddings_progress=st.integers(min_value=0, max_value=100))
    @settings(max_examples=100)
    def test_analysis_failed_returns_zero(self, embeddings_progress: int):
        """
        **Feature: progress-tracking-refactor, Property 7: Overall Progress Computation**
        **Validates: Requirements 3.4, 4.2**

        Property: When analysis_status is 'failed', overall_progress SHALL be 0.
        """
        from app.schemas.analysis import compute_overall_progress

        progress = compute_overall_progress(
            analysis_status="failed",
            embeddings_status="none",
            embeddings_progress=embeddings_progress,
            semantic_cache_status="none",
        )

        assert progress == 0, (
            f"overall_progress should be 0 when analysis failed, got: {progress}"
        )

    @given(embeddings_progress=st.integers(min_value=0, max_value=100))
    @settings(max_examples=100)
    def test_embeddings_running_scales_progress(self, embeddings_progress: int):
        """
        **Feature: progress-tracking-refactor, ai-scan-progress-fix, Property 7: Overall Progress Computation**
        **Validates: Requirements 3.4, 4.2, 6.1**

        Property: When embeddings_status is 'running', overall_progress SHALL scale
        embeddings_progress from (0-100) to (30-60).
        Formula: 30 + int(embeddings_progress * 0.3)
        """
        from app.schemas.analysis import compute_overall_progress

        progress = compute_overall_progress(
            analysis_status="completed",
            embeddings_status="running",
            embeddings_progress=embeddings_progress,
            semantic_cache_status="none",
            ai_scan_status="none",
            ai_scan_progress=0,
        )

        expected = 30 + int(embeddings_progress * 0.3)

        assert progress == expected, (
            f"overall_progress should be {expected} when embeddings running "
            f"with progress={embeddings_progress}, got: {progress}"
        )

    @given(
        embeddings_status=st.sampled_from(["none", "pending"]),
        embeddings_progress=st.integers(min_value=0, max_value=100),
    )
    @settings(max_examples=100)
    def test_embeddings_not_started_returns_30(
        self, embeddings_status: str, embeddings_progress: int
    ):
        """
        **Feature: progress-tracking-refactor, ai-scan-progress-fix, Property 7: Overall Progress Computation**
        **Validates: Requirements 3.4, 4.2, 6.1**

        Property: When analysis is completed and embeddings_status is 'none' or 'pending',
        overall_progress SHALL be 30 (start of embeddings phase).
        """
        from app.schemas.analysis import compute_overall_progress

        progress = compute_overall_progress(
            analysis_status="completed",
            embeddings_status=embeddings_status,
            embeddings_progress=embeddings_progress,
            semantic_cache_status="none",
            ai_scan_status="none",
            ai_scan_progress=0,
        )

        assert progress == 30, (
            f"overall_progress should be 30 when embeddings not started, got: {progress}"
        )

    @given(
        semantic_cache_status=st.sampled_from(["none", "pending"]),
    )
    @settings(max_examples=100)
    def test_semantic_cache_not_started_returns_60(self, semantic_cache_status: str):
        """
        **Feature: progress-tracking-refactor, ai-scan-progress-fix, Property 7: Overall Progress Computation**
        **Validates: Requirements 3.4, 4.2, 6.1**

        Property: When embeddings are completed and semantic_cache_status is 'none' or 'pending',
        overall_progress SHALL be 60 (start of semantic cache phase).
        """
        from app.schemas.analysis import compute_overall_progress

        progress = compute_overall_progress(
            analysis_status="completed",
            embeddings_status="completed",
            embeddings_progress=100,
            semantic_cache_status=semantic_cache_status,
            ai_scan_status="none",
            ai_scan_progress=0,
        )

        assert progress == 60, (
            f"overall_progress should be 60 when semantic cache not started, got: {progress}"
        )

    def test_semantic_cache_computing_returns_70(self):
        """
        **Feature: progress-tracking-refactor, ai-scan-progress-fix, Property 7: Overall Progress Computation**
        **Validates: Requirements 3.4, 4.2, 6.1**

        Property: When semantic_cache_status is 'computing', overall_progress SHALL be 70
        (mid-point of semantic cache phase 60-80%).
        """
        from app.schemas.analysis import compute_overall_progress

        progress = compute_overall_progress(
            analysis_status="completed",
            embeddings_status="completed",
            embeddings_progress=100,
            semantic_cache_status="computing",
            ai_scan_status="none",
            ai_scan_progress=0,
        )

        assert progress == 70, (
            f"overall_progress should be 70 when semantic cache computing, got: {progress}"
        )

    def test_all_complete_returns_100(self):
        """
        **Feature: progress-tracking-refactor, ai-scan-progress-fix, Property 7: Overall Progress Computation**
        **Validates: Requirements 3.4, 4.2, 6.1**

        Property: When all phases are completed (including AI scan), overall_progress SHALL be 100.
        """
        from app.schemas.analysis import compute_overall_progress

        progress = compute_overall_progress(
            analysis_status="completed",
            embeddings_status="completed",
            embeddings_progress=100,
            semantic_cache_status="completed",
            ai_scan_status="completed",
            ai_scan_progress=100,
        )

        assert progress == 100, (
            f"overall_progress should be 100 when all complete, got: {progress}"
        )

    @given(
        analysis_status=st.sampled_from(["pending", "running", "completed", "failed"]),
        embeddings_status=st.sampled_from(["none", "pending", "running", "completed", "failed"]),
        semantic_cache_status=st.sampled_from(["none", "pending", "computing", "completed", "failed"]),
        ai_scan_status=st.sampled_from(["none", "pending", "running", "completed", "failed", "skipped"]),
    )
    @settings(max_examples=200)
    def test_is_complete_only_when_all_completed(
        self,
        analysis_status: str,
        embeddings_status: str,
        semantic_cache_status: str,
        ai_scan_status: str,
    ):
        """
        **Feature: progress-tracking-refactor, ai-scan-progress-fix, Property 7: Overall Progress Computation**
        **Validates: Requirements 4.2, 4.3, 6.1**

        Property: is_complete SHALL be True if and only if all four phases
        (analysis, embeddings, semantic_cache, ai_scan) are 'completed' or ai_scan is 'skipped'.
        """
        from app.schemas.analysis import compute_is_complete

        is_complete = compute_is_complete(
            analysis_status=analysis_status,
            embeddings_status=embeddings_status,
            semantic_cache_status=semantic_cache_status,
            ai_scan_status=ai_scan_status,
        )

        expected = (
            analysis_status == "completed"
            and embeddings_status == "completed"
            and semantic_cache_status == "completed"
            and ai_scan_status in ("completed", "skipped")
        )

        assert is_complete == expected, (
            f"is_complete should be {expected}, got: {is_complete}\n"
            f"Inputs: analysis={analysis_status}, embeddings={embeddings_status}, "
            f"semantic={semantic_cache_status}, ai_scan={ai_scan_status}"
        )

    @given(
        analysis_status=st.sampled_from(["pending", "running", "completed", "failed"]),
        embeddings_status=st.sampled_from(["none", "pending", "running", "completed", "failed"]),
        embeddings_stage=st.one_of(
            st.none(),
            st.sampled_from(["initializing", "chunking", "embedding", "indexing", "completed"]),
        ),
        semantic_cache_status=st.sampled_from(["none", "pending", "computing", "completed", "failed"]),
    )
    @settings(max_examples=200)
    def test_overall_stage_returns_string(
        self,
        analysis_status: str,
        embeddings_status: str,
        embeddings_stage: str | None,
        semantic_cache_status: str,
    ):
        """
        **Feature: progress-tracking-refactor, Property 7: Overall Progress Computation**
        **Validates: Requirements 4.3**

        Property: For any combination of states, compute_overall_stage SHALL return
        a non-empty string describing the current phase.
        """
        from app.schemas.analysis import compute_overall_stage

        stage = compute_overall_stage(
            analysis_status=analysis_status,
            embeddings_status=embeddings_status,
            embeddings_stage=embeddings_stage,
            semantic_cache_status=semantic_cache_status,
        )

        assert isinstance(stage, str), f"overall_stage should be a string, got: {type(stage)}"
        assert len(stage) > 0, "overall_stage should not be empty"

    @given(embeddings_progress=st.integers(min_value=0, max_value=100))
    @settings(max_examples=100)
    def test_progress_monotonically_increases_through_phases(self, embeddings_progress: int):
        """
        **Feature: progress-tracking-refactor, Property 7: Overall Progress Computation**
        **Validates: Requirements 3.4, 4.2**

        Property: Progress SHALL monotonically increase as phases complete:
        pending < running < completed(analysis) < running(embeddings) < completed(embeddings) < completed(semantic)
        """
        from app.schemas.analysis import compute_overall_progress

        # Phase 1: Analysis pending
        p1 = compute_overall_progress("pending", "none", 0, "none")

        # Phase 2: Analysis running
        p2 = compute_overall_progress("running", "none", 0, "none")

        # Phase 3: Analysis complete, embeddings not started
        p3 = compute_overall_progress("completed", "none", 0, "none")

        # Phase 4: Embeddings running at given progress
        p4 = compute_overall_progress("completed", "running", embeddings_progress, "none")

        # Phase 5: Embeddings complete
        p5 = compute_overall_progress("completed", "completed", 100, "none")

        # Phase 6: Semantic cache computing
        p6 = compute_overall_progress("completed", "completed", 100, "computing")

        # Phase 7: All complete
        p7 = compute_overall_progress("completed", "completed", 100, "completed")

        # Verify monotonic increase (allowing equality for edge cases)
        assert p1 <= p2, f"pending ({p1}) should be <= running ({p2})"
        assert p2 <= p3, f"running ({p2}) should be <= completed analysis ({p3})"
        assert p3 <= p4, f"completed analysis ({p3}) should be <= embeddings running ({p4})"
        assert p4 <= p5, f"embeddings running ({p4}) should be <= embeddings complete ({p5})"
        assert p5 <= p6, f"embeddings complete ({p5}) should be <= semantic computing ({p6})"
        assert p6 <= p7, f"semantic computing ({p6}) should be <= all complete ({p7})"
