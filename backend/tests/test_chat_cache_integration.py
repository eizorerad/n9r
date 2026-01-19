"""Integration tests for Chat API cache usage.

Tests the integration between the Chat API and the Repository Content Cache,
verifying cache hit and cache miss fallback paths.

**Feature: repo-content-cache**
**Validates: Requirements 1.1, 1.2, 6.1**
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# The async_session_maker is imported inside the functions from app.core.database
# So we need to patch it at that location
DATABASE_MODULE = "app.core.database"
ENCRYPTION_MODULE = "app.core.encryption"
REPO_CONTENT_MODULE = "app.services.repo_content"
CHAT_MODULE = "app.api.v1.chat"

# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def mock_repository():
    """Create a mock repository object."""
    repo = MagicMock()
    repo.id = uuid.uuid4()
    repo.full_name = "test-owner/test-repo"
    repo.default_branch = "main"
    repo.owner_id = uuid.uuid4()
    return repo


@pytest.fixture
def mock_user():
    """Create a mock user object."""
    user = MagicMock()
    user.id = uuid.uuid4()
    user.access_token_encrypted = "encrypted_token"
    return user


@pytest.fixture
def sample_tree():
    """Sample tree structure from cache."""
    return [
        "src/main.py",
        "src/utils.py",
        "src/models/user.py",
        "src/models/repo.py",
        "tests/test_main.py",
        "README.md",
    ]


@pytest.fixture
def sample_file_content():
    """Sample file content from cache."""
    return '''def hello_world():
    """Say hello to the world."""
    print("Hello, World!")


if __name__ == "__main__":
    hello_world()
'''


# =============================================================================
# Tests for _format_cached_tree_lines
# =============================================================================


class TestFormatCachedTreeLines:
    """Tests for the _format_cached_tree_lines helper function.

    **Feature: repo-content-cache**
    **Validates: Requirements 1.1**
    """

    def test_format_empty_tree(self):
        """Empty tree should return empty list."""
        from app.api.v1.chat import _format_cached_tree_lines

        result = _format_cached_tree_lines([], path="", depth=4, max_entries=100)
        assert result == []

    def test_format_simple_tree(self, sample_tree):
        """Simple tree should be formatted with proper indentation."""
        from app.api.v1.chat import _format_cached_tree_lines

        result = _format_cached_tree_lines(
            sample_tree, path="", depth=4, max_entries=100
        )

        # Should have entries for directories and files
        assert len(result) > 0

        # Check that directories have trailing slash
        dir_entries = [line for line in result if line.strip().endswith("/")]
        assert len(dir_entries) > 0  # Should have src/, tests/, models/

    def test_format_tree_with_path_filter(self, sample_tree):
        """Tree should be filtered by path prefix."""
        from app.api.v1.chat import _format_cached_tree_lines

        result = _format_cached_tree_lines(
            sample_tree, path="src", depth=4, max_entries=100
        )

        # Should only include files under src/
        # The result should not include tests/ or README.md at root level
        for line in result:
            # Lines should be related to src/ contents
            assert "tests" not in line.lower() or "test_" in line.lower()

    def test_format_tree_respects_depth(self, sample_tree):
        """Tree formatting should respect depth limit."""
        from app.api.v1.chat import _format_cached_tree_lines

        # With depth=1, should only show top-level items
        result = _format_cached_tree_lines(
            sample_tree, path="", depth=1, max_entries=100
        )

        # All entries should have no indentation (depth 0)
        for line in result:
            # Top-level entries start with "- "
            assert line.startswith("- "), f"Expected top-level entry, got: {line}"

    def test_format_tree_respects_max_entries(self, sample_tree):
        """Tree formatting should respect max_entries limit."""
        from app.api.v1.chat import _format_cached_tree_lines

        result = _format_cached_tree_lines(
            sample_tree, path="", depth=4, max_entries=2
        )

        # Should have at most 2 entries
        assert len(result) <= 2


# =============================================================================
# Tests for _get_repo_tree_lines Cache Integration
# =============================================================================


class TestGetRepoTreeLinesCache:
    """Tests for _get_repo_tree_lines cache integration.

    **Feature: repo-content-cache**
    **Validates: Requirements 1.1, 6.1**
    """

    @pytest.mark.asyncio
    async def test_cache_hit_returns_cached_tree(
        self, mock_repository, mock_user, sample_tree
    ):
        """When cache has tree, should return from cache without GitHub API call.

        **Feature: repo-content-cache**
        **Validates: Requirements 1.1, 6.1**
        """
        from app.api.v1.chat import _get_repo_tree_lines

        # Mock database session and queries
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock()

        # Mock the session maker as async context manager
        mock_session_maker = MagicMock()
        mock_session_maker.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_maker.return_value.__aexit__ = AsyncMock(return_value=None)

        # Mock repository query result
        mock_repo_result = MagicMock()
        mock_repo_result.scalar_one_or_none.return_value = mock_repository

        # Mock user query result
        mock_user_result = MagicMock()
        mock_user_result.scalar_one_or_none.return_value = mock_user

        # Set up execute to return different results for different queries
        mock_db.execute.side_effect = [mock_repo_result, mock_user_result]

        # Mock RepoContentService
        mock_service = MagicMock()
        mock_service.get_tree = AsyncMock(return_value=sample_tree)

        # Patch at the correct locations (where they are imported from)
        with patch(f"{DATABASE_MODULE}.async_session_maker", mock_session_maker), \
             patch(f"{ENCRYPTION_MODULE}.decrypt_token_or_none", return_value="test_token"), \
             patch(f"{REPO_CONTENT_MODULE}.RepoContentService", return_value=mock_service):

            lines, source = await _get_repo_tree_lines(
                repository_id=mock_repository.id,
                user_id=mock_user.id,
                path="",
                ref="abc123def456",
                depth=4,
                max_entries=100,
            )

            # Should return from cache
            assert source == "cache"
            assert len(lines) > 0

            # Cache service should have been called
            mock_service.get_tree.assert_called_once()

    @pytest.mark.asyncio
    async def test_cache_miss_falls_back_to_github(
        self, mock_repository, mock_user
    ):
        """When cache misses, should fall back to GitHub API.

        **Feature: repo-content-cache**
        **Validates: Requirements 6.1**
        """
        from app.api.v1.chat import _get_repo_tree_lines

        # Mock database session
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock()

        mock_session_maker = MagicMock()
        mock_session_maker.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_maker.return_value.__aexit__ = AsyncMock(return_value=None)

        # Mock repository and user query results
        mock_repo_result = MagicMock()
        mock_repo_result.scalar_one_or_none.return_value = mock_repository

        mock_user_result = MagicMock()
        mock_user_result.scalar_one_or_none.return_value = mock_user

        mock_db.execute.side_effect = [mock_repo_result, mock_user_result]

        # Mock RepoContentService to return None (cache miss)
        mock_service = MagicMock()
        mock_service.get_tree = AsyncMock(return_value=None)

        # Mock GitHubService
        mock_github = MagicMock()
        mock_github.get_repository_contents = AsyncMock(return_value=[
            {"name": "src", "path": "src", "type": "dir"},
            {"name": "README.md", "path": "README.md", "type": "file"},
        ])

        with patch(f"{DATABASE_MODULE}.async_session_maker", mock_session_maker), \
             patch(f"{ENCRYPTION_MODULE}.decrypt_token_or_none", return_value="test_token"), \
             patch(f"{REPO_CONTENT_MODULE}.RepoContentService", return_value=mock_service), \
             patch(f"{CHAT_MODULE}.GitHubService", return_value=mock_github):

            lines, source = await _get_repo_tree_lines(
                repository_id=mock_repository.id,
                user_id=mock_user.id,
                path="",
                ref="abc123def456",
                depth=4,
                max_entries=100,
            )

            # Should fall back to GitHub API
            assert source == "github_api"

            # GitHub service should have been called
            mock_github.get_repository_contents.assert_called()


# =============================================================================
# Tests for _read_repo_file_text Cache Integration
# =============================================================================


class TestReadRepoFileTextCache:
    """Tests for _read_repo_file_text cache integration.

    **Feature: repo-content-cache**
    **Validates: Requirements 1.2, 1.3, 6.1**
    """

    @pytest.mark.asyncio
    async def test_cache_hit_returns_cached_content(
        self, mock_repository, mock_user, sample_file_content
    ):
        """When cache has file, should return from cache without GitHub API call.

        **Feature: repo-content-cache**
        **Validates: Requirements 1.2, 6.1**
        """
        from app.api.v1.chat import _read_repo_file_text

        # Mock database session
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock()

        mock_session_maker = MagicMock()
        mock_session_maker.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_maker.return_value.__aexit__ = AsyncMock(return_value=None)

        # Mock repository and user query results
        mock_repo_result = MagicMock()
        mock_repo_result.scalar_one_or_none.return_value = mock_repository

        mock_user_result = MagicMock()
        mock_user_result.scalar_one_or_none.return_value = mock_user

        mock_db.execute.side_effect = [mock_repo_result, mock_user_result]

        # Mock RepoContentService to return cached content
        mock_service = MagicMock()
        mock_service.get_file = AsyncMock(return_value=sample_file_content)

        with patch(f"{DATABASE_MODULE}.async_session_maker", mock_session_maker), \
             patch(f"{ENCRYPTION_MODULE}.decrypt_token_or_none", return_value="test_token"), \
             patch(f"{REPO_CONTENT_MODULE}.RepoContentService", return_value=mock_service):

            content, source = await _read_repo_file_text(
                repository_id=mock_repository.id,
                user_id=mock_user.id,
                file_path="src/main.py",
                ref="abc123def456",
                max_chars=10000,
            )

            # Should return from cache
            assert source == "cache"
            assert content == sample_file_content

            # Cache service should have been called
            mock_service.get_file.assert_called_once()

    @pytest.mark.asyncio
    async def test_cache_miss_falls_back_to_github(
        self, mock_repository, mock_user, sample_file_content
    ):
        """When cache misses, should fall back to GitHub API.

        **Feature: repo-content-cache**
        **Validates: Requirements 1.3, 6.1**
        """
        from app.api.v1.chat import _read_repo_file_text

        # Mock database session
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock()

        mock_session_maker = MagicMock()
        mock_session_maker.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_maker.return_value.__aexit__ = AsyncMock(return_value=None)

        # Mock repository and user query results
        mock_repo_result = MagicMock()
        mock_repo_result.scalar_one_or_none.return_value = mock_repository

        mock_user_result = MagicMock()
        mock_user_result.scalar_one_or_none.return_value = mock_user

        mock_db.execute.side_effect = [mock_repo_result, mock_user_result]

        # Mock RepoContentService to return None (cache miss)
        mock_service = MagicMock()
        mock_service.get_file = AsyncMock(return_value=None)

        # Mock GitHubService
        mock_github = MagicMock()
        mock_github.get_repository_contents = AsyncMock(return_value={
            "name": "main.py",
            "path": "src/main.py",
            "type": "file",
            "size": 100,
            "content": "base64content",
        })
        mock_github.get_file_content = AsyncMock(return_value=sample_file_content)

        with patch(f"{DATABASE_MODULE}.async_session_maker", mock_session_maker), \
             patch(f"{ENCRYPTION_MODULE}.decrypt_token_or_none", return_value="test_token"), \
             patch(f"{REPO_CONTENT_MODULE}.RepoContentService", return_value=mock_service), \
             patch(f"{CHAT_MODULE}.GitHubService", return_value=mock_github):

            content, source = await _read_repo_file_text(
                repository_id=mock_repository.id,
                user_id=mock_user.id,
                file_path="src/main.py",
                ref="abc123def456",
                max_chars=10000,
            )

            # Should fall back to GitHub API
            assert source == "github_api"
            assert content == sample_file_content

            # GitHub service should have been called
            mock_github.get_file_content.assert_called()

    @pytest.mark.asyncio
    async def test_sensitive_path_blocked(self, mock_repository, mock_user):
        """Sensitive paths should be blocked regardless of cache.

        **Feature: repo-content-cache**
        **Validates: Requirements 1.2**
        """
        from app.api.v1.chat import _read_repo_file_text

        # No need to mock anything - sensitive paths are blocked early
        content, source = await _read_repo_file_text(
            repository_id=mock_repository.id,
            user_id=mock_user.id,
            file_path=".env",
            ref="abc123def456",
            max_chars=10000,
        )

        # Should be blocked
        assert source == "blocked"
        assert content == ""

    @pytest.mark.asyncio
    async def test_content_truncation(
        self, mock_repository, mock_user
    ):
        """Large content should be truncated.

        **Feature: repo-content-cache**
        **Validates: Requirements 1.2**
        """
        from app.api.v1.chat import _read_repo_file_text

        # Create large content
        large_content = "x" * 20000

        # Mock database session
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock()

        mock_session_maker = MagicMock()
        mock_session_maker.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_maker.return_value.__aexit__ = AsyncMock(return_value=None)

        # Mock repository and user query results
        mock_repo_result = MagicMock()
        mock_repo_result.scalar_one_or_none.return_value = mock_repository

        mock_user_result = MagicMock()
        mock_user_result.scalar_one_or_none.return_value = mock_user

        mock_db.execute.side_effect = [mock_repo_result, mock_user_result]

        # Mock RepoContentService to return large content
        mock_service = MagicMock()
        mock_service.get_file = AsyncMock(return_value=large_content)

        with patch(f"{DATABASE_MODULE}.async_session_maker", mock_session_maker), \
             patch(f"{ENCRYPTION_MODULE}.decrypt_token_or_none", return_value="test_token"), \
             patch(f"{REPO_CONTENT_MODULE}.RepoContentService", return_value=mock_service):

            content, source = await _read_repo_file_text(
                repository_id=mock_repository.id,
                user_id=mock_user.id,
                file_path="src/main.py",
                ref="abc123def456",
                max_chars=1000,
            )

            # Should be truncated
            assert source == "cache"
            assert len(content) < len(large_content)
            assert "[... truncated ...]" in content
