"""Integration tests for full parallel analysis pipeline.

Tests the complete parallel execution of Static Analysis, Embeddings, and AI Scan
tracks, verifying they start simultaneously and handle partial failures correctly.

**Feature: parallel-analysis-pipeline**
**Validates: Requirements 1.1, 4.1, 4.2, 4.3**
"""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.schemas.analysis import (
    compute_is_complete_parallel,
    compute_overall_progress_parallel,
    compute_overall_stage_parallel,
)

# =============================================================================
# Hypothesis Strategies
# =============================================================================


def valid_commit_sha() -> st.SearchStrategy[str]:
    """Generate valid Git commit SHAs (40 hex characters)."""
    return st.text(
        alphabet="0123456789abcdef",
        min_size=40,
        max_size=40,
    )


def valid_uuid() -> st.SearchStrategy[uuid.UUID]:
    """Generate valid UUIDs."""
    return st.uuids()


def progress_strategy() -> st.SearchStrategy[int]:
    """Generate valid progress values (0-100)."""
    return st.integers(min_value=0, max_value=100)


# =============================================================================
# Test Fixtures
# =============================================================================


def create_mock_analysis(
    analysis_id: uuid.UUID | None = None,
    repository_id: uuid.UUID | None = None,
    commit_sha: str = "a" * 40,
    status: str = "pending",
    embeddings_status: str = "pending",
    embeddings_progress: int = 0,
    embeddings_stage: str | None = None,
    semantic_cache_status: str = "pending",
    ai_scan_status: str = "pending",
    ai_scan_progress: int = 0,
    ai_scan_stage: str | None = None,
    vci_score: float | None = None,
    grade: str | None = None,
    vectors_count: int = 0,
    semantic_cache: dict | None = None,
    ai_scan_cache: dict | None = None,
) -> MagicMock:
    """Create a mock Analysis object for testing."""
    mock = MagicMock()
    mock.id = analysis_id or uuid.uuid4()
    mock.repository_id = repository_id or uuid.uuid4()
    mock.commit_sha = commit_sha
    mock.status = status
    mock.embeddings_status = embeddings_status
    mock.embeddings_progress = embeddings_progress
    mock.embeddings_stage = embeddings_stage
    mock.semantic_cache_status = semantic_cache_status
    mock.ai_scan_status = ai_scan_status
    mock.ai_scan_progress = ai_scan_progress
    mock.ai_scan_stage = ai_scan_stage
    mock.vci_score = vci_score
    mock.grade = grade
    mock.vectors_count = vectors_count
    mock.semantic_cache = semantic_cache
    mock.ai_scan_cache = ai_scan_cache
    mock.state_updated_at = datetime.now(UTC)
    mock.embeddings_started_at = None
    mock.embeddings_completed_at = None
    mock.ai_scan_started_at = None
    mock.ai_scan_completed_at = None
    mock.embeddings_message = None
    mock.embeddings_error = None
    mock.ai_scan_message = None
    mock.ai_scan_error = None
    return mock


def create_mock_repository(
    repository_id: uuid.UUID | None = None,
    owner_id: uuid.UUID | None = None,
    full_name: str = "owner/repo",
    default_branch: str = "main",
    is_active: bool = True,
) -> MagicMock:
    """Create a mock Repository object for testing."""
    mock = MagicMock()
    mock.id = repository_id or uuid.uuid4()
    mock.owner_id = owner_id or uuid.uuid4()
    mock.full_name = full_name
    mock.default_branch = default_branch
    mock.is_active = is_active
    return mock


def create_mock_user(user_id: uuid.UUID | None = None) -> MagicMock:
    """Create a mock User object for testing."""
    mock = MagicMock()
    mock.id = user_id or uuid.uuid4()
    mock.access_token_encrypted = None
    return mock


# =============================================================================
# Integration Tests: Full Parallel Pipeline (Task 11.1)
# =============================================================================


class TestFullParallelPipelineIntegration:
    """
    Integration tests for the full parallel analysis pipeline.

    Tests that all three tasks (Static Analysis, Embeddings, AI Scan)
    start simultaneously when an analysis is triggered.

    **Feature: parallel-analysis-pipeline**
    **Validates: Requirements 1.1**
    """

    @given(
        repository_id=valid_uuid(),
        user_id=valid_uuid(),
        commit_sha=valid_commit_sha(),
    )
    @settings(max_examples=50, deadline=None)
    @pytest.mark.asyncio
    async def test_all_three_tasks_start_simultaneously(
        self,
        repository_id: uuid.UUID,
        user_id: uuid.UUID,
        commit_sha: str,
    ):
        """
        Test that all three tasks are dispatched simultaneously from API endpoint.

        **Feature: parallel-analysis-pipeline**
        **Validates: Requirements 1.1**

        Property: For any analysis trigger, Static Analysis, Embeddings, and
        AI Scan tasks SHALL all be dispatched before the API returns.
        """
        from app.api.v1.analyses import TriggerAnalysisRequest, trigger_analysis

        # Track task dispatch order
        dispatch_order = []

        def track_analyze_dispatch(**kwargs):
            dispatch_order.append(("analyze_repository", kwargs))
            return MagicMock(id="task-1")

        def track_embeddings_dispatch(**kwargs):
            dispatch_order.append(("generate_embeddings_parallel", kwargs))
            return MagicMock(id="task-2")

        def track_ai_scan_dispatch(**kwargs):
            dispatch_order.append(("run_ai_scan", kwargs))
            return MagicMock(id="task-3")

        # Create mock repository
        mock_repository = create_mock_repository(
            repository_id=repository_id,
            owner_id=user_id,
        )

        # Create mock user
        mock_user = create_mock_user(user_id=user_id)

        # Create mock database session
        mock_db = AsyncMock()

        mock_result_repo = MagicMock()
        mock_result_repo.scalar_one_or_none.return_value = mock_repository

        mock_result_lock = MagicMock()
        mock_result_lock.scalar_one_or_none.return_value = mock_repository

        mock_result_analyses = MagicMock()
        mock_result_analyses.scalars.return_value.all.return_value = []

        mock_db.execute.side_effect = [
            mock_result_repo,
            mock_result_lock,
            mock_result_analyses,
        ]

        mock_db.add = MagicMock()
        mock_db.commit = AsyncMock()

        created_analysis_id = uuid.uuid4()
        async def mock_refresh(obj):
            obj.id = created_analysis_id
        mock_db.refresh = mock_refresh

        with patch('app.api.v1.analyses.settings') as mock_settings, \
             patch('app.api.v1.analyses.analyze_repository') as mock_analyze, \
             patch('app.api.v1.analyses.generate_embeddings_parallel') as mock_embeddings, \
             patch('app.api.v1.analyses.run_ai_scan') as mock_ai_scan, \
             patch('app.api.v1.analyses.publish_analysis_progress'):

            mock_settings.ai_scan_enabled = True
            mock_analyze.delay = track_analyze_dispatch
            mock_embeddings.delay = track_embeddings_dispatch
            mock_ai_scan.delay = track_ai_scan_dispatch

            body = TriggerAnalysisRequest(commit_sha=commit_sha)

            await trigger_analysis(
                repository_id=repository_id,
                db=mock_db,
                user=mock_user,
                body=body,
            )

        # Property: All three tasks MUST be dispatched
        assert len(dispatch_order) == 3, (
            f"Expected 3 tasks dispatched, got {len(dispatch_order)}\n"
            f"Dispatched: {[t[0] for t in dispatch_order]}"
        )

        # Property: All three task types MUST be present
        task_names = {t[0] for t in dispatch_order}
        expected_tasks = {"analyze_repository", "generate_embeddings_parallel", "run_ai_scan"}
        assert task_names == expected_tasks, (
            f"Expected tasks {expected_tasks}, got {task_names}"
        )

        # Property: All tasks MUST receive the same commit_sha
        for task_name, kwargs in dispatch_order:
            if task_name in ("analyze_repository", "generate_embeddings_parallel"):
                assert kwargs.get("commit_sha") == commit_sha, (
                    f"{task_name} received wrong commit_sha: {kwargs.get('commit_sha')}"
                )


# =============================================================================
# Integration Tests: Partial Failure Scenarios (Task 11.1)
# =============================================================================


class TestPartialFailureScenarios:
    """
    Integration tests for partial failure scenarios in parallel pipeline.

    Tests that when one track fails, other tracks can still complete
    and provide partial results.

    **Feature: parallel-analysis-pipeline**
    **Validates: Requirements 4.1, 4.2, 4.3**
    """

    @given(
        analysis_progress=progress_strategy(),
        embeddings_progress=progress_strategy(),
        ai_scan_progress=progress_strategy(),
    )
    @settings(max_examples=100)
    def test_static_analysis_fails_others_succeed(
        self,
        analysis_progress: int,
        embeddings_progress: int,
        ai_scan_progress: int,
    ):
        """
        Test: Static Analysis fails but Embeddings and AI Scan succeed.

        **Feature: parallel-analysis-pipeline**
        **Validates: Requirements 4.1**

        Property: When Static Analysis fails but Embeddings and AI Scan succeed,
        the system SHALL display Embeddings and AI Scan results without VCI score.
        """
        # Scenario: Static Analysis failed, others completed
        is_complete = compute_is_complete_parallel(
            analysis_status="failed",
            embeddings_status="completed",
            semantic_cache_status="completed",
            ai_scan_status="completed",
        )

        progress = compute_overall_progress_parallel(
            analysis_status="failed",
            analysis_progress=analysis_progress,
            embeddings_status="completed",
            embeddings_progress=embeddings_progress,
            semantic_cache_status="completed",
            ai_scan_status="completed",
            ai_scan_progress=ai_scan_progress,
        )

        stage = compute_overall_stage_parallel(
            analysis_status="failed",
            embeddings_status="completed",
            embeddings_stage="completed",
            semantic_cache_status="completed",
            ai_scan_status="completed",
            ai_scan_stage="completed",
        )

        # Property: System should be complete (all tracks in terminal state)
        assert is_complete is True, (
            "System should be complete when all tracks are in terminal states"
        )

        # Property: Progress should be 100% (all terminal)
        assert progress == 100, (
            f"Expected 100% progress when all terminal, got {progress}%"
        )

        # Property: Stage should indicate failure
        assert "✗" in stage or "fail" in stage.lower(), (
            f"Stage should indicate failure: {stage}"
        )

    @given(
        analysis_progress=progress_strategy(),
        embeddings_progress=progress_strategy(),
        ai_scan_progress=progress_strategy(),
    )
    @settings(max_examples=100)
    def test_embeddings_fails_others_succeed(
        self,
        analysis_progress: int,
        embeddings_progress: int,
        ai_scan_progress: int,
    ):
        """
        Test: Embeddings fails but Static Analysis and AI Scan succeed.

        **Feature: parallel-analysis-pipeline**
        **Validates: Requirements 4.2**

        Property: When Embeddings fails but Static Analysis and AI Scan succeed,
        the system SHALL display VCI score and AI Scan results without semantic analysis.
        """
        # Scenario: Embeddings failed (semantic cache also fails), others completed
        is_complete = compute_is_complete_parallel(
            analysis_status="completed",
            embeddings_status="failed",
            semantic_cache_status="failed",  # Semantic cache fails if embeddings fails
            ai_scan_status="completed",
        )

        progress = compute_overall_progress_parallel(
            analysis_status="completed",
            analysis_progress=analysis_progress,
            embeddings_status="failed",
            embeddings_progress=embeddings_progress,
            semantic_cache_status="failed",
            ai_scan_status="completed",
            ai_scan_progress=ai_scan_progress,
        )

        compute_overall_stage_parallel(
            analysis_status="completed",
            embeddings_status="failed",
            embeddings_stage="error",
            semantic_cache_status="failed",
            ai_scan_status="completed",
            ai_scan_stage="completed",
        )

        # Property: System should be complete (all tracks in terminal state)
        assert is_complete is True, (
            "System should be complete when all tracks are in terminal states"
        )

        # Property: Progress should be 100% (all terminal)
        assert progress == 100, (
            f"Expected 100% progress when all terminal, got {progress}%"
        )

    @given(
        analysis_progress=progress_strategy(),
        embeddings_progress=progress_strategy(),
        ai_scan_progress=progress_strategy(),
    )
    @settings(max_examples=100)
    def test_ai_scan_fails_others_succeed(
        self,
        analysis_progress: int,
        embeddings_progress: int,
        ai_scan_progress: int,
    ):
        """
        Test: AI Scan fails but Static Analysis and Embeddings succeed.

        **Feature: parallel-analysis-pipeline**
        **Validates: Requirements 4.3**

        Property: When AI Scan fails but Static Analysis and Embeddings succeed,
        the system SHALL display VCI score and semantic analysis without AI insights.
        """
        # Scenario: AI Scan failed, others completed
        is_complete = compute_is_complete_parallel(
            analysis_status="completed",
            embeddings_status="completed",
            semantic_cache_status="completed",
            ai_scan_status="failed",
        )

        progress = compute_overall_progress_parallel(
            analysis_status="completed",
            analysis_progress=analysis_progress,
            embeddings_status="completed",
            embeddings_progress=embeddings_progress,
            semantic_cache_status="completed",
            ai_scan_status="failed",
            ai_scan_progress=ai_scan_progress,
        )

        compute_overall_stage_parallel(
            analysis_status="completed",
            embeddings_status="completed",
            embeddings_stage="completed",
            semantic_cache_status="completed",
            ai_scan_status="failed",
            ai_scan_stage="error",
        )

        # Property: System should be complete (all tracks in terminal state)
        assert is_complete is True, (
            "System should be complete when all tracks are in terminal states"
        )

        # Property: Progress should be 100% (all terminal)
        assert progress == 100, (
            f"Expected 100% progress when all terminal, got {progress}%"
        )


    def test_all_tracks_fail(self):
        """
        Test: All three tracks fail.

        **Feature: parallel-analysis-pipeline**
        **Validates: Requirements 4.1, 4.2, 4.3**

        Property: When all tracks fail, the system SHALL still be marked complete
        (all in terminal state) with 100% progress.
        """
        is_complete = compute_is_complete_parallel(
            analysis_status="failed",
            embeddings_status="failed",
            semantic_cache_status="failed",
            ai_scan_status="failed",
        )

        progress = compute_overall_progress_parallel(
            analysis_status="failed",
            analysis_progress=50,
            embeddings_status="failed",
            embeddings_progress=30,
            semantic_cache_status="failed",
            ai_scan_status="failed",
            ai_scan_progress=20,
        )

        # Property: System should be complete (all tracks in terminal state)
        assert is_complete is True, (
            "System should be complete when all tracks are in terminal states (even if failed)"
        )

        # Property: Progress should be 100% (all terminal)
        assert progress == 100, (
            f"Expected 100% progress when all terminal, got {progress}%"
        )

    def test_mixed_terminal_states(self):
        """
        Test: Mixed terminal states (completed, failed, skipped).

        **Feature: parallel-analysis-pipeline**
        **Validates: Requirements 4.1, 4.2, 4.3**

        Property: Any combination of terminal states (completed/failed/skipped)
        SHALL result in is_complete=True and progress=100%.
        """
        # Test various combinations
        test_cases = [
            ("completed", "completed", "completed", "skipped"),
            ("completed", "failed", "failed", "skipped"),
            ("failed", "completed", "completed", "skipped"),
            ("completed", "completed", "completed", "failed"),
            ("failed", "failed", "failed", "skipped"),
        ]

        for analysis, embeddings, semantic, ai_scan in test_cases:
            is_complete = compute_is_complete_parallel(
                analysis_status=analysis,
                embeddings_status=embeddings,
                semantic_cache_status=semantic,
                ai_scan_status=ai_scan,
            )

            progress = compute_overall_progress_parallel(
                analysis_status=analysis,
                analysis_progress=100,
                embeddings_status=embeddings,
                embeddings_progress=100,
                semantic_cache_status=semantic,
                ai_scan_status=ai_scan,
                ai_scan_progress=100,
            )

            assert is_complete is True, (
                f"Expected is_complete=True for ({analysis}, {embeddings}, {semantic}, {ai_scan})"
            )
            assert progress == 100, (
                f"Expected progress=100 for ({analysis}, {embeddings}, {semantic}, {ai_scan}), got {progress}"
            )


# =============================================================================
# Integration Tests: Progress Updates During Parallel Execution (Task 11.1)
# =============================================================================


class TestProgressUpdatesDuringParallelExecution:
    """
    Integration tests for progress updates during parallel execution.

    Tests that progress is correctly calculated as tracks progress independently.

    **Feature: parallel-analysis-pipeline**
    **Validates: Requirements 1.1, 4.1, 4.2, 4.3**
    """

    @given(
        analysis_progress=progress_strategy(),
        embeddings_progress=progress_strategy(),
        ai_scan_progress=progress_strategy(),
    )
    @settings(max_examples=100)
    def test_progress_during_all_tracks_running(
        self,
        analysis_progress: int,
        embeddings_progress: int,
        ai_scan_progress: int,
    ):
        """
        Test progress calculation when all three tracks are running.

        **Feature: parallel-analysis-pipeline**
        **Validates: Requirements 1.1**

        Property: When all tracks are running, progress SHALL be the weighted
        sum of track contributions, capped at 95%.
        """
        progress = compute_overall_progress_parallel(
            analysis_status="running",
            analysis_progress=analysis_progress,
            embeddings_status="running",
            embeddings_progress=embeddings_progress,
            semantic_cache_status="pending",
            ai_scan_status="running",
            ai_scan_progress=ai_scan_progress,
        )

        # Property: Progress MUST be between 0 and 95 (capped)
        assert 0 <= progress <= 95, (
            f"Progress {progress} should be between 0 and 95 when not all complete"
        )

        # Property: Progress should increase with track progress
        # Calculate expected contribution
        expected_static = int(analysis_progress * 0.33)
        expected_embeddings = int(embeddings_progress * 0.25)
        expected_ai_scan = int(ai_scan_progress * 0.33)
        expected_total = min(expected_static + expected_embeddings + expected_ai_scan, 95)

        assert progress == expected_total, (
            f"Expected progress {expected_total}, got {progress}"
        )

    def test_progress_as_tracks_complete_sequentially(self):
        """
        Test progress as tracks complete one by one.

        **Feature: parallel-analysis-pipeline**
        **Validates: Requirements 1.1**

        Property: Progress SHALL increase as each track completes.
        """
        # All pending
        progress_0 = compute_overall_progress_parallel(
            analysis_status="pending",
            analysis_progress=0,
            embeddings_status="pending",
            embeddings_progress=0,
            semantic_cache_status="pending",
            ai_scan_status="pending",
            ai_scan_progress=0,
        )

        # Static Analysis completed
        progress_1 = compute_overall_progress_parallel(
            analysis_status="completed",
            analysis_progress=100,
            embeddings_status="running",
            embeddings_progress=50,
            semantic_cache_status="pending",
            ai_scan_status="running",
            ai_scan_progress=50,
        )

        # Static Analysis + Embeddings completed
        progress_2 = compute_overall_progress_parallel(
            analysis_status="completed",
            analysis_progress=100,
            embeddings_status="completed",
            embeddings_progress=100,
            semantic_cache_status="computing",
            ai_scan_status="running",
            ai_scan_progress=75,
        )

        # All completed
        progress_3 = compute_overall_progress_parallel(
            analysis_status="completed",
            analysis_progress=100,
            embeddings_status="completed",
            embeddings_progress=100,
            semantic_cache_status="completed",
            ai_scan_status="completed",
            ai_scan_progress=100,
        )

        # Property: Progress should increase monotonically
        assert progress_0 <= progress_1 <= progress_2 <= progress_3, (
            f"Progress should increase: {progress_0} <= {progress_1} <= {progress_2} <= {progress_3}"
        )

        # Property: Final progress should be 100%
        assert progress_3 == 100, f"Final progress should be 100%, got {progress_3}%"

        # Property: Initial progress should be 0%
        assert progress_0 == 0, f"Initial progress should be 0%, got {progress_0}%"


    def test_stage_description_during_parallel_execution(self):
        """
        Test stage description when multiple tracks are running.

        **Feature: parallel-analysis-pipeline**
        **Validates: Requirements 1.1**

        Property: When multiple tracks are running, stage description SHALL
        show all active tracks separated by bullet (•).
        """
        # All three tracks running
        stage = compute_overall_stage_parallel(
            analysis_status="running",
            embeddings_status="running",
            embeddings_stage="embedding",
            semantic_cache_status="pending",
            ai_scan_status="running",
            ai_scan_stage="scanning",
        )

        # Property: Stage should contain bullet separator
        assert "•" in stage, (
            f"Stage should contain bullet separator when multiple tracks running: {stage}"
        )

        # Two tracks running (one completed)
        stage_partial = compute_overall_stage_parallel(
            analysis_status="completed",
            embeddings_status="running",
            embeddings_stage="indexing",
            semantic_cache_status="pending",
            ai_scan_status="running",
            ai_scan_stage="merging",
        )

        # Property: Stage should show completed track with checkmark
        assert "✓" in stage_partial, (
            f"Stage should show checkmark for completed track: {stage_partial}"
        )

    @given(
        embeddings_progress=progress_strategy(),
        ai_scan_progress=progress_strategy(),
    )
    @settings(max_examples=50)
    def test_progress_cap_prevents_premature_100(
        self,
        embeddings_progress: int,
        ai_scan_progress: int,
    ):
        """
        Test that progress is capped at 95% until all tracks complete.

        **Feature: parallel-analysis-pipeline**
        **Validates: Requirements 1.1**

        Property: Progress SHALL NOT reach 100% until all tracks are in
        terminal states.
        """
        # Even with high progress values, if not all terminal, cap at 95%
        progress = compute_overall_progress_parallel(
            analysis_status="completed",
            analysis_progress=100,
            embeddings_status="completed",
            embeddings_progress=100,
            semantic_cache_status="completed",
            ai_scan_status="running",  # Still running!
            ai_scan_progress=ai_scan_progress,
        )

        # Property: Progress MUST NOT exceed 95% when not all terminal
        assert progress <= 95, (
            f"Progress {progress}% should not exceed 95% when AI scan still running"
        )


# =============================================================================
# Integration Tests: Full Status API with Parallel Progress
# =============================================================================


class TestFullStatusAPIParallelProgress:
    """
    Integration tests for Full Status API with parallel progress calculation.

    **Feature: parallel-analysis-pipeline**
    **Validates: Requirements 1.1, 4.1, 4.2, 4.3**
    """

    @pytest.mark.asyncio
    async def test_full_status_returns_parallel_progress(self):
        """
        Test that Full Status API returns correctly computed parallel progress.

        **Feature: parallel-analysis-pipeline**
        **Validates: Requirements 1.1**
        """
        from app.api.v1.analyses import get_analysis_full_status

        analysis_id = uuid.uuid4()
        repository_id = uuid.uuid4()
        user_id = uuid.uuid4()

        # Create mock analysis with parallel execution state
        mock_analysis = create_mock_analysis(
            analysis_id=analysis_id,
            repository_id=repository_id,
            status="running",
            embeddings_status="running",
            embeddings_progress=50,
            embeddings_stage="embedding",
            semantic_cache_status="pending",
            ai_scan_status="running",
            ai_scan_progress=30,
            ai_scan_stage="scanning",
        )

        # Create mock repository
        mock_repository = create_mock_repository(
            repository_id=repository_id,
            owner_id=user_id,
        )
        mock_analysis.repository = mock_repository

        # Create mock user
        mock_user = create_mock_user(user_id=user_id)

        # Create mock database session
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_analysis
        mock_db.execute.return_value = mock_result

        # Call the endpoint
        response = await get_analysis_full_status(
            analysis_id=analysis_id,
            db=mock_db,
            user=mock_user,
        )

        # Verify response contains parallel progress fields
        assert response.analysis_status == "running"
        assert response.embeddings_status.value == "running"
        assert response.ai_scan_status.value == "running"

        # Verify overall progress is computed using parallel formula
        assert 0 <= response.overall_progress <= 95, (
            f"Overall progress {response.overall_progress} should be between 0 and 95"
        )

        # Verify stage shows parallel execution
        assert "•" in response.overall_stage, (
            f"Stage should show parallel execution: {response.overall_stage}"
        )

        # Verify is_complete is False (still running)
        assert response.is_complete is False

    @pytest.mark.asyncio
    async def test_full_status_shows_partial_failure(self):
        """
        Test that Full Status API correctly shows partial failure state.

        **Feature: parallel-analysis-pipeline**
        **Validates: Requirements 4.1, 4.2, 4.3**
        """
        from app.api.v1.analyses import get_analysis_full_status

        analysis_id = uuid.uuid4()
        repository_id = uuid.uuid4()
        user_id = uuid.uuid4()

        # Create mock analysis with partial failure
        mock_analysis = create_mock_analysis(
            analysis_id=analysis_id,
            repository_id=repository_id,
            status="completed",
            vci_score=75.5,
            grade="B",
            embeddings_status="completed",
            embeddings_progress=100,
            semantic_cache_status="completed",
            semantic_cache={"architecture_health": {"overall_score": 80}},
            ai_scan_status="failed",  # AI Scan failed
            ai_scan_progress=50,
            ai_scan_stage="error",
        )
        mock_analysis.ai_scan_error = "LLM API timeout"

        # Create mock repository
        mock_repository = create_mock_repository(
            repository_id=repository_id,
            owner_id=user_id,
        )
        mock_analysis.repository = mock_repository

        # Create mock user
        mock_user = create_mock_user(user_id=user_id)

        # Create mock database session
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_analysis
        mock_db.execute.return_value = mock_result

        # Call the endpoint
        response = await get_analysis_full_status(
            analysis_id=analysis_id,
            db=mock_db,
            user=mock_user,
        )

        # Verify partial results are available
        assert response.vci_score == 75.5
        assert response.has_semantic_cache is True

        # Verify AI scan failure is shown
        assert response.ai_scan_status.value == "failed"
        assert response.ai_scan_error == "LLM API timeout"

        # Verify system is complete (all terminal)
        assert response.is_complete is True
        assert response.overall_progress == 100


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
