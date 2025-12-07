"""Property-based tests for parallel task dispatch from API endpoint.

Tests the trigger_analysis endpoint which orchestrates parallel dispatch
of Static Analysis, Embeddings, and AI Scan tasks.

**Feature: parallel-analysis-pipeline**
**Validates: Requirements 1.1, 1.2, 1.4**
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st


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


def valid_branch_name() -> st.SearchStrategy[str]:
    """Generate valid Git branch names."""
    return st.text(
        alphabet="abcdefghijklmnopqrstuvwxyz0123456789-_/",
        min_size=1,
        max_size=50,
    ).filter(lambda x: not x.startswith('/') and not x.endswith('/'))


# =============================================================================
# Property Tests: Parallel Task Dispatch
# =============================================================================


class TestParallelTaskDispatchProperty:
    """
    Property tests for parallel task dispatch.
    
    **Feature: parallel-analysis-pipeline, Property 1: Parallel Task Dispatch**
    **Validates: Requirements 1.1, 1.2**
    """

    @given(
        repository_id=valid_uuid(),
        user_id=valid_uuid(),
        commit_sha=valid_commit_sha(),
        branch=valid_branch_name(),
        ai_scan_enabled=st.booleans(),
    )
    @settings(max_examples=100, deadline=None)
    @pytest.mark.asyncio
    async def test_all_statuses_set_to_pending_on_creation(
        self,
        repository_id: uuid.UUID,
        user_id: uuid.UUID,
        commit_sha: str,
        branch: str,
        ai_scan_enabled: bool,
    ):
        """
        Property: For any analysis creation, the API endpoint SHALL set
        analysis_status, embeddings_status, and ai_scan_status to "pending"
        (or "skipped" for ai_scan if disabled) before dispatching tasks.
        
        **Feature: parallel-analysis-pipeline, Property 1: Parallel Task Dispatch**
        **Validates: Requirements 1.2**
        """
        from app.api.v1.analyses import trigger_analysis, TriggerAnalysisRequest
        from app.models.analysis import Analysis
        
        # Track what Analysis was created with
        captured_analysis = {}
        
        def capture_analysis_add(analysis):
            captured_analysis['status'] = analysis.status
            captured_analysis['embeddings_status'] = analysis.embeddings_status
            captured_analysis['ai_scan_status'] = analysis.ai_scan_status
            captured_analysis['commit_sha'] = analysis.commit_sha
        
        # Create mock repository
        mock_repository = MagicMock()
        mock_repository.id = repository_id
        mock_repository.owner_id = user_id
        mock_repository.is_active = True
        mock_repository.default_branch = "main"
        mock_repository.full_name = "owner/repo"
        
        # Create mock user
        mock_user = MagicMock()
        mock_user.id = user_id
        mock_user.access_token_encrypted = None
        
        # Create mock database session
        mock_db = AsyncMock()
        
        # First execute returns repository (for access check)
        # Second execute returns repository (for lock)
        # Third execute returns empty list (no existing analyses)
        mock_result_repo = MagicMock()
        mock_result_repo.scalar_one_or_none.return_value = mock_repository
        
        mock_result_lock = MagicMock()
        mock_result_lock.scalar_one_or_none.return_value = mock_repository
        
        mock_result_analyses = MagicMock()
        mock_result_analyses.scalars.return_value.all.return_value = []
        
        mock_db.execute.side_effect = [
            mock_result_repo,  # Repository access check
            mock_result_lock,  # Repository lock
            mock_result_analyses,  # Existing analyses check
        ]
        
        # Capture the analysis when added
        def mock_add(obj):
            if isinstance(obj, Analysis):
                capture_analysis_add(obj)
        
        mock_db.add = mock_add
        mock_db.commit = AsyncMock()
        
        # Mock refresh to set the analysis ID
        async def mock_refresh(obj):
            obj.id = uuid.uuid4()
        mock_db.refresh = mock_refresh
        
        # Mock Celery tasks
        mock_analyze_task = MagicMock()
        mock_analyze_task.id = "task-1"
        
        mock_embeddings_task = MagicMock()
        mock_embeddings_task.id = "task-2"
        
        mock_ai_scan_task = MagicMock()
        mock_ai_scan_task.id = "task-3"
        
        # Patch settings and tasks
        with patch('app.api.v1.analyses.settings') as mock_settings, \
             patch('app.api.v1.analyses.analyze_repository') as mock_analyze, \
             patch('app.api.v1.analyses.generate_embeddings_parallel') as mock_embeddings, \
             patch('app.api.v1.analyses.run_ai_scan') as mock_ai_scan, \
             patch('app.api.v1.analyses.publish_analysis_progress'):
            
            mock_settings.ai_scan_enabled = ai_scan_enabled
            mock_analyze.delay.return_value = mock_analyze_task
            mock_embeddings.delay.return_value = mock_embeddings_task
            mock_ai_scan.delay.return_value = mock_ai_scan_task
            
            # Create request body
            body = TriggerAnalysisRequest(branch=branch, commit_sha=commit_sha)
            
            # Call the endpoint
            result = await trigger_analysis(
                repository_id=repository_id,
                db=mock_db,
                user=mock_user,
                body=body,
            )
        
        # Property: analysis_status MUST be "pending"
        assert captured_analysis['status'] == "pending", \
            f"Expected analysis_status='pending', got '{captured_analysis['status']}'"
        
        # Property: embeddings_status MUST be "pending"
        assert captured_analysis['embeddings_status'] == "pending", \
            f"Expected embeddings_status='pending', got '{captured_analysis['embeddings_status']}'"
        
        # Property: ai_scan_status MUST be "pending" if enabled, "skipped" if disabled
        expected_ai_scan_status = "pending" if ai_scan_enabled else "skipped"
        assert captured_analysis['ai_scan_status'] == expected_ai_scan_status, \
            f"Expected ai_scan_status='{expected_ai_scan_status}', got '{captured_analysis['ai_scan_status']}'"
        
        # Property: commit_sha MUST be stored
        assert captured_analysis['commit_sha'] == commit_sha, \
            f"Expected commit_sha='{commit_sha}', got '{captured_analysis['commit_sha']}'"

    @given(
        repository_id=valid_uuid(),
        user_id=valid_uuid(),
        commit_sha=valid_commit_sha(),
        ai_scan_enabled=st.booleans(),
    )
    @settings(max_examples=100, deadline=None)
    @pytest.mark.asyncio
    async def test_all_three_tasks_dispatched_when_enabled(
        self,
        repository_id: uuid.UUID,
        user_id: uuid.UUID,
        commit_sha: str,
        ai_scan_enabled: bool,
    ):
        """
        Property: For any analysis creation, the API endpoint SHALL dispatch
        Static Analysis, Embeddings, and AI Scan tasks (if enabled).
        
        **Feature: parallel-analysis-pipeline, Property 1: Parallel Task Dispatch**
        **Validates: Requirements 1.1, 1.4**
        """
        from app.api.v1.analyses import trigger_analysis, TriggerAnalysisRequest
        from app.models.analysis import Analysis
        
        # Create mock repository
        mock_repository = MagicMock()
        mock_repository.id = repository_id
        mock_repository.owner_id = user_id
        mock_repository.is_active = True
        mock_repository.default_branch = "main"
        mock_repository.full_name = "owner/repo"
        
        # Create mock user
        mock_user = MagicMock()
        mock_user.id = user_id
        mock_user.access_token_encrypted = None
        
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
        
        async def mock_refresh(obj):
            obj.id = uuid.uuid4()
        mock_db.refresh = mock_refresh
        
        # Mock Celery tasks
        mock_analyze_task = MagicMock()
        mock_analyze_task.id = "task-1"
        
        mock_embeddings_task = MagicMock()
        mock_embeddings_task.id = "task-2"
        
        mock_ai_scan_task = MagicMock()
        mock_ai_scan_task.id = "task-3"
        
        with patch('app.api.v1.analyses.settings') as mock_settings, \
             patch('app.api.v1.analyses.analyze_repository') as mock_analyze, \
             patch('app.api.v1.analyses.generate_embeddings_parallel') as mock_embeddings, \
             patch('app.api.v1.analyses.run_ai_scan') as mock_ai_scan, \
             patch('app.api.v1.analyses.publish_analysis_progress'):
            
            mock_settings.ai_scan_enabled = ai_scan_enabled
            mock_analyze.delay.return_value = mock_analyze_task
            mock_embeddings.delay.return_value = mock_embeddings_task
            mock_ai_scan.delay.return_value = mock_ai_scan_task
            
            body = TriggerAnalysisRequest(commit_sha=commit_sha)
            
            result = await trigger_analysis(
                repository_id=repository_id,
                db=mock_db,
                user=mock_user,
                body=body,
            )
        
        # Property: analyze_repository.delay() MUST be called
        mock_analyze.delay.assert_called_once()
        call_kwargs = mock_analyze.delay.call_args.kwargs
        assert call_kwargs['repository_id'] == str(repository_id)
        assert call_kwargs['commit_sha'] == commit_sha
        
        # Property: generate_embeddings_parallel.delay() MUST be called
        mock_embeddings.delay.assert_called_once()
        call_kwargs = mock_embeddings.delay.call_args.kwargs
        assert call_kwargs['repository_id'] == str(repository_id)
        assert call_kwargs['commit_sha'] == commit_sha
        
        # Property: run_ai_scan.delay() MUST be called if enabled, NOT called if disabled
        if ai_scan_enabled:
            mock_ai_scan.delay.assert_called_once()
        else:
            mock_ai_scan.delay.assert_not_called()


# =============================================================================
# Property Tests: Config-Based Dispatch
# =============================================================================


class TestConfigBasedDispatchProperty:
    """
    Property tests for config-based task dispatch.
    
    **Feature: parallel-analysis-pipeline, Property 3: Config-Based Dispatch**
    **Validates: Requirements 1.4**
    """

    @given(
        repository_id=valid_uuid(),
        user_id=valid_uuid(),
        commit_sha=valid_commit_sha(),
    )
    @settings(max_examples=50, deadline=None)
    @pytest.mark.asyncio
    async def test_ai_scan_skipped_when_disabled(
        self,
        repository_id: uuid.UUID,
        user_id: uuid.UUID,
        commit_sha: str,
    ):
        """
        Property: For any analysis creation with AI scan disabled,
        ai_scan_status SHALL be "skipped" and run_ai_scan SHALL NOT be dispatched.
        
        **Feature: parallel-analysis-pipeline, Property 3: Config-Based Dispatch**
        **Validates: Requirements 1.4**
        """
        from app.api.v1.analyses import trigger_analysis, TriggerAnalysisRequest
        from app.models.analysis import Analysis
        
        captured_analysis = {}
        
        def capture_analysis_add(analysis):
            if isinstance(analysis, Analysis):
                captured_analysis['ai_scan_status'] = analysis.ai_scan_status
        
        mock_repository = MagicMock()
        mock_repository.id = repository_id
        mock_repository.owner_id = user_id
        mock_repository.is_active = True
        mock_repository.default_branch = "main"
        mock_repository.full_name = "owner/repo"
        
        mock_user = MagicMock()
        mock_user.id = user_id
        mock_user.access_token_encrypted = None
        
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
        
        mock_db.add = capture_analysis_add
        mock_db.commit = AsyncMock()
        
        async def mock_refresh(obj):
            obj.id = uuid.uuid4()
        mock_db.refresh = mock_refresh
        
        mock_analyze_task = MagicMock()
        mock_analyze_task.id = "task-1"
        
        with patch('app.api.v1.analyses.settings') as mock_settings, \
             patch('app.api.v1.analyses.analyze_repository') as mock_analyze, \
             patch('app.api.v1.analyses.generate_embeddings_parallel') as mock_embeddings, \
             patch('app.api.v1.analyses.run_ai_scan') as mock_ai_scan, \
             patch('app.api.v1.analyses.publish_analysis_progress'):
            
            # AI scan is DISABLED
            mock_settings.ai_scan_enabled = False
            mock_analyze.delay.return_value = mock_analyze_task
            mock_embeddings.delay.return_value = MagicMock()
            
            body = TriggerAnalysisRequest(commit_sha=commit_sha)
            
            await trigger_analysis(
                repository_id=repository_id,
                db=mock_db,
                user=mock_user,
                body=body,
            )
        
        # Property: ai_scan_status MUST be "skipped" when disabled
        assert captured_analysis['ai_scan_status'] == "skipped", \
            f"Expected ai_scan_status='skipped', got '{captured_analysis['ai_scan_status']}'"
        
        # Property: run_ai_scan.delay() MUST NOT be called when disabled
        mock_ai_scan.delay.assert_not_called()


# =============================================================================
# Unit Tests: Task Dispatch Verification
# =============================================================================


class TestTaskDispatchVerification:
    """
    Unit tests for verifying task dispatch behavior.
    
    **Feature: parallel-analysis-pipeline**
    """

    @pytest.mark.asyncio
    async def test_all_tasks_receive_correct_parameters(self):
        """
        Test that all dispatched tasks receive the correct parameters.
        
        **Feature: parallel-analysis-pipeline**
        **Validates: Requirements 1.1, 1.3**
        """
        from app.api.v1.analyses import trigger_analysis, TriggerAnalysisRequest
        from app.models.analysis import Analysis
        
        repository_id = uuid.uuid4()
        user_id = uuid.uuid4()
        commit_sha = "a" * 40
        
        mock_repository = MagicMock()
        mock_repository.id = repository_id
        mock_repository.owner_id = user_id
        mock_repository.is_active = True
        mock_repository.default_branch = "main"
        mock_repository.full_name = "owner/repo"
        
        mock_user = MagicMock()
        mock_user.id = user_id
        mock_user.access_token_encrypted = None
        
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
        
        mock_analyze_task = MagicMock()
        mock_analyze_task.id = "task-1"
        
        with patch('app.api.v1.analyses.settings') as mock_settings, \
             patch('app.api.v1.analyses.analyze_repository') as mock_analyze, \
             patch('app.api.v1.analyses.generate_embeddings_parallel') as mock_embeddings, \
             patch('app.api.v1.analyses.run_ai_scan') as mock_ai_scan, \
             patch('app.api.v1.analyses.publish_analysis_progress'):
            
            mock_settings.ai_scan_enabled = True
            mock_analyze.delay.return_value = mock_analyze_task
            mock_embeddings.delay.return_value = MagicMock()
            mock_ai_scan.delay.return_value = MagicMock()
            
            body = TriggerAnalysisRequest(commit_sha=commit_sha)
            
            await trigger_analysis(
                repository_id=repository_id,
                db=mock_db,
                user=mock_user,
                body=body,
            )
        
        # Verify analyze_repository parameters
        analyze_call = mock_analyze.delay.call_args
        assert analyze_call.kwargs['repository_id'] == str(repository_id)
        assert analyze_call.kwargs['analysis_id'] == str(created_analysis_id)
        assert analyze_call.kwargs['commit_sha'] == commit_sha
        assert analyze_call.kwargs['triggered_by'] == "manual"
        
        # Verify generate_embeddings_parallel parameters
        embeddings_call = mock_embeddings.delay.call_args
        assert embeddings_call.kwargs['repository_id'] == str(repository_id)
        assert embeddings_call.kwargs['analysis_id'] == str(created_analysis_id)
        assert embeddings_call.kwargs['commit_sha'] == commit_sha
        
        # Verify run_ai_scan parameters
        ai_scan_call = mock_ai_scan.delay.call_args
        assert ai_scan_call.kwargs['analysis_id'] == str(created_analysis_id)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
