"""GitHub API service for repository operations."""

import logging
from datetime import UTC, datetime
from typing import Any

import httpx

from app.core.encryption import decrypt_token

logger = logging.getLogger(__name__)


class GitHubAPIError(Exception):
    """Base exception for GitHub API errors."""

    def __init__(self, message: str, status_code: int = 500):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class GitHubRateLimitError(GitHubAPIError):
    """Exception raised when GitHub API rate limit is exceeded."""

    def __init__(self, reset_at: datetime | None = None, message: str | None = None):
        self.reset_at = reset_at
        if message is None:
            if reset_at:
                # Calculate minutes until reset
                now = datetime.now(UTC)
                diff = reset_at - now
                minutes = max(1, int(diff.total_seconds() / 60))
                message = f"GitHub API rate limit exceeded. Please try again in {minutes} minute{'s' if minutes != 1 else ''}."
            else:
                message = "GitHub API rate limit exceeded. Please try again later."
        super().__init__(message, status_code=403)


class GitHubPermissionError(GitHubAPIError):
    """Exception raised when user lacks permission to access a resource."""

    def __init__(self, message: str = "You don't have permission to access this resource."):
        super().__init__(message, status_code=403)


class GitHubAuthenticationError(GitHubAPIError):
    """Exception raised when GitHub authentication fails."""

    def __init__(self, message: str = "GitHub authentication failed. Please re-authenticate."):
        super().__init__(message, status_code=401)


class GitHubTimeoutError(GitHubAPIError):
    """Exception raised when GitHub API request times out."""

    def __init__(self, message: str = "GitHub API request timed out. Please try again."):
        super().__init__(message, status_code=504)


class GitHubService:
    """Service for interacting with GitHub API."""

    BASE_URL = "https://api.github.com"
    # Timeout configuration: 30s connect, 60s read
    DEFAULT_TIMEOUT = httpx.Timeout(connect=30.0, read=60.0, write=30.0, pool=30.0)

    def __init__(self, access_token: str):
        """Initialize GitHub service with access token.

        Args:
            access_token: GitHub OAuth access token (plaintext or encrypted).
        """
        # Try to decrypt if encrypted, otherwise use as-is
        try:
            self.access_token = decrypt_token(access_token)
        except Exception:
            self.access_token = access_token

    def _get_headers(self) -> dict[str, str]:
        """Get headers for GitHub API requests."""
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def _handle_response_error(self, response: httpx.Response) -> None:
        """Handle GitHub API error responses.

        Args:
            response: The HTTP response from GitHub API.

        Raises:
            GitHubRateLimitError: When rate limit is exceeded (403 with rate limit headers).
            GitHubAuthenticationError: When authentication fails (401).
            GitHubPermissionError: When user lacks permission (403 without rate limit).
            GitHubAPIError: For other API errors.
        """
        if response.is_success:
            return

        status_code = response.status_code

        # Check for rate limit error (403 with specific headers)
        if status_code == 403:
            # Check rate limit headers
            remaining = response.headers.get("x-ratelimit-remaining")
            reset_timestamp = response.headers.get("x-ratelimit-reset")

            # Rate limit exceeded if remaining is 0 or response indicates rate limit
            if remaining == "0" or "rate limit" in response.text.lower():
                reset_at = None
                if reset_timestamp:
                    try:
                        reset_at = datetime.fromtimestamp(int(reset_timestamp), tz=UTC)
                    except (ValueError, TypeError):
                        pass
                raise GitHubRateLimitError(reset_at=reset_at)

            # Otherwise it's a permission error
            raise GitHubPermissionError()

        # Authentication error
        if status_code == 401:
            raise GitHubAuthenticationError()

        # Not found - could be permission issue or actual 404
        if status_code == 404:
            raise GitHubAPIError("Repository not found or access denied.", status_code=404)

        # Other errors
        try:
            error_data = response.json()
            message = error_data.get("message", response.text)
        except Exception:
            message = response.text or f"GitHub API error: {status_code}"

        raise GitHubAPIError(message, status_code=status_code)

    async def get_user(self) -> dict[str, Any]:
        """Get the authenticated user's info."""
        async with httpx.AsyncClient(timeout=self.DEFAULT_TIMEOUT) as client:
            response = await client.get(
                f"{self.BASE_URL}/user",
                headers=self._get_headers(),
            )
            response.raise_for_status()
            return response.json()

    async def list_user_repositories(
        self,
        per_page: int = 100,
        page: int = 1,
        sort: str = "updated",
        affiliation: str = "owner,collaborator,organization_member",
    ) -> list[dict[str, Any]]:
        """List repositories for the authenticated user.

        Args:
            per_page: Number of results per page (max 100).
            page: Page number.
            sort: Sort field (created, updated, pushed, full_name).
            affiliation: Comma-separated list of affiliations.

        Returns:
            List of repository data dicts.
        """
        async with httpx.AsyncClient(timeout=self.DEFAULT_TIMEOUT) as client:
            response = await client.get(
                f"{self.BASE_URL}/user/repos",
                headers=self._get_headers(),
                params={
                    "per_page": per_page,
                    "page": page,
                    "sort": sort,
                    "affiliation": affiliation,
                },
            )
            response.raise_for_status()
            return response.json()

    async def get_repository(self, owner: str, repo: str) -> dict[str, Any]:
        """Get a specific repository.

        Args:
            owner: Repository owner.
            repo: Repository name.

        Returns:
            Repository data dict.
        """
        async with httpx.AsyncClient(timeout=self.DEFAULT_TIMEOUT) as client:
            response = await client.get(
                f"{self.BASE_URL}/repos/{owner}/{repo}",
                headers=self._get_headers(),
            )
            response.raise_for_status()
            return response.json()

    async def get_repository_contents(
        self,
        owner: str,
        repo: str,
        path: str = "",
        ref: str | None = None,
    ) -> list[dict[str, Any]] | dict[str, Any]:
        """Get contents of a repository path.

        Args:
            owner: Repository owner.
            repo: Repository name.
            path: Path within the repository.
            ref: Git reference (branch, tag, commit).

        Returns:
            List of content items for directories, or single item for files.
        """
        params = {}
        if ref:
            params["ref"] = ref

        async with httpx.AsyncClient(timeout=self.DEFAULT_TIMEOUT) as client:
            response = await client.get(
                f"{self.BASE_URL}/repos/{owner}/{repo}/contents/{path}",
                headers=self._get_headers(),
                params=params,
            )
            response.raise_for_status()
            return response.json()

    async def get_file_content(
        self,
        owner: str,
        repo: str,
        path: str,
        ref: str | None = None,
    ) -> str:
        """Get the decoded content of a file.

        Args:
            owner: Repository owner.
            repo: Repository name.
            path: File path within the repository.
            ref: Git reference.

        Returns:
            Decoded file content as string.
        """
        import base64

        result = await self.get_repository_contents(owner, repo, path, ref)

        if isinstance(result, list):
            raise ValueError(f"Path '{path}' is a directory, not a file")

        if result.get("type") != "file":
            raise ValueError(f"Path '{path}' is not a file")

        content = result.get("content", "")
        encoding = result.get("encoding", "base64")

        if encoding == "base64":
            return base64.b64decode(content).decode("utf-8")
        return content

    async def get_repository_tree(
        self,
        owner: str,
        repo: str,
        tree_sha: str = "HEAD",
        recursive: bool = True,
    ) -> list[dict[str, Any]]:
        """Get the full tree of a repository.

        Args:
            owner: Repository owner.
            repo: Repository name.
            tree_sha: Tree SHA or branch name.
            recursive: Whether to get tree recursively.

        Returns:
            List of tree items.
        """
        params = {"recursive": "1"} if recursive else {}

        async with httpx.AsyncClient(timeout=self.DEFAULT_TIMEOUT) as client:
            response = await client.get(
                f"{self.BASE_URL}/repos/{owner}/{repo}/git/trees/{tree_sha}",
                headers=self._get_headers(),
                params=params,
            )
            response.raise_for_status()
            data = response.json()
            return data.get("tree", [])

    async def get_branch(
        self,
        owner: str,
        repo: str,
        branch: str,
    ) -> dict[str, Any]:
        """Get branch information.

        Args:
            owner: Repository owner.
            repo: Repository name.
            branch: Branch name.

        Returns:
            Branch data dict.
        """
        async with httpx.AsyncClient(timeout=self.DEFAULT_TIMEOUT) as client:
            response = await client.get(
                f"{self.BASE_URL}/repos/{owner}/{repo}/branches/{branch}",
                headers=self._get_headers(),
            )
            response.raise_for_status()
            return response.json()

    async def list_branches(
        self,
        owner: str,
        repo: str,
        per_page: int = 30,
    ) -> list[dict[str, Any]]:
        """List repository branches.

        Args:
            owner: Repository owner.
            repo: Repository name.
            per_page: Number of branches to return (max 100).

        Returns:
            List of branch objects with name, commit SHA, and protection status.

        Raises:
            GitHubRateLimitError: When rate limit is exceeded.
            GitHubPermissionError: When user lacks permission.
            GitHubAuthenticationError: When authentication fails.
            GitHubAPIError: For other API errors.
        """
        try:
            async with httpx.AsyncClient(timeout=self.DEFAULT_TIMEOUT) as client:
                response = await client.get(
                    f"{self.BASE_URL}/repos/{owner}/{repo}/branches",
                    headers=self._get_headers(),
                    params={"per_page": min(per_page, 100)},
                )
                self._handle_response_error(response)
                branches = response.json()

                # Transform to consistent format
                return [
                    {
                        "name": branch["name"],
                        "commit_sha": branch["commit"]["sha"],
                        "protected": branch.get("protected", False),
                    }
                    for branch in branches
                ]
        except httpx.TimeoutException:
            raise GitHubTimeoutError()

    async def list_commits(
        self,
        owner: str,
        repo: str,
        sha: str | None = None,
        per_page: int = 30,
        page: int = 1,
    ) -> list[dict[str, Any]]:
        """List commits for a branch.

        Args:
            owner: Repository owner.
            repo: Repository name.
            sha: Branch name or commit SHA to list commits from.
            per_page: Number of commits per page (max 100).
            page: Page number for pagination.

        Returns:
            List of commit objects with SHA, message, author, and timestamp.

        Raises:
            GitHubRateLimitError: When rate limit is exceeded.
            GitHubPermissionError: When user lacks permission.
            GitHubAuthenticationError: When authentication fails.
            GitHubAPIError: For other API errors.
        """
        params: dict[str, Any] = {
            "per_page": min(per_page, 100),
            "page": page,
        }
        if sha:
            params["sha"] = sha

        try:
            async with httpx.AsyncClient(timeout=self.DEFAULT_TIMEOUT) as client:
                response = await client.get(
                    f"{self.BASE_URL}/repos/{owner}/{repo}/commits",
                    headers=self._get_headers(),
                    params=params,
                )
                self._handle_response_error(response)
                commits = response.json()

                # Transform to consistent format
                return [
                    {
                        "sha": commit["sha"],
                        "message": commit["commit"]["message"],
                        "author_name": commit["commit"]["author"]["name"],
                        "author_login": commit["author"]["login"] if commit.get("author") else None,
                        "author_avatar_url": commit["author"]["avatar_url"] if commit.get("author") else None,
                        "committed_at": commit["commit"]["author"]["date"],
                    }
                    for commit in commits
                ]
        except httpx.TimeoutException:
            raise GitHubTimeoutError()

    async def create_branch(
        self,
        owner: str,
        repo: str,
        branch_name: str,
        from_sha: str,
    ) -> dict[str, Any]:
        """Create a new branch.

        Args:
            owner: Repository owner.
            repo: Repository name.
            branch_name: Name for the new branch.
            from_sha: SHA to create branch from.

        Returns:
            Reference data dict.
        """
        async with httpx.AsyncClient(timeout=self.DEFAULT_TIMEOUT) as client:
            response = await client.post(
                f"{self.BASE_URL}/repos/{owner}/{repo}/git/refs",
                headers=self._get_headers(),
                json={
                    "ref": f"refs/heads/{branch_name}",
                    "sha": from_sha,
                },
            )
            response.raise_for_status()
            return response.json()

    async def create_or_update_file(
        self,
        owner: str,
        repo: str,
        path: str,
        content: str,
        message: str,
        branch: str,
        sha: str | None = None,
    ) -> dict[str, Any]:
        """Create or update a file in a repository.

        Args:
            owner: Repository owner.
            repo: Repository name.
            path: File path.
            content: File content (will be base64 encoded).
            message: Commit message.
            branch: Branch name.
            sha: SHA of the file being replaced (required for updates).

        Returns:
            Commit data dict.
        """
        import base64

        payload = {
            "message": message,
            "content": base64.b64encode(content.encode()).decode(),
            "branch": branch,
        }

        if sha:
            payload["sha"] = sha

        async with httpx.AsyncClient(timeout=self.DEFAULT_TIMEOUT) as client:
            response = await client.put(
                f"{self.BASE_URL}/repos/{owner}/{repo}/contents/{path}",
                headers=self._get_headers(),
                json=payload,
            )
            response.raise_for_status()
            return response.json()

    async def create_pull_request(
        self,
        owner: str,
        repo: str,
        title: str,
        body: str,
        head: str,
        base: str,
        draft: bool = False,
    ) -> dict[str, Any]:
        """Create a pull request.

        Args:
            owner: Repository owner.
            repo: Repository name.
            title: PR title.
            body: PR description.
            head: Head branch.
            base: Base branch.
            draft: Whether to create as draft.

        Returns:
            Pull request data dict.
        """
        async with httpx.AsyncClient(timeout=self.DEFAULT_TIMEOUT) as client:
            response = await client.post(
                f"{self.BASE_URL}/repos/{owner}/{repo}/pulls",
                headers=self._get_headers(),
                json={
                    "title": title,
                    "body": body,
                    "head": head,
                    "base": base,
                    "draft": draft,
                },
            )
            response.raise_for_status()
            return response.json()

    async def merge_pull_request(
        self,
        owner: str,
        repo: str,
        pull_number: int,
        commit_title: str | None = None,
        merge_method: str = "squash",
    ) -> dict[str, Any]:
        """Merge a pull request.

        Args:
            owner: Repository owner.
            repo: Repository name.
            pull_number: PR number.
            commit_title: Optional commit title.
            merge_method: Merge method (merge, squash, rebase).

        Returns:
            Merge result dict.
        """
        payload: dict[str, Any] = {"merge_method": merge_method}
        if commit_title:
            payload["commit_title"] = commit_title

        async with httpx.AsyncClient(timeout=self.DEFAULT_TIMEOUT) as client:
            response = await client.put(
                f"{self.BASE_URL}/repos/{owner}/{repo}/pulls/{pull_number}/merge",
                headers=self._get_headers(),
                json=payload,
            )
            response.raise_for_status()
            return response.json()

    async def close_pull_request(
        self,
        owner: str,
        repo: str,
        pull_number: int,
    ) -> dict[str, Any]:
        """Close a pull request without merging.

        Args:
            owner: Repository owner.
            repo: Repository name.
            pull_number: PR number.

        Returns:
            Updated PR data dict.
        """
        async with httpx.AsyncClient(timeout=self.DEFAULT_TIMEOUT) as client:
            response = await client.patch(
                f"{self.BASE_URL}/repos/{owner}/{repo}/pulls/{pull_number}",
                headers=self._get_headers(),
                json={"state": "closed"},
            )
            response.raise_for_status()
            return response.json()

    async def create_webhook(
        self,
        owner: str,
        repo: str,
        url: str,
        events: list[str],
        secret: str | None = None,
    ) -> dict[str, Any]:
        """Create a webhook for a repository.

        Args:
            owner: Repository owner.
            repo: Repository name.
            url: Webhook URL.
            events: List of events to subscribe to.
            secret: Webhook secret for signature verification.

        Returns:
            Webhook data dict.
        """
        config = {
            "url": url,
            "content_type": "json",
        }
        if secret:
            config["secret"] = secret

        async with httpx.AsyncClient(timeout=self.DEFAULT_TIMEOUT) as client:
            response = await client.post(
                f"{self.BASE_URL}/repos/{owner}/{repo}/hooks",
                headers=self._get_headers(),
                json={
                    "name": "web",
                    "active": True,
                    "events": events,
                    "config": config,
                },
            )
            response.raise_for_status()
            return response.json()

    async def delete_webhook(
        self,
        owner: str,
        repo: str,
        hook_id: int,
    ) -> None:
        """Delete a webhook from a repository.

        Args:
            owner: Repository owner.
            repo: Repository name.
            hook_id: Webhook ID.
        """
        async with httpx.AsyncClient(timeout=self.DEFAULT_TIMEOUT) as client:
            response = await client.delete(
                f"{self.BASE_URL}/repos/{owner}/{repo}/hooks/{hook_id}",
                headers=self._get_headers(),
            )
            response.raise_for_status()

    async def create_auto_pr(
        self,
        owner: str,
        repo: str,
        issue_id: str,
        issue_title: str,
        file_path: str,
        original_content: str,
        fixed_content: str,
        test_file_path: str | None = None,
        test_content: str | None = None,
        description: str = "",
        base_branch: str = "main",
    ) -> dict[str, Any]:
        """Create an auto-PR for a code fix.

        This high-level method handles:
        1. Getting the base branch SHA
        2. Creating a new branch
        3. Committing the fix
        4. Committing tests if provided
        5. Creating the PR

        Args:
            owner: Repository owner.
            repo: Repository name.
            issue_id: Issue ID for branch naming.
            issue_title: Issue title for PR title.
            file_path: Path to the fixed file.
            original_content: Original file content (unused, for reference).
            fixed_content: Fixed file content.
            test_file_path: Optional test file path.
            test_content: Optional test file content.
            description: PR description/body.
            base_branch: Base branch to create PR against.

        Returns:
            Created PR data dict.
        """
        import time

        # Generate unique branch name
        timestamp = int(time.time())
        branch_name = f"n9r/fix-{issue_id[:8]}-{timestamp}"

        # Get base branch SHA
        base = await self.get_branch(owner, repo, base_branch)
        base_sha = base["commit"]["sha"]

        # Create new branch
        await self.create_branch(owner, repo, branch_name, base_sha)

        # Get current file SHA (for update)
        try:
            current = await self.get_repository_contents(owner, repo, file_path, base_branch)
            file_sha = current.get("sha") if isinstance(current, dict) else None
        except Exception:
            file_sha = None

        # Commit the fix
        await self.create_or_update_file(
            owner=owner,
            repo=repo,
            path=file_path,
            content=fixed_content,
            message=f"fix: {issue_title}\n\nAuto-fix by n9r for issue {issue_id}",
            branch=branch_name,
            sha=file_sha,
        )

        # Commit test file if provided
        if test_file_path and test_content:
            try:
                test_current = await self.get_repository_contents(owner, repo, test_file_path, branch_name)
                test_sha = test_current.get("sha") if isinstance(test_current, dict) else None
            except Exception:
                test_sha = None

            await self.create_or_update_file(
                owner=owner,
                repo=repo,
                path=test_file_path,
                content=test_content,
                message=f"test: add regression test for {issue_title}",
                branch=branch_name,
                sha=test_sha,
            )

        # Create PR
        pr_title = f"🔧 n9r auto-fix: {issue_title}"
        pr_body = f"""## Auto-generated PR by n9r

**Issue:** {issue_title}
**Issue ID:** `{issue_id}`

### Changes
{description}

### Files Modified
- `{file_path}`
{f"- `{test_file_path}` (regression test)" if test_file_path else ""}

---
*This PR was automatically generated by [n9r](https://n9r.dev). Review the changes and merge if they look good.*
"""

        pr = await self.create_pull_request(
            owner=owner,
            repo=repo,
            title=pr_title,
            body=pr_body,
            head=branch_name,
            base=base_branch,
            draft=False,
        )

        return pr
