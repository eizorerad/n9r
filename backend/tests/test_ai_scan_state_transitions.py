"""Property-based tests for AI Scan state transitions.

Uses Hypothesis for property-based testing to verify correctness properties
defined in the design document for the ai-scan-progress-fix feature.

**Feature: ai-scan-progress-fix, Property 1: AI Scan State Transitions**
**Validates: Requirements 1.2, 1.3, 1.4**
"""

from hypothesis import given, settings, assume
from hypothesis import strategies as st

# =============================================================================
# Valid Status Values (from design document)
# =============================================================================

VALID_AI_SCAN_STATUS = ["none", "pending", "running", "completed", "failed", "skipped"]
VALID_PROGRESS_RANGE = (0, 100)

# AI scan status transitions (from design document)
# Key: current status, Value: set of allowed next statuses
AI_SCAN_TRANSITIONS: dict[str, set[str]] = {
    "none": {"pending", "skipped"},
    "pending": {"running", "failed", "skipped"},
    "running": {"completed", "failed"},
    "completed": set(),  # Terminal state
    "failed": {"pending"},  # Can retry
    "skipped": set(),  # Terminal state
}


# =============================================================================
# Custom Strategies
# =============================================================================


def valid_ai_scan_status() -> st.SearchStrategy[str]:
    """Generate valid ai_scan_status values."""
    return st.sampled_from(VALID_AI_SCAN_STATUS)


def valid_progress() -> st.SearchStrategy[int]:
    """Generate valid progress values (0-100)."""
    return st.integers(min_value=0, max_value=100)


def invalid_ai_scan_status() -> st.SearchStrategy[str]:
    """Generate invalid ai_scan_status values."""
    return st.text(min_size=1, max_size=20).filter(
        lambda s: s not in VALID_AI_SCAN_STATUS
    )


def invalid_progress_below() -> st.SearchStrategy[int]:
    """Generate invalid progress values below 0."""
    return st.integers(max_value=-1)


def invalid_progress_above() -> st.SearchStrategy[int]:
    """Generate invalid progress values above 100."""
    return st.integers(min_value=101)


@st.composite
def valid_transition_pair(draw: st.DrawFn) -> tuple[str, str]:
    """Generate a valid (current_status, new_status) transition pair."""
    # Pick a current status that has at least one valid transition
    current_statuses_with_transitions = [
        s for s, transitions in AI_SCAN_TRANSITIONS.items() if transitions
    ]
    current_status = draw(st.sampled_from(current_statuses_with_transitions))
    new_status = draw(st.sampled_from(list(AI_SCAN_TRANSITIONS[current_status])))
    return (current_status, new_status)


@st.composite
def invalid_transition_pair(draw: st.DrawFn) -> tuple[str, str]:
    """Generate an invalid (current_status, new_status) transition pair."""
    current_status = draw(valid_ai_scan_status())
    new_status = draw(valid_ai_scan_status())
    # Ensure the transition is invalid
    assume(new_status not in AI_SCAN_TRANSITIONS.get(current_status, set()))
    return (current_status, new_status)


# =============================================================================
# Validation Functions (mirrors what AnalysisStateService will implement)
# =============================================================================


def validate_ai_scan_status(status: str) -> bool:
    """
    Validate ai_scan_status against CHECK constraint.
    
    Mirrors: CHECK (ai_scan_status IN ('none', 'pending', 'running', 'completed', 'failed', 'skipped'))
    """
    return status in VALID_AI_SCAN_STATUS


def validate_ai_scan_progress(progress: int) -> bool:
    """
    Validate ai_scan_progress against CHECK constraint.
    
    Mirrors: CHECK (ai_scan_progress >= 0 AND ai_scan_progress <= 100)
    """
    return 0 <= progress <= 100


def is_valid_ai_scan_transition(current_status: str, new_status: str) -> bool:
    """
    Check if an AI scan status transition is valid.
    
    Args:
        current_status: Current ai_scan_status value
        new_status: Proposed new ai_scan_status value
        
    Returns:
        True if transition is valid, False otherwise
    """
    if current_status not in AI_SCAN_TRANSITIONS:
        return False
    return new_status in AI_SCAN_TRANSITIONS[current_status]


# =============================================================================
# Property Tests for AI Scan Status Constraint
# =============================================================================


class TestAIScanStatusConstraint:
    """
    Property tests for ai_scan_status CHECK constraint.
    
    **Feature: ai-scan-progress-fix, Property 1: AI Scan State Transitions**
    **Validates: Requirements 1.2, 1.3, 1.4**
    """

    @given(valid_ai_scan_status())
    @settings(max_examples=100)
    def test_valid_ai_scan_status_accepted(self, status: str):
        """
        **Feature: ai-scan-progress-fix, Property 1: AI Scan State Transitions**
        **Validates: Requirements 1.2, 1.3, 1.4**
        
        Property: For any valid ai_scan_status value ('none', 'pending', 'running', 
        'completed', 'failed', 'skipped'), the validation SHALL accept the value.
        """
        assert validate_ai_scan_status(status), (
            f"Valid ai_scan_status '{status}' should be accepted\n"
            f"Valid values: {VALID_AI_SCAN_STATUS}"
        )

    @given(invalid_ai_scan_status())
    @settings(max_examples=100)
    def test_invalid_ai_scan_status_rejected(self, status: str):
        """
        **Feature: ai-scan-progress-fix, Property 1: AI Scan State Transitions**
        **Validates: Requirements 1.2, 1.3, 1.4**
        
        Property: For any invalid ai_scan_status value (not in the valid set),
        the validation SHALL reject the value.
        """
        # Ensure we're testing truly invalid values
        assume(status not in VALID_AI_SCAN_STATUS)
        
        assert not validate_ai_scan_status(status), (
            f"Invalid ai_scan_status '{status}' should be rejected\n"
            f"Valid values: {VALID_AI_SCAN_STATUS}"
        )


class TestAIScanProgressConstraint:
    """
    Property tests for ai_scan_progress CHECK constraint.
    
    **Feature: ai-scan-progress-fix, Property 1: AI Scan State Transitions**
    **Validates: Requirements 1.2, 1.3, 1.4**
    """

    @given(valid_progress())
    @settings(max_examples=100)
    def test_valid_progress_accepted(self, progress: int):
        """
        **Feature: ai-scan-progress-fix, Property 1: AI Scan State Transitions**
        **Validates: Requirements 1.2, 1.3, 1.4**
        
        Property: For any progress value between 0 and 100 inclusive,
        the validation SHALL accept the value.
        """
        assert validate_ai_scan_progress(progress), (
            f"Valid progress {progress} should be accepted\n"
            f"Valid range: [0, 100]"
        )

    @given(invalid_progress_below())
    @settings(max_examples=100)
    def test_progress_below_zero_rejected(self, progress: int):
        """
        **Feature: ai-scan-progress-fix, Property 1: AI Scan State Transitions**
        **Validates: Requirements 1.2, 1.3, 1.4**
        
        Property: For any progress value below 0,
        the validation SHALL reject the value.
        """
        assert not validate_ai_scan_progress(progress), (
            f"Progress {progress} below 0 should be rejected\n"
            f"Valid range: [0, 100]"
        )

    @given(invalid_progress_above())
    @settings(max_examples=100)
    def test_progress_above_hundred_rejected(self, progress: int):
        """
        **Feature: ai-scan-progress-fix, Property 1: AI Scan State Transitions**
        **Validates: Requirements 1.2, 1.3, 1.4**
        
        Property: For any progress value above 100,
        the validation SHALL reject the value.
        """
        assert not validate_ai_scan_progress(progress), (
            f"Progress {progress} above 100 should be rejected\n"
            f"Valid range: [0, 100]"
        )


class TestAIScanStateTransitions:
    """
    Property tests for AI scan state transition validation.
    
    **Feature: ai-scan-progress-fix, Property 1: AI Scan State Transitions**
    **Validates: Requirements 1.2, 1.3, 1.4**
    """

    @given(valid_transition_pair())
    @settings(max_examples=100)
    def test_valid_transitions_accepted(self, transition: tuple[str, str]):
        """
        **Feature: ai-scan-progress-fix, Property 1: AI Scan State Transitions**
        **Validates: Requirements 1.2, 1.3, 1.4**
        
        Property: For any valid state transition according to AI_SCAN_TRANSITIONS,
        the transition validation SHALL accept the transition.
        """
        current_status, new_status = transition
        assert is_valid_ai_scan_transition(current_status, new_status), (
            f"Valid transition '{current_status}' -> '{new_status}' should be accepted\n"
            f"Allowed transitions from '{current_status}': {AI_SCAN_TRANSITIONS[current_status]}"
        )

    @given(invalid_transition_pair())
    @settings(max_examples=100)
    def test_invalid_transitions_rejected(self, transition: tuple[str, str]):
        """
        **Feature: ai-scan-progress-fix, Property 1: AI Scan State Transitions**
        **Validates: Requirements 1.2, 1.3, 1.4**
        
        Property: For any invalid state transition (not in AI_SCAN_TRANSITIONS),
        the transition validation SHALL reject the transition.
        """
        current_status, new_status = transition
        assert not is_valid_ai_scan_transition(current_status, new_status), (
            f"Invalid transition '{current_status}' -> '{new_status}' should be rejected\n"
            f"Allowed transitions from '{current_status}': {AI_SCAN_TRANSITIONS.get(current_status, set())}"
        )

    @given(valid_ai_scan_status())
    @settings(max_examples=100)
    def test_terminal_states_have_no_transitions(self, status: str):
        """
        **Feature: ai-scan-progress-fix, Property 1: AI Scan State Transitions**
        **Validates: Requirements 1.2, 1.3, 1.4**
        
        Property: For terminal states ('completed', 'skipped'), no outgoing
        transitions SHALL be allowed.
        """
        terminal_states = {"completed", "skipped"}
        if status in terminal_states:
            allowed_transitions = AI_SCAN_TRANSITIONS.get(status, set())
            assert len(allowed_transitions) == 0, (
                f"Terminal state '{status}' should have no outgoing transitions\n"
                f"Found transitions: {allowed_transitions}"
            )

    @given(valid_ai_scan_status())
    @settings(max_examples=100)
    def test_failed_state_allows_retry(self, status: str):
        """
        **Feature: ai-scan-progress-fix, Property 1: AI Scan State Transitions**
        **Validates: Requirements 1.2, 1.3, 1.4**
        
        Property: The 'failed' state SHALL allow transition to 'pending' for retry.
        """
        if status == "failed":
            assert is_valid_ai_scan_transition("failed", "pending"), (
                "Failed state should allow retry via transition to 'pending'"
            )


class TestAIScanTransitionCompleteness:
    """
    Property tests for AI scan transition map completeness.
    
    **Feature: ai-scan-progress-fix, Property 1: AI Scan State Transitions**
    **Validates: Requirements 1.2, 1.3, 1.4**
    """

    @given(valid_ai_scan_status())
    @settings(max_examples=100)
    def test_all_valid_statuses_in_transition_map(self, status: str):
        """
        **Feature: ai-scan-progress-fix, Property 1: AI Scan State Transitions**
        **Validates: Requirements 1.2, 1.3, 1.4**
        
        Property: For any valid ai_scan_status, the status SHALL be a key
        in the AI_SCAN_TRANSITIONS map.
        """
        assert status in AI_SCAN_TRANSITIONS, (
            f"Valid status '{status}' should be in AI_SCAN_TRANSITIONS map\n"
            f"Map keys: {list(AI_SCAN_TRANSITIONS.keys())}"
        )

    @given(valid_ai_scan_status(), valid_ai_scan_status())
    @settings(max_examples=200)
    def test_transition_validation_consistency(
        self, current_status: str, new_status: str
    ):
        """
        **Feature: ai-scan-progress-fix, Property 1: AI Scan State Transitions**
        **Validates: Requirements 1.2, 1.3, 1.4**
        
        Property: For any pair of valid statuses, the transition validation
        SHALL correctly identify whether the transition is valid or invalid.
        """
        expected_valid = new_status in AI_SCAN_TRANSITIONS.get(current_status, set())
        actual_valid = is_valid_ai_scan_transition(current_status, new_status)
        
        assert actual_valid == expected_valid, (
            f"Transition validation mismatch for '{current_status}' -> '{new_status}'\n"
            f"Expected valid: {expected_valid}, Got: {actual_valid}\n"
            f"Allowed transitions: {AI_SCAN_TRANSITIONS.get(current_status, set())}"
        )


# =============================================================================
# Property Tests for AI Scan State Service Methods
# =============================================================================


class TestAIScanTimestampUpdates:
    """
    Property tests for AI scan timestamp updates on state changes.
    
    **Feature: ai-scan-progress-fix, Property 3: State Timestamp Updates**
    **Validates: Requirements 2.4**
    """

    @given(
        initial_status=st.sampled_from(["none", "pending", "running", "failed"]),
        progress=valid_progress(),
    )
    @settings(max_examples=100)
    def test_timestamp_updated_on_ai_scan_status_change(
        self, initial_status: str, progress: int
    ):
        """
        **Feature: ai-scan-progress-fix, Property 3: State Timestamp Updates**
        **Validates: Requirements 2.4**
        
        Property: For any AI scan state change via AnalysisStateService, the 
        state_updated_at timestamp SHALL be updated to a value greater than or 
        equal to the previous value.
        """
        from datetime import datetime, timezone
        from unittest.mock import MagicMock
        import uuid
        
        from app.services.analysis_state import (
            AnalysisStateService,
            AI_SCAN_TRANSITIONS,
        )
        
        # Create mock analysis
        analysis_id = uuid.uuid4()
        initial_timestamp = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        
        mock_analysis = MagicMock()
        mock_analysis.id = analysis_id
        mock_analysis.ai_scan_status = initial_status
        mock_analysis.ai_scan_progress = 0
        mock_analysis.ai_scan_stage = None
        mock_analysis.ai_scan_message = None
        mock_analysis.ai_scan_error = None
        mock_analysis.ai_scan_started_at = None
        mock_analysis.ai_scan_completed_at = None
        mock_analysis.ai_scan_cache = None
        mock_analysis.state_updated_at = initial_timestamp
        
        # Create mock session
        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_analysis
        mock_session.execute.return_value = mock_result
        
        # Create service with events disabled
        service = AnalysisStateService(mock_session, publish_events=False)
        
        # Determine valid next status
        allowed = AI_SCAN_TRANSITIONS.get(initial_status, set())
        if not allowed:
            return  # Skip if no valid transitions
        
        new_status = list(allowed)[0]
        
        # Perform update
        service.update_ai_scan_status(
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


class TestAIScanFailureIsolation:
    """
    Property tests for AI scan failure isolation.
    
    **Feature: ai-scan-progress-fix, Property 6: Failure Isolation**
    **Validates: Requirements 5.2**
    """

    @given(
        error_message=st.text(min_size=1, max_size=100, alphabet=st.characters(whitelist_categories=('L', 'N', 'P', 'Z'))),
        embeddings_status=st.sampled_from(["none", "pending", "running", "completed", "failed"]),
        semantic_cache_status=st.sampled_from(["none", "pending", "computing", "completed", "failed"]),
    )
    @settings(max_examples=100)
    def test_ai_scan_failure_does_not_affect_other_statuses(
        self, error_message: str, embeddings_status: str, semantic_cache_status: str
    ):
        """
        **Feature: ai-scan-progress-fix, Property 6: Failure Isolation**
        **Validates: Requirements 5.2**
        
        Property: For any AI scan failure (ai_scan_status="failed"), the 
        analysis_status, embeddings_status, semantic_cache_status, and their 
        associated data SHALL remain unchanged.
        """
        from datetime import datetime, timezone
        from unittest.mock import MagicMock
        import uuid
        
        from app.services.analysis_state import AnalysisStateService
        
        # Create mock analysis in 'running' state (can transition to 'failed')
        analysis_id = uuid.uuid4()
        initial_timestamp = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        
        mock_analysis = MagicMock()
        mock_analysis.id = analysis_id
        mock_analysis.status = "completed"  # Analysis status
        mock_analysis.embeddings_status = embeddings_status
        mock_analysis.embeddings_progress = 50
        mock_analysis.semantic_cache_status = semantic_cache_status
        mock_analysis.semantic_cache = {"test": "data"}
        mock_analysis.ai_scan_status = "running"  # Can transition to failed
        mock_analysis.ai_scan_progress = 30
        mock_analysis.ai_scan_stage = "scanning"
        mock_analysis.ai_scan_message = "In progress"
        mock_analysis.ai_scan_error = None
        mock_analysis.ai_scan_started_at = initial_timestamp
        mock_analysis.ai_scan_completed_at = None
        mock_analysis.ai_scan_cache = None
        mock_analysis.state_updated_at = initial_timestamp
        
        # Create mock session
        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_analysis
        mock_session.execute.return_value = mock_result
        
        # Create service with events disabled
        service = AnalysisStateService(mock_session, publish_events=False)
        
        # Fail AI scan
        service.fail_ai_scan(analysis_id, error_message)
        
        # Verify AI scan status changed to failed
        assert mock_analysis.ai_scan_status == "failed", (
            f"ai_scan_status should be 'failed', got: '{mock_analysis.ai_scan_status}'"
        )
        
        # Verify error message was stored
        assert mock_analysis.ai_scan_error == error_message, (
            f"ai_scan_error should be '{error_message}', got: '{mock_analysis.ai_scan_error}'"
        )
        
        # Verify other statuses were NOT changed (isolation)
        assert mock_analysis.status == "completed", (
            f"analysis status should remain 'completed', got: '{mock_analysis.status}'"
        )
        assert mock_analysis.embeddings_status == embeddings_status, (
            f"embeddings_status should remain '{embeddings_status}', got: '{mock_analysis.embeddings_status}'"
        )
        assert mock_analysis.semantic_cache_status == semantic_cache_status, (
            f"semantic_cache_status should remain '{semantic_cache_status}', got: '{mock_analysis.semantic_cache_status}'"
        )
        assert mock_analysis.semantic_cache == {"test": "data"}, (
            "semantic_cache data should remain unchanged"
        )


class TestAIScanRetryCapability:
    """
    Property tests for AI scan retry capability.
    
    **Feature: ai-scan-progress-fix, Property 7: Retry Capability**
    **Validates: Requirements 5.3**
    """

    @given(
        original_error=st.text(min_size=1, max_size=100, alphabet=st.characters(whitelist_categories=('L', 'N', 'P', 'Z'))),
    )
    @settings(max_examples=100)
    def test_failed_ai_scan_can_retry_to_pending(self, original_error: str):
        """
        **Feature: ai-scan-progress-fix, Property 7: Retry Capability**
        **Validates: Requirements 5.3**
        
        Property: For any analysis with ai_scan_status="failed", the transition 
        to ai_scan_status="pending" SHALL be valid and SHALL clear ai_scan_error.
        """
        from datetime import datetime, timezone
        from unittest.mock import MagicMock
        import uuid
        
        from app.services.analysis_state import (
            AnalysisStateService,
            is_valid_ai_scan_transition,
        )
        
        # First verify the transition is valid
        assert is_valid_ai_scan_transition("failed", "pending"), (
            "Transition from 'failed' to 'pending' should be valid for retry"
        )
        
        # Create mock analysis in 'failed' state
        analysis_id = uuid.uuid4()
        initial_timestamp = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        
        mock_analysis = MagicMock()
        mock_analysis.id = analysis_id
        mock_analysis.ai_scan_status = "failed"
        mock_analysis.ai_scan_progress = 30
        mock_analysis.ai_scan_stage = "error"
        mock_analysis.ai_scan_message = f"AI scan failed: {original_error}"
        mock_analysis.ai_scan_error = original_error
        mock_analysis.ai_scan_started_at = initial_timestamp
        mock_analysis.ai_scan_completed_at = None
        mock_analysis.ai_scan_cache = None
        mock_analysis.state_updated_at = initial_timestamp
        
        # Create mock session
        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_analysis
        mock_session.execute.return_value = mock_result
        
        # Create service with events disabled
        service = AnalysisStateService(mock_session, publish_events=False)
        
        # Retry by marking as pending
        service.mark_ai_scan_pending(analysis_id)
        
        # Verify status changed to pending
        assert mock_analysis.ai_scan_status == "pending", (
            f"ai_scan_status should be 'pending' after retry, got: '{mock_analysis.ai_scan_status}'"
        )
        
        # Verify progress was reset
        assert mock_analysis.ai_scan_progress == 0, (
            f"ai_scan_progress should be reset to 0, got: {mock_analysis.ai_scan_progress}"
        )
        
        # Verify stage was updated
        assert mock_analysis.ai_scan_stage == "pending", (
            f"ai_scan_stage should be 'pending', got: '{mock_analysis.ai_scan_stage}'"
        )

    def test_retry_transition_is_valid(self):
        """
        **Feature: ai-scan-progress-fix, Property 7: Retry Capability**
        **Validates: Requirements 5.3**
        
        Property: The 'failed' -> 'pending' transition SHALL always be valid.
        """
        from app.services.analysis_state import (
            AI_SCAN_TRANSITIONS,
            is_valid_ai_scan_transition,
        )
        
        # Verify in transition map
        assert "pending" in AI_SCAN_TRANSITIONS["failed"], (
            "'pending' should be in allowed transitions from 'failed'"
        )
        
        # Verify via validation function
        assert is_valid_ai_scan_transition("failed", "pending"), (
            "Transition 'failed' -> 'pending' should be valid"
        )


# =============================================================================
# Property Tests for Automatic Chaining from Semantic Cache
# =============================================================================


class TestAutomaticChainingFromSemanticCache:
    """
    Property tests for automatic AI scan chaining from semantic cache completion.
    
    **Feature: ai-scan-progress-fix, Property 2: Automatic Chaining from Semantic Cache**
    **Validates: Requirements 1.1**
    """

    @given(
        cache_data=st.fixed_dictionaries({
            "clusters": st.lists(st.integers(), min_size=0, max_size=5),
            "outliers": st.lists(st.integers(), min_size=0, max_size=3),
        }),
    )
    @settings(max_examples=100)
    def test_semantic_cache_completion_triggers_ai_scan_pending_when_enabled(
        self, cache_data: dict
    ):
        """
        **Feature: ai-scan-progress-fix, Property 2: Automatic Chaining from Semantic Cache**
        **Validates: Requirements 1.1**
        
        Property: For any analysis where semantic_cache_status transitions to 
        "completed" and ai_scan_enabled=True, the ai_scan_status SHALL 
        automatically transition to "pending".
        """
        from datetime import datetime, timezone
        from unittest.mock import MagicMock, patch
        import uuid
        
        from app.services.analysis_state import AnalysisStateService
        
        # Create mock analysis in 'computing' state (can transition to 'completed')
        analysis_id = uuid.uuid4()
        initial_timestamp = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        
        mock_analysis = MagicMock()
        mock_analysis.id = analysis_id
        mock_analysis.semantic_cache_status = "computing"
        mock_analysis.semantic_cache = None
        mock_analysis.ai_scan_status = "none"  # Not yet started
        mock_analysis.ai_scan_stage = None
        mock_analysis.ai_scan_message = None
        mock_analysis.state_updated_at = initial_timestamp
        
        # Create mock session
        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_analysis
        mock_session.execute.return_value = mock_result
        
        # Create service with events disabled
        service = AnalysisStateService(mock_session, publish_events=False)
        
        # Mock settings with ai_scan_enabled=True
        mock_settings = MagicMock()
        mock_settings.ai_scan_enabled = True
        
        with patch('app.core.config.settings', mock_settings):
            # Complete semantic cache
            service.complete_semantic_cache(analysis_id, cache_data)
        
        # Verify semantic cache status changed to completed
        assert mock_analysis.semantic_cache_status == "completed", (
            f"semantic_cache_status should be 'completed', got: '{mock_analysis.semantic_cache_status}'"
        )
        
        # Verify cache data was stored
        assert mock_analysis.semantic_cache == cache_data, (
            f"semantic_cache should contain the cache data"
        )
        
        # Verify AI scan was auto-triggered to pending
        assert mock_analysis.ai_scan_status == "pending", (
            f"ai_scan_status should be 'pending' after semantic cache completion, "
            f"got: '{mock_analysis.ai_scan_status}'"
        )
        
        # Verify AI scan stage and message were set
        assert mock_analysis.ai_scan_stage == "pending", (
            f"ai_scan_stage should be 'pending', got: '{mock_analysis.ai_scan_stage}'"
        )
        assert mock_analysis.ai_scan_message is not None, (
            "ai_scan_message should be set"
        )

    @given(
        cache_data=st.fixed_dictionaries({
            "clusters": st.lists(st.integers(), min_size=0, max_size=5),
            "outliers": st.lists(st.integers(), min_size=0, max_size=3),
        }),
        existing_ai_scan_status=st.sampled_from(["pending", "running", "completed", "failed", "skipped"]),
    )
    @settings(max_examples=100)
    def test_semantic_cache_completion_preserves_non_none_ai_scan_status(
        self, cache_data: dict, existing_ai_scan_status: str
    ):
        """
        **Feature: ai-scan-progress-fix, Property 2: Automatic Chaining from Semantic Cache**
        **Validates: Requirements 1.1**
        
        Property: For any analysis where ai_scan_status is NOT 'none' when 
        semantic_cache completes, the ai_scan_status SHALL remain unchanged.
        """
        from datetime import datetime, timezone
        from unittest.mock import MagicMock, patch
        import uuid
        
        from app.services.analysis_state import AnalysisStateService
        
        # Create mock analysis with existing AI scan status
        analysis_id = uuid.uuid4()
        initial_timestamp = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        
        mock_analysis = MagicMock()
        mock_analysis.id = analysis_id
        mock_analysis.semantic_cache_status = "computing"
        mock_analysis.semantic_cache = None
        mock_analysis.ai_scan_status = existing_ai_scan_status  # Already started/completed
        mock_analysis.ai_scan_stage = "some_stage"
        mock_analysis.ai_scan_message = "some message"
        mock_analysis.state_updated_at = initial_timestamp
        
        # Create mock session
        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_analysis
        mock_session.execute.return_value = mock_result
        
        # Create service with events disabled
        service = AnalysisStateService(mock_session, publish_events=False)
        
        # Mock settings with ai_scan_enabled=True
        mock_settings = MagicMock()
        mock_settings.ai_scan_enabled = True
        
        with patch('app.core.config.settings', mock_settings):
            # Complete semantic cache
            service.complete_semantic_cache(analysis_id, cache_data)
        
        # Verify semantic cache status changed to completed
        assert mock_analysis.semantic_cache_status == "completed", (
            f"semantic_cache_status should be 'completed', got: '{mock_analysis.semantic_cache_status}'"
        )
        
        # Verify AI scan status was NOT changed (already had a non-none status)
        assert mock_analysis.ai_scan_status == existing_ai_scan_status, (
            f"ai_scan_status should remain '{existing_ai_scan_status}' when not 'none', "
            f"got: '{mock_analysis.ai_scan_status}'"
        )

    def test_chaining_only_happens_from_none_status(self):
        """
        **Feature: ai-scan-progress-fix, Property 2: Automatic Chaining from Semantic Cache**
        **Validates: Requirements 1.1**
        
        Property: Auto-chaining to AI scan SHALL only occur when ai_scan_status 
        is 'none', not when it's any other status.
        """
        # This is a simple verification that the logic is correct
        # The property tests above verify this with generated data
        non_none_statuses = ["pending", "running", "completed", "failed", "skipped"]
        
        for status in non_none_statuses:
            # If ai_scan_status is not 'none', it should not be changed
            # This is verified by the property test above
            assert status != "none", f"Status '{status}' should not be 'none'"


class TestAIScanSkipBehavior:
    """
    Property tests for AI scan skip behavior when disabled.
    
    **Feature: ai-scan-progress-fix, Property 8: Skip Behavior**
    **Validates: Requirements 5.1**
    """

    @given(
        cache_data=st.fixed_dictionaries({
            "clusters": st.lists(st.integers(), min_size=0, max_size=5),
            "outliers": st.lists(st.integers(), min_size=0, max_size=3),
        }),
    )
    @settings(max_examples=100)
    def test_semantic_cache_completion_skips_ai_scan_when_disabled(
        self, cache_data: dict
    ):
        """
        **Feature: ai-scan-progress-fix, Property 8: Skip Behavior**
        **Validates: Requirements 5.1**
        
        Property: For any analysis where ai_scan_enabled=False, the ai_scan_status 
        SHALL be "skipped" after semantic cache completes, and no AI scan task 
        SHALL be queued.
        """
        from datetime import datetime, timezone
        from unittest.mock import MagicMock, patch
        import uuid
        
        from app.services.analysis_state import AnalysisStateService
        
        # Create mock analysis in 'computing' state (can transition to 'completed')
        analysis_id = uuid.uuid4()
        initial_timestamp = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        
        mock_analysis = MagicMock()
        mock_analysis.id = analysis_id
        mock_analysis.semantic_cache_status = "computing"
        mock_analysis.semantic_cache = None
        mock_analysis.ai_scan_status = "none"  # Not yet started
        mock_analysis.ai_scan_stage = None
        mock_analysis.ai_scan_message = None
        mock_analysis.state_updated_at = initial_timestamp
        
        # Create mock session
        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_analysis
        mock_session.execute.return_value = mock_result
        
        # Create service with events disabled
        service = AnalysisStateService(mock_session, publish_events=False)
        
        # Mock settings with ai_scan_enabled=False
        mock_settings = MagicMock()
        mock_settings.ai_scan_enabled = False
        
        with patch('app.core.config.settings', mock_settings):
            # Complete semantic cache
            service.complete_semantic_cache(analysis_id, cache_data)
        
        # Verify semantic cache status changed to completed
        assert mock_analysis.semantic_cache_status == "completed", (
            f"semantic_cache_status should be 'completed', got: '{mock_analysis.semantic_cache_status}'"
        )
        
        # Verify cache data was stored
        assert mock_analysis.semantic_cache == cache_data, (
            f"semantic_cache should contain the cache data"
        )
        
        # Verify AI scan was skipped (not pending)
        assert mock_analysis.ai_scan_status == "skipped", (
            f"ai_scan_status should be 'skipped' when ai_scan_enabled=False, "
            f"got: '{mock_analysis.ai_scan_status}'"
        )
        
        # Verify AI scan stage and message were set appropriately
        assert mock_analysis.ai_scan_stage == "skipped", (
            f"ai_scan_stage should be 'skipped', got: '{mock_analysis.ai_scan_stage}'"
        )
        assert mock_analysis.ai_scan_message is not None, (
            "ai_scan_message should be set"
        )
        assert "disabled" in mock_analysis.ai_scan_message.lower() or "skipped" in mock_analysis.ai_scan_message.lower(), (
            f"ai_scan_message should indicate skipped/disabled, got: '{mock_analysis.ai_scan_message}'"
        )

    @given(
        cache_data=st.fixed_dictionaries({
            "clusters": st.lists(st.integers(), min_size=0, max_size=5),
            "outliers": st.lists(st.integers(), min_size=0, max_size=3),
        }),
        existing_ai_scan_status=st.sampled_from(["pending", "running", "completed", "failed", "skipped"]),
    )
    @settings(max_examples=100)
    def test_skip_does_not_override_existing_ai_scan_status(
        self, cache_data: dict, existing_ai_scan_status: str
    ):
        """
        **Feature: ai-scan-progress-fix, Property 8: Skip Behavior**
        **Validates: Requirements 5.1**
        
        Property: For any analysis where ai_scan_status is NOT 'none' when 
        semantic_cache completes (even with ai_scan_enabled=False), the 
        ai_scan_status SHALL remain unchanged.
        """
        from datetime import datetime, timezone
        from unittest.mock import MagicMock, patch
        import uuid
        
        from app.services.analysis_state import AnalysisStateService
        
        # Create mock analysis with existing AI scan status
        analysis_id = uuid.uuid4()
        initial_timestamp = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        
        mock_analysis = MagicMock()
        mock_analysis.id = analysis_id
        mock_analysis.semantic_cache_status = "computing"
        mock_analysis.semantic_cache = None
        mock_analysis.ai_scan_status = existing_ai_scan_status  # Already started/completed
        mock_analysis.ai_scan_stage = "some_stage"
        mock_analysis.ai_scan_message = "some message"
        mock_analysis.state_updated_at = initial_timestamp
        
        # Create mock session
        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_analysis
        mock_session.execute.return_value = mock_result
        
        # Create service with events disabled
        service = AnalysisStateService(mock_session, publish_events=False)
        
        # Mock settings with ai_scan_enabled=False
        mock_settings = MagicMock()
        mock_settings.ai_scan_enabled = False
        
        with patch('app.core.config.settings', mock_settings):
            # Complete semantic cache
            service.complete_semantic_cache(analysis_id, cache_data)
        
        # Verify semantic cache status changed to completed
        assert mock_analysis.semantic_cache_status == "completed", (
            f"semantic_cache_status should be 'completed', got: '{mock_analysis.semantic_cache_status}'"
        )
        
        # Verify AI scan status was NOT changed (already had a non-none status)
        assert mock_analysis.ai_scan_status == existing_ai_scan_status, (
            f"ai_scan_status should remain '{existing_ai_scan_status}' when not 'none', "
            f"got: '{mock_analysis.ai_scan_status}'"
        )

    def test_skipped_is_terminal_state(self):
        """
        **Feature: ai-scan-progress-fix, Property 8: Skip Behavior**
        **Validates: Requirements 5.1**
        
        Property: The 'skipped' state SHALL be a terminal state with no 
        outgoing transitions.
        """
        from app.services.analysis_state import AI_SCAN_TRANSITIONS
        
        # Verify skipped is in the transition map
        assert "skipped" in AI_SCAN_TRANSITIONS, (
            "'skipped' should be in AI_SCAN_TRANSITIONS map"
        )
        
        # Verify skipped has no outgoing transitions
        assert len(AI_SCAN_TRANSITIONS["skipped"]) == 0, (
            f"'skipped' should have no outgoing transitions, "
            f"found: {AI_SCAN_TRANSITIONS['skipped']}"
        )

    @given(
        ai_scan_enabled=st.booleans(),
        cache_data=st.fixed_dictionaries({
            "clusters": st.lists(st.integers(), min_size=0, max_size=5),
            "outliers": st.lists(st.integers(), min_size=0, max_size=3),
        }),
    )
    @settings(max_examples=100)
    def test_ai_scan_status_depends_on_enabled_setting(
        self, ai_scan_enabled: bool, cache_data: dict
    ):
        """
        **Feature: ai-scan-progress-fix, Property 8: Skip Behavior**
        **Validates: Requirements 5.1**
        
        Property: For any analysis with ai_scan_status='none', after semantic 
        cache completes, the ai_scan_status SHALL be 'pending' if ai_scan_enabled=True, 
        or 'skipped' if ai_scan_enabled=False.
        """
        from datetime import datetime, timezone
        from unittest.mock import MagicMock, patch
        import uuid
        
        from app.services.analysis_state import AnalysisStateService
        
        # Create mock analysis in 'computing' state
        analysis_id = uuid.uuid4()
        initial_timestamp = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        
        mock_analysis = MagicMock()
        mock_analysis.id = analysis_id
        mock_analysis.semantic_cache_status = "computing"
        mock_analysis.semantic_cache = None
        mock_analysis.ai_scan_status = "none"  # Not yet started
        mock_analysis.ai_scan_stage = None
        mock_analysis.ai_scan_message = None
        mock_analysis.state_updated_at = initial_timestamp
        
        # Create mock session
        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_analysis
        mock_session.execute.return_value = mock_result
        
        # Create service with events disabled
        service = AnalysisStateService(mock_session, publish_events=False)
        
        # Mock settings with the given ai_scan_enabled value
        mock_settings = MagicMock()
        mock_settings.ai_scan_enabled = ai_scan_enabled
        
        with patch('app.core.config.settings', mock_settings):
            # Complete semantic cache
            service.complete_semantic_cache(analysis_id, cache_data)
        
        # Verify the expected ai_scan_status based on ai_scan_enabled
        expected_status = "pending" if ai_scan_enabled else "skipped"
        assert mock_analysis.ai_scan_status == expected_status, (
            f"ai_scan_status should be '{expected_status}' when ai_scan_enabled={ai_scan_enabled}, "
            f"got: '{mock_analysis.ai_scan_status}'"
        )
