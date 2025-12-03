"""Tests for GitHubService branch and commit methods."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.github import (
    GitHubAPIError,
    GitHubAuthenticationError,
    GitHubPermissionError,
    GitHubRateLimitError,
    GitHubService,
)


class TestListBranches:
    """Tests for GitHubService.list_branches()."""

    def setup_method(self):
        self.service = GitHubService("test_token")

    @pytest.mark.asyncio
    async def test_list_branches_parses_response(self):
        """list_branches should parse GitHub API response correctly."""
        mock_response = [
            {
                "name": "main",
                "commit": {"sha": "abc123def456"},
                "protected": True,
            },
            {
                "name": "feature-branch",
                "commit": {"sha": "789xyz000111"},
                "protected": False,
            },
        ]

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_instance
            mock_response_obj = MagicMock()
            mock_response_obj.json.return_value = mock_response
            mock_response_obj.is_success = True
            mock_instance.get.return_value = mock_response_obj

            result = await self.service.list_branches("owner", "repo")

        assert len(result) == 2
        assert result[0]["name"] == "main"
        assert result[0]["commit_sha"] == "abc123def456"
        assert result[0]["protected"] is True
        assert result[1]["name"] == "feature-branch"
        assert result[1]["commit_sha"] == "789xyz000111"
        assert result[1]["protected"] is False

    @pytest.mark.asyncio
    async def test_list_branches_handles_missing_protected(self):
        """list_branches should default protected to False if missing."""
        mock_response = [
            {
                "name": "main",
                "commit": {"sha": "abc123"},
            },
        ]

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_instance
            mock_response_obj = MagicMock()
            mock_response_obj.json.return_value = mock_response
            mock_response_obj.is_success = True
            mock_instance.get.return_value = mock_response_obj

            result = await self.service.list_branches("owner", "repo")

        assert result[0]["protected"] is False

    @pytest.mark.asyncio
    async def test_list_branches_caps_per_page_at_100(self):
        """list_branches should cap per_page at 100."""
        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_instance
            mock_response_obj = MagicMock()
            mock_response_obj.json.return_value = []
            mock_response_obj.is_success = True
            mock_instance.get.return_value = mock_response_obj

            await self.service.list_branches("owner", "repo", per_page=200)

            # Check that per_page was capped at 100
            call_args = mock_instance.get.call_args
            assert call_args.kwargs["params"]["per_page"] == 100

    @pytest.mark.asyncio
    async def test_list_branches_raises_on_api_error(self):
        """list_branches should raise GitHubAPIError on 404 errors."""
        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_instance
            mock_response_obj = MagicMock()
            mock_response_obj.status_code = 404
            mock_response_obj.is_success = False
            mock_response_obj.text = "Not Found"
            mock_response_obj.json.return_value = {"message": "Not Found"}
            mock_response_obj.headers = {}
            mock_instance.get.return_value = mock_response_obj

            with pytest.raises(GitHubAPIError) as exc_info:
                await self.service.list_branches("owner", "repo")
            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_list_branches_raises_rate_limit_error(self):
        """list_branches should raise GitHubRateLimitError when rate limited."""
        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_instance
            mock_response_obj = MagicMock()
            mock_response_obj.status_code = 403
            mock_response_obj.is_success = False
            mock_response_obj.text = "rate limit exceeded"
            mock_response_obj.headers = {"x-ratelimit-remaining": "0", "x-ratelimit-reset": "1700000000"}
            mock_instance.get.return_value = mock_response_obj

            with pytest.raises(GitHubRateLimitError):
                await self.service.list_branches("owner", "repo")

    @pytest.mark.asyncio
    async def test_list_branches_raises_permission_error(self):
        """list_branches should raise GitHubPermissionError on 403 without rate limit."""
        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_instance
            mock_response_obj = MagicMock()
            mock_response_obj.status_code = 403
            mock_response_obj.is_success = False
            mock_response_obj.text = "Forbidden"
            mock_response_obj.headers = {"x-ratelimit-remaining": "100"}
            mock_instance.get.return_value = mock_response_obj

            with pytest.raises(GitHubPermissionError):
                await self.service.list_branches("owner", "repo")

    @pytest.mark.asyncio
    async def test_list_branches_raises_auth_error(self):
        """list_branches should raise GitHubAuthenticationError on 401."""
        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_instance
            mock_response_obj = MagicMock()
            mock_response_obj.status_code = 401
            mock_response_obj.is_success = False
            mock_response_obj.text = "Unauthorized"
            mock_response_obj.headers = {}
            mock_instance.get.return_value = mock_response_obj

            with pytest.raises(GitHubAuthenticationError):
                await self.service.list_branches("owner", "repo")


class TestListCommits:
    """Tests for GitHubService.list_commits()."""

    def setup_method(self):
        self.service = GitHubService("test_token")

    @pytest.mark.asyncio
    async def test_list_commits_parses_response(self):
        """list_commits should parse GitHub API response correctly."""
        mock_response = [
            {
                "sha": "abc123def456789",
                "commit": {
                    "message": "Initial commit\n\nWith body",
                    "author": {
                        "name": "John Doe",
                        "date": "2025-01-15T10:30:00Z",
                    },
                },
                "author": {
                    "login": "johndoe",
                    "avatar_url": "https://avatars.githubusercontent.com/u/123",
                },
            },
        ]

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_instance
            mock_response_obj = MagicMock()
            mock_response_obj.json.return_value = mock_response
            mock_response_obj.is_success = True
            mock_instance.get.return_value = mock_response_obj

            result = await self.service.list_commits("owner", "repo")

        assert len(result) == 1
        assert result[0]["sha"] == "abc123def456789"
        assert result[0]["message"] == "Initial commit\n\nWith body"
        assert result[0]["author_name"] == "John Doe"
        assert result[0]["author_login"] == "johndoe"
        assert result[0]["author_avatar_url"] == "https://avatars.githubusercontent.com/u/123"
        assert result[0]["committed_at"] == "2025-01-15T10:30:00Z"

    @pytest.mark.asyncio
    async def test_list_commits_handles_null_author(self):
        """list_commits should handle commits with null author (deleted user)."""
        mock_response = [
            {
                "sha": "abc123",
                "commit": {
                    "message": "Commit by deleted user",
                    "author": {
                        "name": "Deleted User",
                        "date": "2025-01-15T10:30:00Z",
                    },
                },
                "author": None,  # User was deleted
            },
        ]

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_instance
            mock_response_obj = MagicMock()
            mock_response_obj.json.return_value = mock_response
            mock_response_obj.is_success = True
            mock_instance.get.return_value = mock_response_obj

            result = await self.service.list_commits("owner", "repo")

        assert result[0]["author_login"] is None
        assert result[0]["author_avatar_url"] is None

    @pytest.mark.asyncio
    async def test_list_commits_passes_sha_param(self):
        """list_commits should pass sha parameter for branch filtering."""
        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_instance
            mock_response_obj = MagicMock()
            mock_response_obj.json.return_value = []
            mock_response_obj.is_success = True
            mock_instance.get.return_value = mock_response_obj

            await self.service.list_commits("owner", "repo", sha="feature-branch")

            call_args = mock_instance.get.call_args
            assert call_args.kwargs["params"]["sha"] == "feature-branch"

    @pytest.mark.asyncio
    async def test_list_commits_pagination_params(self):
        """list_commits should pass pagination parameters."""
        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_instance
            mock_response_obj = MagicMock()
            mock_response_obj.json.return_value = []
            mock_response_obj.is_success = True
            mock_instance.get.return_value = mock_response_obj

            await self.service.list_commits("owner", "repo", per_page=50, page=2)

            call_args = mock_instance.get.call_args
            assert call_args.kwargs["params"]["per_page"] == 50
            assert call_args.kwargs["params"]["page"] == 2

    @pytest.mark.asyncio
    async def test_list_commits_caps_per_page_at_100(self):
        """list_commits should cap per_page at 100."""
        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_instance
            mock_response_obj = MagicMock()
            mock_response_obj.json.return_value = []
            mock_response_obj.is_success = True
            mock_instance.get.return_value = mock_response_obj

            await self.service.list_commits("owner", "repo", per_page=200)

            call_args = mock_instance.get.call_args
            assert call_args.kwargs["params"]["per_page"] == 100

    @pytest.mark.asyncio
    async def test_list_commits_raises_on_api_error(self):
        """list_commits should raise GitHubAPIError on 404 errors."""
        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_instance
            mock_response_obj = MagicMock()
            mock_response_obj.status_code = 404
            mock_response_obj.is_success = False
            mock_response_obj.text = "Not Found"
            mock_response_obj.json.return_value = {"message": "Not Found"}
            mock_response_obj.headers = {}
            mock_instance.get.return_value = mock_response_obj

            with pytest.raises(GitHubAPIError) as exc_info:
                await self.service.list_commits("owner", "repo")
            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_list_commits_raises_rate_limit_error(self):
        """list_commits should raise GitHubRateLimitError when rate limited."""
        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_instance
            mock_response_obj = MagicMock()
            mock_response_obj.status_code = 403
            mock_response_obj.is_success = False
            mock_response_obj.text = "rate limit exceeded"
            mock_response_obj.headers = {"x-ratelimit-remaining": "0", "x-ratelimit-reset": "1700000000"}
            mock_instance.get.return_value = mock_response_obj

            with pytest.raises(GitHubRateLimitError):
                await self.service.list_commits("owner", "repo")

    @pytest.mark.asyncio
    async def test_list_commits_raises_permission_error(self):
        """list_commits should raise GitHubPermissionError on 403 without rate limit."""
        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_instance
            mock_response_obj = MagicMock()
            mock_response_obj.status_code = 403
            mock_response_obj.is_success = False
            mock_response_obj.text = "Forbidden"
            mock_response_obj.headers = {"x-ratelimit-remaining": "100"}
            mock_instance.get.return_value = mock_response_obj

            with pytest.raises(GitHubPermissionError):
                await self.service.list_commits("owner", "repo")

    @pytest.mark.asyncio
    async def test_list_commits_raises_auth_error(self):
        """list_commits should raise GitHubAuthenticationError on 401."""
        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_instance
            mock_response_obj = MagicMock()
            mock_response_obj.status_code = 401
            mock_response_obj.is_success = False
            mock_response_obj.text = "Unauthorized"
            mock_response_obj.headers = {}
            mock_instance.get.return_value = mock_response_obj

            with pytest.raises(GitHubAuthenticationError):
                await self.service.list_commits("owner", "repo")
