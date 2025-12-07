"""Property-based tests for parallel embeddings task.

Tests the generate_embeddings_parallel task which clones the repository
independently using the commit_sha from the Analysis record.

**Feature: parallel-analysis-pipeline**
**Validates: Requirements 5.1, 5.4**
"""

from unittest.mock import MagicMock, patch

from hypothesis import given, settings
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


def valid_uuid_str() -> st.SearchStrategy[str]:
    """Generate valid UUID strings."""
    return st.uuids().map(str)


def valid_repo_url() -> st.SearchStrategy[str]:
    """Generate valid GitHub repository URLs."""
    return st.text(
        alphabet="abcdefghijklmnopqrstuvwxyz0123456789-_",
        min_size=3,
        max_size=30,
    ).map(lambda name: f"https://github.com/owner/{name}")


# =============================================================================
# Property Tests: Independent Cloning with Commit SHA
# =============================================================================


class TestIndependentCloningProperty:
    """
    Property tests for independent cloning with commit SHA.

    **Feature: parallel-analysis-pipeline, Property 9: Independent Cloning with Commit SHA**
    **Validates: Requirements 5.1, 5.4**
    """

    @given(
        repository_id=valid_uuid_str(),
        analysis_id=valid_uuid_str(),
        commit_sha=valid_commit_sha(),
    )
    @settings(max_examples=100, deadline=None)
    def test_parallel_embeddings_clones_with_correct_commit_sha(
        self,
        repository_id: str,
        analysis_id: str,
        commit_sha: str,
    ):
        """
        Property: For any analysis, generate_embeddings_parallel SHALL clone
        the repository using the commit_sha provided as parameter.

        **Feature: parallel-analysis-pipeline, Property 9: Independent Cloning with Commit SHA**
        **Validates: Requirements 5.1, 5.4**
        """
        # Mock all external dependencies
        mock_repo_analyzer = MagicMock()
        mock_repo_analyzer.__enter__ = MagicMock(return_value=mock_repo_analyzer)
        mock_repo_analyzer.__exit__ = MagicMock(return_value=False)
        mock_repo_analyzer.clone.return_value = "/tmp/test_repo"

        repo_url = f"https://github.com/test/repo-{repository_id[:8]}"
        access_token = "test_token"

        # Track what RepoAnalyzer was called with
        captured_args = {}

        def capture_repo_analyzer(*args, **kwargs):
            captured_args['args'] = args
            captured_args['kwargs'] = kwargs
            return mock_repo_analyzer

        # Patch at the source modules where the imports happen
        with patch('app.workers.helpers.get_repo_url', return_value=(repo_url, access_token)) as mock_get_repo_url, \
             patch('app.services.repo_analyzer.RepoAnalyzer', side_effect=capture_repo_analyzer), \
             patch('app.workers.helpers.collect_files_for_embedding', return_value=[]), \
             patch('app.workers.embeddings._update_embeddings_state'), \
             patch('app.workers.embeddings.publish_embedding_progress'):

            # Import after patching
            from app.workers.embeddings import generate_embeddings_parallel

            # Patch the task's update_state method on the task object itself
            generate_embeddings_parallel.update_state = MagicMock()

            # Call the task synchronously using apply()
            generate_embeddings_parallel.apply(
                args=[repository_id, analysis_id, commit_sha],
            )

            # Verify RepoAnalyzer was instantiated with correct commit_sha
            assert 'kwargs' in captured_args, "RepoAnalyzer was not called"
            assert captured_args['kwargs'].get('commit_sha') == commit_sha, \
                f"Expected commit_sha={commit_sha}, got {captured_args['kwargs'].get('commit_sha')}"

            # Verify the repo_url was passed correctly
            assert captured_args['args'][0] == repo_url, \
                f"Expected repo_url={repo_url}, got {captured_args['args'][0]}"

            # Verify get_repo_url was called with correct repository_id
            mock_get_repo_url.assert_called_once_with(repository_id)

    @given(
        repository_id=valid_uuid_str(),
        analysis_id=valid_uuid_str(),
        commit_sha=valid_commit_sha(),
    )
    @settings(max_examples=100, deadline=None)
    def test_parallel_embeddings_uses_same_commit_sha_for_all_operations(
        self,
        repository_id: str,
        analysis_id: str,
        commit_sha: str,
    ):
        """
        Property: For any analysis, the commit_sha used for cloning SHALL be
        the same commit_sha stored in the result payload.

        **Feature: parallel-analysis-pipeline, Property 9: Independent Cloning with Commit SHA**
        **Validates: Requirements 5.4**
        """
        mock_repo_analyzer = MagicMock()
        mock_repo_analyzer.__enter__ = MagicMock(return_value=mock_repo_analyzer)
        mock_repo_analyzer.__exit__ = MagicMock(return_value=False)
        mock_repo_analyzer.clone.return_value = "/tmp/test_repo"

        repo_url = "https://github.com/test/repo"

        # Patch at the source modules where the imports happen
        with patch('app.workers.helpers.get_repo_url', return_value=(repo_url, None)), \
             patch('app.services.repo_analyzer.RepoAnalyzer', return_value=mock_repo_analyzer), \
             patch('app.workers.helpers.collect_files_for_embedding', return_value=[]), \
             patch('app.workers.embeddings._update_embeddings_state'), \
             patch('app.workers.embeddings.publish_embedding_progress'):

            from app.workers.embeddings import generate_embeddings_parallel

            # Patch the task's update_state method on the task object itself
            generate_embeddings_parallel.update_state = MagicMock()

            # Call the task synchronously using apply()
            async_result = generate_embeddings_parallel.apply(
                args=[repository_id, analysis_id, commit_sha],
            )
            result = async_result.result

            # Verify the result contains the same commit_sha
            assert result["commit_sha"] == commit_sha
            assert result["repository_id"] == repository_id
            assert result["analysis_id"] == analysis_id


# =============================================================================
# Unit Tests: Helper Functions
# =============================================================================


class TestHelperFunctions:
    """
    Unit tests for shared helper functions.

    **Feature: parallel-analysis-pipeline**
    **Validates: Requirements 5.1, 5.2, 5.3**
    """

    def test_get_repo_url_function_exists(self):
        """Test that get_repo_url function is importable from helpers."""
        from app.workers.helpers import get_repo_url
        assert callable(get_repo_url)

    def test_collect_files_for_embedding_function_exists(self):
        """Test that collect_files_for_embedding function is importable from helpers."""
        from app.workers.helpers import collect_files_for_embedding
        assert callable(collect_files_for_embedding)

    def test_generate_embeddings_parallel_task_exists(self):
        """Test that generate_embeddings_parallel task is registered."""
        from app.workers.embeddings import generate_embeddings_parallel
        assert generate_embeddings_parallel is not None
        assert hasattr(generate_embeddings_parallel, 'delay')

    def test_collect_files_for_embedding_returns_empty_for_none_path(self):
        """Test that collect_files_for_embedding returns empty list for None path."""
        from app.workers.helpers import collect_files_for_embedding
        result = collect_files_for_embedding(None)
        assert result == []

    def test_collect_files_for_embedding_returns_empty_for_empty_string(self):
        """Test that collect_files_for_embedding returns empty list for empty string."""
        from app.workers.helpers import collect_files_for_embedding
        result = collect_files_for_embedding("")
        assert result == []


# =============================================================================
# Integration Tests: Task Registration
# =============================================================================


class TestTaskRegistration:
    """
    Tests for Celery task registration.

    **Feature: parallel-analysis-pipeline**
    """

    def test_generate_embeddings_parallel_has_correct_name(self):
        """Test that generate_embeddings_parallel has the correct task name."""
        from app.workers.embeddings import generate_embeddings_parallel
        assert generate_embeddings_parallel.name == "app.workers.embeddings.generate_embeddings_parallel"

    def test_generate_embeddings_parallel_is_bound(self):
        """Test that generate_embeddings_parallel is a bound task (has self)."""
        from app.workers.embeddings import generate_embeddings_parallel
        # Bound tasks have __wrapped__ attribute
        assert hasattr(generate_embeddings_parallel, '__wrapped__')
