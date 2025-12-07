"""Property-based tests for parallel progress calculation functions.

Tests the compute_overall_progress_parallel, compute_overall_stage_parallel,
and compute_is_complete_parallel functions.

**Feature: parallel-analysis-pipeline**
**Validates: Requirements 2.1, 2.2, 2.3, 2.4, 3.1, 3.2, 3.3, 4.1, 4.2, 4.3, 4.4**
"""

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from app.schemas.analysis import (
    compute_is_complete_parallel,
    compute_overall_progress_parallel,
    compute_overall_stage_parallel,
)

# =============================================================================
# Hypothesis Strategies
# =============================================================================


def analysis_status_strategy() -> st.SearchStrategy[str]:
    """Generate valid analysis status values."""
    return st.sampled_from(["pending", "running", "completed", "failed"])


def embeddings_status_strategy() -> st.SearchStrategy[str]:
    """Generate valid embeddings status values."""
    return st.sampled_from(["pending", "running", "completed", "failed"])


def semantic_cache_status_strategy() -> st.SearchStrategy[str]:
    """Generate valid semantic cache status values."""
    return st.sampled_from(["pending", "computing", "completed", "failed"])


def ai_scan_status_strategy() -> st.SearchStrategy[str]:
    """Generate valid AI scan status values."""
    return st.sampled_from(["pending", "running", "completed", "failed", "skipped"])


def progress_strategy() -> st.SearchStrategy[int]:
    """Generate valid progress values (0-100)."""
    return st.integers(min_value=0, max_value=100)


def embeddings_stage_strategy() -> st.SearchStrategy[str | None]:
    """Generate valid embeddings stage values."""
    return st.one_of(
        st.none(),
        st.sampled_from(["initializing", "chunking", "embedding", "indexing", "completed"])
    )


def ai_scan_stage_strategy() -> st.SearchStrategy[str | None]:
    """Generate valid AI scan stage values."""
    return st.one_of(
        st.none(),
        st.sampled_from(["initializing", "cloning", "generating_view", "scanning", "merging", "investigating", "completed"])
    )


# =============================================================================
# Property Tests: Parallel Progress Calculation (Property 4)
# =============================================================================


class TestParallelProgressCalculationProperty:
    """
    Property tests for parallel progress calculation.

    **Feature: parallel-analysis-pipeline, Property 4: Parallel Progress Calculation**
    **Validates: Requirements 2.1, 2.2**
    """

    @given(
        analysis_status=analysis_status_strategy(),
        analysis_progress=progress_strategy(),
        embeddings_status=embeddings_status_strategy(),
        embeddings_progress=progress_strategy(),
        semantic_cache_status=semantic_cache_status_strategy(),
        ai_scan_status=ai_scan_status_strategy(),
        ai_scan_progress=progress_strategy(),
    )
    @settings(max_examples=100)
    def test_progress_bounds(
        self,
        analysis_status: str,
        analysis_progress: int,
        embeddings_status: str,
        embeddings_progress: int,
        semantic_cache_status: str,
        ai_scan_status: str,
        ai_scan_progress: int,
    ):
        """
        Property: For any combination of track statuses and progress values,
        the computed overall_progress SHALL be between 0 and 100.

        **Feature: parallel-analysis-pipeline, Property 4: Parallel Progress Calculation**
        **Validates: Requirements 2.1**
        """
        progress = compute_overall_progress_parallel(
            analysis_status=analysis_status,
            analysis_progress=analysis_progress,
            embeddings_status=embeddings_status,
            embeddings_progress=embeddings_progress,
            semantic_cache_status=semantic_cache_status,
            ai_scan_status=ai_scan_status,
            ai_scan_progress=ai_scan_progress,
        )

        # Property: Progress MUST be between 0 and 100
        assert 0 <= progress <= 100, f"Progress {progress} is out of bounds [0, 100]"

    @given(
        analysis_status=analysis_status_strategy(),
        analysis_progress=progress_strategy(),
        embeddings_status=embeddings_status_strategy(),
        embeddings_progress=progress_strategy(),
        semantic_cache_status=semantic_cache_status_strategy(),
        ai_scan_status=ai_scan_status_strategy(),
        ai_scan_progress=progress_strategy(),
    )
    @settings(max_examples=100)
    def test_progress_weighted_sum(
        self,
        analysis_status: str,
        analysis_progress: int,
        embeddings_status: str,
        embeddings_progress: int,
        semantic_cache_status: str,
        ai_scan_status: str,
        ai_scan_progress: int,
    ):
        """
        Property: For any combination of track statuses and progress values,
        the computed overall_progress SHALL equal the sum of weighted track
        contributions (33% each), capped at 95% unless all complete.

        **Feature: parallel-analysis-pipeline, Property 4: Parallel Progress Calculation**
        **Validates: Requirements 2.1, 2.2**
        """
        progress = compute_overall_progress_parallel(
            analysis_status=analysis_status,
            analysis_progress=analysis_progress,
            embeddings_status=embeddings_status,
            embeddings_progress=embeddings_progress,
            semantic_cache_status=semantic_cache_status,
            ai_scan_status=ai_scan_status,
            ai_scan_progress=ai_scan_progress,
        )

        # Calculate expected track contributions
        terminal_states = ("completed", "failed", "skipped")

        # Track A: Static Analysis (0-33%)
        if analysis_status == "pending":
            expected_static = 0
        elif analysis_status == "running":
            expected_static = int(analysis_progress * 0.33)
        elif analysis_status in terminal_states:
            expected_static = 33
        else:
            expected_static = 0

        # Track B: Embeddings + Semantic Cache (0-33%)
        if embeddings_status == "pending":
            expected_embeddings = 0
        elif embeddings_status == "running":
            expected_embeddings = int(embeddings_progress * 0.25)
        elif embeddings_status in terminal_states:
            expected_embeddings = 25
            if semantic_cache_status == "computing":
                expected_embeddings = 29
            elif semantic_cache_status in terminal_states:
                expected_embeddings = 33
        else:
            expected_embeddings = 0

        # Track C: AI Scan (0-33%)
        if ai_scan_status == "pending":
            expected_ai_scan = 0
        elif ai_scan_status == "running":
            expected_ai_scan = int(ai_scan_progress * 0.33)
        elif ai_scan_status in terminal_states:
            expected_ai_scan = 33
        else:
            expected_ai_scan = 0

        expected_total = expected_static + expected_embeddings + expected_ai_scan

        # Check if all terminal
        all_terminal = (
            analysis_status in terminal_states and
            embeddings_status in terminal_states and
            semantic_cache_status in terminal_states and
            ai_scan_status in terminal_states
        )

        if all_terminal:
            expected_progress = 100
        else:
            expected_progress = min(expected_total, 95)

        assert progress == expected_progress, \
            f"Expected progress {expected_progress}, got {progress}"


# =============================================================================
# Property Tests: Progress Completion Detection (Property 5)
# =============================================================================


class TestProgressCompletionDetectionProperty:
    """
    Property tests for progress completion detection.

    **Feature: parallel-analysis-pipeline, Property 5: Progress Completion Detection**
    **Validates: Requirements 2.3**
    """

    @given(
        analysis_progress=progress_strategy(),
        embeddings_progress=progress_strategy(),
        ai_scan_progress=progress_strategy(),
    )
    @settings(max_examples=100)
    def test_all_terminal_returns_100(
        self,
        analysis_progress: int,
        embeddings_progress: int,
        ai_scan_progress: int,
    ):
        """
        Property: For any state where all tracks reach terminal states,
        the computed overall_progress SHALL be 100%.

        **Feature: parallel-analysis-pipeline, Property 5: Progress Completion Detection**
        **Validates: Requirements 2.3**
        """
        # Test all combinations of terminal states
        terminal_analysis = ["completed", "failed"]
        terminal_embeddings = ["completed", "failed"]
        terminal_semantic = ["completed", "failed"]
        terminal_ai_scan = ["completed", "failed", "skipped"]

        for analysis_status in terminal_analysis:
            for embeddings_status in terminal_embeddings:
                for semantic_cache_status in terminal_semantic:
                    for ai_scan_status in terminal_ai_scan:
                        progress = compute_overall_progress_parallel(
                            analysis_status=analysis_status,
                            analysis_progress=analysis_progress,
                            embeddings_status=embeddings_status,
                            embeddings_progress=embeddings_progress,
                            semantic_cache_status=semantic_cache_status,
                            ai_scan_status=ai_scan_status,
                            ai_scan_progress=ai_scan_progress,
                        )

                        assert progress == 100, \
                            f"Expected 100% when all terminal, got {progress}% " \
                            f"(analysis={analysis_status}, embeddings={embeddings_status}, " \
                            f"semantic={semantic_cache_status}, ai_scan={ai_scan_status})"


# =============================================================================
# Property Tests: Progress Cap at 95% (Property 6)
# =============================================================================


class TestProgressCapProperty:
    """
    Property tests for progress cap at 95%.

    **Feature: parallel-analysis-pipeline, Property 6: Progress Cap at 95%**
    **Validates: Requirements 2.4**
    """

    @given(
        analysis_status=analysis_status_strategy(),
        analysis_progress=progress_strategy(),
        embeddings_status=embeddings_status_strategy(),
        embeddings_progress=progress_strategy(),
        semantic_cache_status=semantic_cache_status_strategy(),
        ai_scan_status=ai_scan_status_strategy(),
        ai_scan_progress=progress_strategy(),
    )
    @settings(max_examples=100)
    def test_progress_capped_at_95_when_not_all_terminal(
        self,
        analysis_status: str,
        analysis_progress: int,
        embeddings_status: str,
        embeddings_progress: int,
        semantic_cache_status: str,
        ai_scan_status: str,
        ai_scan_progress: int,
    ):
        """
        Property: For any state where at least one track has not reached
        a terminal state, the computed overall_progress SHALL NOT exceed 95%.

        **Feature: parallel-analysis-pipeline, Property 6: Progress Cap at 95%**
        **Validates: Requirements 2.4**
        """
        terminal_states = ("completed", "failed", "skipped")

        # Check if all terminal
        all_terminal = (
            analysis_status in terminal_states and
            embeddings_status in terminal_states and
            semantic_cache_status in terminal_states and
            ai_scan_status in terminal_states
        )

        # Skip if all terminal (that case is tested separately)
        assume(not all_terminal)

        progress = compute_overall_progress_parallel(
            analysis_status=analysis_status,
            analysis_progress=analysis_progress,
            embeddings_status=embeddings_status,
            embeddings_progress=embeddings_progress,
            semantic_cache_status=semantic_cache_status,
            ai_scan_status=ai_scan_status,
            ai_scan_progress=ai_scan_progress,
        )

        # Property: Progress MUST NOT exceed 95% when not all terminal
        assert progress <= 95, \
            f"Progress {progress}% exceeds 95% cap when not all tracks terminal"


# =============================================================================
# Property Tests: Combined Stage Description (Property 7)
# =============================================================================


class TestCombinedStageDescriptionProperty:
    """
    Property tests for combined stage description.

    **Feature: parallel-analysis-pipeline, Property 7: Combined Stage Description**
    **Validates: Requirements 3.1, 3.2, 3.3**
    """

    @given(
        analysis_status=analysis_status_strategy(),
        embeddings_status=embeddings_status_strategy(),
        embeddings_stage=embeddings_stage_strategy(),
        semantic_cache_status=semantic_cache_status_strategy(),
        ai_scan_status=ai_scan_status_strategy(),
        ai_scan_stage=ai_scan_stage_strategy(),
    )
    @settings(max_examples=100)
    def test_stage_description_not_empty(
        self,
        analysis_status: str,
        embeddings_status: str,
        embeddings_stage: str | None,
        semantic_cache_status: str,
        ai_scan_status: str,
        ai_scan_stage: str | None,
    ):
        """
        Property: For any combination of track statuses, the computed
        overall_stage SHALL return a non-empty string.

        **Feature: parallel-analysis-pipeline, Property 7: Combined Stage Description**
        **Validates: Requirements 3.1**
        """
        stage = compute_overall_stage_parallel(
            analysis_status=analysis_status,
            embeddings_status=embeddings_status,
            embeddings_stage=embeddings_stage,
            semantic_cache_status=semantic_cache_status,
            ai_scan_status=ai_scan_status,
            ai_scan_stage=ai_scan_stage,
        )

        assert stage, "Stage description should not be empty"
        assert len(stage) > 0, "Stage description should have content"

    @given(
        embeddings_stage=embeddings_stage_strategy(),
        ai_scan_stage=ai_scan_stage_strategy(),
    )
    @settings(max_examples=50)
    def test_multiple_running_tracks_use_bullet_separator(
        self,
        embeddings_stage: str | None,
        ai_scan_stage: str | None,
    ):
        """
        Property: For any state where multiple tracks are running,
        the computed overall_stage SHALL contain descriptions for all
        running tracks separated by bullet (•).

        **Feature: parallel-analysis-pipeline, Property 7: Combined Stage Description**
        **Validates: Requirements 3.1, 3.3**
        """
        # All three tracks running
        stage = compute_overall_stage_parallel(
            analysis_status="running",
            embeddings_status="running",
            embeddings_stage=embeddings_stage,
            semantic_cache_status="pending",
            ai_scan_status="running",
            ai_scan_stage=ai_scan_stage,
        )

        # Property: Multiple running tracks should be separated by bullet
        assert "•" in stage, \
            f"Expected bullet separator in stage description: '{stage}'"

    @given(
        embeddings_stage=embeddings_stage_strategy(),
        ai_scan_stage=ai_scan_stage_strategy(),
    )
    @settings(max_examples=50)
    def test_completed_tracks_show_checkmark(
        self,
        embeddings_stage: str | None,
        ai_scan_stage: str | None,
    ):
        """
        Property: For any state where a track is completed while others run,
        the computed overall_stage SHALL indicate the completed track with checkmark.

        **Feature: parallel-analysis-pipeline, Property 7: Combined Stage Description**
        **Validates: Requirements 3.2**
        """
        # Analysis completed, others running
        stage = compute_overall_stage_parallel(
            analysis_status="completed",
            embeddings_status="running",
            embeddings_stage=embeddings_stage,
            semantic_cache_status="pending",
            ai_scan_status="running",
            ai_scan_stage=ai_scan_stage,
        )

        # Property: Completed track should show checkmark
        assert "✓" in stage, \
            f"Expected checkmark for completed track in stage description: '{stage}'"


# =============================================================================
# Property Tests: Terminal State Completion (Property 8)
# =============================================================================


class TestTerminalStateCompletionProperty:
    """
    Property tests for terminal state completion.

    **Feature: parallel-analysis-pipeline, Property 8: Terminal State Completion**
    **Validates: Requirements 4.1, 4.2, 4.3, 4.4**
    """

    @given(
        analysis_terminal=st.sampled_from(["completed", "failed"]),
        embeddings_terminal=st.sampled_from(["completed", "failed"]),
        semantic_terminal=st.sampled_from(["completed", "failed"]),
        ai_scan_terminal=st.sampled_from(["completed", "failed", "skipped"]),
    )
    @settings(max_examples=100)
    def test_is_complete_true_for_all_terminal_combinations(
        self,
        analysis_terminal: str,
        embeddings_terminal: str,
        semantic_terminal: str,
        ai_scan_terminal: str,
    ):
        """
        Property: For any combination where all tracks are in terminal states
        (completed/failed/skipped), is_complete SHALL return True regardless
        of which specific terminal state each track is in.

        **Feature: parallel-analysis-pipeline, Property 8: Terminal State Completion**
        **Validates: Requirements 4.1, 4.2, 4.3, 4.4**
        """
        is_complete = compute_is_complete_parallel(
            analysis_status=analysis_terminal,
            embeddings_status=embeddings_terminal,
            semantic_cache_status=semantic_terminal,
            ai_scan_status=ai_scan_terminal,
        )

        assert is_complete is True, \
            f"Expected is_complete=True for terminal states " \
            f"(analysis={analysis_terminal}, embeddings={embeddings_terminal}, " \
            f"semantic={semantic_terminal}, ai_scan={ai_scan_terminal})"

    @given(
        analysis_status=analysis_status_strategy(),
        embeddings_status=embeddings_status_strategy(),
        semantic_cache_status=semantic_cache_status_strategy(),
        ai_scan_status=ai_scan_status_strategy(),
    )
    @settings(max_examples=100)
    def test_is_complete_false_when_any_non_terminal(
        self,
        analysis_status: str,
        embeddings_status: str,
        semantic_cache_status: str,
        ai_scan_status: str,
    ):
        """
        Property: For any combination where at least one track is NOT in
        a terminal state, is_complete SHALL return False.

        **Feature: parallel-analysis-pipeline, Property 8: Terminal State Completion**
        **Validates: Requirements 4.4**
        """
        terminal_states = ("completed", "failed", "skipped")

        # Check if all terminal
        all_terminal = (
            analysis_status in terminal_states and
            embeddings_status in terminal_states and
            semantic_cache_status in terminal_states and
            ai_scan_status in terminal_states
        )

        # Skip if all terminal (that case is tested separately)
        assume(not all_terminal)

        is_complete = compute_is_complete_parallel(
            analysis_status=analysis_status,
            embeddings_status=embeddings_status,
            semantic_cache_status=semantic_cache_status,
            ai_scan_status=ai_scan_status,
        )

        assert is_complete is False, \
            f"Expected is_complete=False when not all terminal " \
            f"(analysis={analysis_status}, embeddings={embeddings_status}, " \
            f"semantic={semantic_cache_status}, ai_scan={ai_scan_status})"


# =============================================================================
# Unit Tests: Edge Cases
# =============================================================================


class TestParallelProgressEdgeCases:
    """Unit tests for edge cases in parallel progress calculation."""

    def test_all_pending_returns_zero(self):
        """Test that all pending tracks return 0% progress."""
        progress = compute_overall_progress_parallel(
            analysis_status="pending",
            analysis_progress=0,
            embeddings_status="pending",
            embeddings_progress=0,
            semantic_cache_status="pending",
            ai_scan_status="pending",
            ai_scan_progress=0,
        )
        assert progress == 0

    def test_all_completed_returns_100(self):
        """Test that all completed tracks return 100% progress."""
        progress = compute_overall_progress_parallel(
            analysis_status="completed",
            analysis_progress=100,
            embeddings_status="completed",
            embeddings_progress=100,
            semantic_cache_status="completed",
            ai_scan_status="completed",
            ai_scan_progress=100,
        )
        assert progress == 100

    def test_mixed_terminal_states_returns_100(self):
        """Test that mixed terminal states (completed/failed/skipped) return 100%."""
        progress = compute_overall_progress_parallel(
            analysis_status="completed",
            analysis_progress=100,
            embeddings_status="failed",
            embeddings_progress=50,
            semantic_cache_status="failed",
            ai_scan_status="skipped",
            ai_scan_progress=0,
        )
        assert progress == 100

    def test_partial_failure_shows_partial_results(self):
        """
        Test that partial failure scenarios allow partial results.

        **Validates: Requirements 4.1, 4.2, 4.3**
        """
        # Static Analysis fails, others succeed
        is_complete = compute_is_complete_parallel(
            analysis_status="failed",
            embeddings_status="completed",
            semantic_cache_status="completed",
            ai_scan_status="completed",
        )
        assert is_complete is True, "Should be complete even with failed analysis"

        # Embeddings fails, others succeed
        is_complete = compute_is_complete_parallel(
            analysis_status="completed",
            embeddings_status="failed",
            semantic_cache_status="failed",  # Semantic cache also fails if embeddings fails
            ai_scan_status="completed",
        )
        assert is_complete is True, "Should be complete even with failed embeddings"

        # AI Scan fails, others succeed
        is_complete = compute_is_complete_parallel(
            analysis_status="completed",
            embeddings_status="completed",
            semantic_cache_status="completed",
            ai_scan_status="failed",
        )
        assert is_complete is True, "Should be complete even with failed AI scan"


class TestParallelStageEdgeCases:
    """Unit tests for edge cases in parallel stage description."""

    def test_all_complete_shows_complete_message(self):
        """Test that all complete tracks show completion message."""
        stage = compute_overall_stage_parallel(
            analysis_status="completed",
            embeddings_status="completed",
            embeddings_stage="completed",
            semantic_cache_status="completed",
            ai_scan_status="completed",
            ai_scan_stage="completed",
        )
        assert "complete" in stage.lower()

    def test_failed_tracks_show_failure_indicator(self):
        """Test that failed tracks show failure indicator."""
        stage = compute_overall_stage_parallel(
            analysis_status="failed",
            embeddings_status="completed",
            embeddings_stage="completed",
            semantic_cache_status="completed",
            ai_scan_status="completed",
            ai_scan_stage="completed",
        )
        assert "✗" in stage or "fail" in stage.lower()

    def test_skipped_ai_scan_shows_skipped(self):
        """Test that skipped AI scan shows skipped status."""
        stage = compute_overall_stage_parallel(
            analysis_status="completed",
            embeddings_status="completed",
            embeddings_stage="completed",
            semantic_cache_status="completed",
            ai_scan_status="skipped",
            ai_scan_stage=None,
        )
        # Should show complete or skipped
        assert "complete" in stage.lower() or "skipped" in stage.lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
