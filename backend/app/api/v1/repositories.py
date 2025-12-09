"""Repository endpoints."""

import logging
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select

from app.api.deps import CurrentUser, DbSession
from app.core.encryption import decrypt_token_or_none
from app.models.repository import Repository
from app.models.user import User


def require_github_token(user: User) -> str:
    """Get GitHub token or raise 403 to indicate GitHub re-authentication needed.

    Returns the decrypted GitHub token if valid.
    Raises HTTPException 403 if token is missing or invalid.

    Note: We use 403 (not 401) because:
    - 401 means "JWT session invalid" → redirect to login
    - 403 means "GitHub token invalid" → show re-auth prompt in UI
    """
    logger.debug(f"Decrypting token for user {user.id}, encrypted_token exists: {bool(user.access_token_encrypted)}")
    github_token = decrypt_token_or_none(user.access_token_encrypted)
    if not github_token:
        logger.warning(f"Failed to decrypt GitHub token for user {user.id}. Token encrypted: {bool(user.access_token_encrypted)}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="GitHub token expired or invalid. Please reconnect your GitHub account.",
        )
    return github_token
from app.schemas.common import PaginatedResponse, PaginationMeta
from app.schemas.repository import (
    AvailableRepository,
    BranchListResponse,
    BranchResponse,
    CommitListResponse,
    CommitResponse,
    FileContent,
    FileTreeItem,
    RepositoryConnect,
    RepositoryDetail,
    RepositoryResponse,
    RepositoryStats,
    RepositoryUpdate,
)
from app.services.github import (
    GitHubAPIError,
    GitHubAuthenticationError,
    GitHubPermissionError,
    GitHubRateLimitError,
    GitHubService,
    GitHubTimeoutError,
)

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("", response_model=PaginatedResponse[RepositoryResponse])
async def list_repositories(
    current_user: CurrentUser,
    db: DbSession,
    org_id: UUID | None = None,
    is_active: bool | None = None,
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
) -> PaginatedResponse[RepositoryResponse]:
    """List connected repositories."""
    query = select(Repository).where(Repository.owner_id == current_user.id)

    if org_id:
        query = query.where(Repository.org_id == org_id)
    if is_active is not None:
        query = query.where(Repository.is_active == is_active)

    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(count_query) or 0

    # Paginate
    query = query.offset((page - 1) * per_page).limit(per_page)
    result = await db.execute(query)
    repositories = result.scalars().all()

    return PaginatedResponse(
        data=[
            RepositoryResponse(
                id=repo.id,
                github_id=repo.github_id,
                name=repo.name,
                full_name=repo.full_name,
                default_branch=repo.default_branch,
                mode=repo.mode,
                is_active=repo.is_active,
                vci_score=float(repo.vci_score) if repo.vci_score else None,
                tech_debt_level=repo.tech_debt_level,
                last_analysis_at=repo.last_analysis_at,
                pending_prs_count=0,  # TODO: Count from auto_prs
                open_issues_count=0,  # TODO: Count from issues
            )
            for repo in repositories
        ],
        pagination=PaginationMeta(
            page=page,
            per_page=per_page,
            total=total,
            total_pages=(total + per_page - 1) // per_page,
        ),
    )


@router.get("/available")
async def list_available_repositories(
    current_user: CurrentUser,
    db: DbSession,
) -> dict[str, list[AvailableRepository]]:
    """List available GitHub repositories for connection."""
    github_token = require_github_token(current_user)

    try:
        github = GitHubService(github_token)
        github_repos = await github.list_user_repositories(per_page=100)

        # Get already connected repository IDs
        result = await db.execute(
            select(Repository.github_id).where(Repository.owner_id == current_user.id)
        )
        connected_ids = {row[0] for row in result.fetchall()}

        available = []
        for repo in github_repos:
            available.append(
                AvailableRepository(
                    github_id=repo["id"],
                    name=repo["name"],
                    full_name=repo["full_name"],
                    private=repo["private"],
                    default_branch=repo.get("default_branch", "main"),
                    language=repo.get("language"),
                    description=repo.get("description"),
                    is_connected=repo["id"] in connected_ids,
                )
            )

        return {"data": available}

    except Exception as e:
        logger.error(f"Failed to list GitHub repositories: {e}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to fetch repositories from GitHub",
        )


@router.post("", response_model=RepositoryResponse, status_code=status.HTTP_201_CREATED)
async def connect_repository(
    repo_data: RepositoryConnect,
    current_user: CurrentUser,
    db: DbSession,
) -> RepositoryResponse:
    """Connect a GitHub repository."""
    # Check if already connected
    existing_result = await db.execute(
        select(Repository).where(Repository.github_id == repo_data.github_id)
    )
    existing = existing_result.scalar_one_or_none()
    if existing:
        if existing.owner_id == current_user.id:
            # User already connected this repo - return it instead of error
            return RepositoryResponse(
                id=existing.id,
                github_id=existing.github_id,
                name=existing.name,
                full_name=existing.full_name,
                default_branch=existing.default_branch,
                mode=existing.mode,
                is_active=existing.is_active,
                vci_score=float(existing.vci_score) if existing.vci_score else None,
                tech_debt_level=existing.tech_debt_level,
                last_analysis_at=existing.last_analysis_at,
                pending_prs_count=0,
                open_issues_count=0,
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Repository already connected by another user",
            )

    github_token = require_github_token(current_user)

    try:
        # Fetch repository details from GitHub
        github = GitHubService(github_token)

        # List repos to find the one we're connecting
        github_repos = await github.list_user_repositories(per_page=100)
        github_repo = next(
            (r for r in github_repos if r["id"] == repo_data.github_id),
            None
        )

        if not github_repo:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Repository not found or not accessible",
            )

        # Create repository record
        # Convert mode enum to string value
        mode_value = repo_data.mode.value if hasattr(repo_data.mode, 'value') else str(repo_data.mode)

        repository = Repository(
            github_id=github_repo["id"],
            owner_id=current_user.id,
            org_id=repo_data.org_id,
            name=github_repo["name"],
            full_name=github_repo["full_name"],
            description=github_repo.get("description"),
            default_branch=github_repo.get("default_branch", "main"),
            language=github_repo.get("language"),
            mode=mode_value,
            is_active=True,
        )
        db.add(repository)
        await db.flush()

        # Get the latest commit SHA for the default branch
        try:
            branch_info = await github.get_branch(
                owner=github_repo["full_name"].split("/")[0],
                repo=github_repo["name"],
                branch=repository.default_branch,
            )
            initial_commit_sha = branch_info.get("commit", {}).get("sha", "HEAD")
        except Exception:
            initial_commit_sha = "HEAD"

        # Create initial analysis record
        from app.models.analysis import Analysis
        analysis = Analysis(
            repository_id=repository.id,
            commit_sha=initial_commit_sha,
            branch=repository.default_branch,
            status="pending",
        )
        db.add(analysis)
        await db.flush()

        # Queue initial analysis with analysis_id
        from app.workers.analysis import analyze_repository
        analyze_repository.delay(
            repository_id=str(repository.id),
            analysis_id=str(analysis.id),
            commit_sha=initial_commit_sha,
            triggered_by="connect",
        )

        logger.info(f"Repository {repository.full_name} connected by user {current_user.id}")

        return RepositoryResponse(
            id=repository.id,
            github_id=repository.github_id,
            name=repository.name,
            full_name=repository.full_name,
            default_branch=repository.default_branch,
            mode=repository.mode,
            is_active=repository.is_active,
            vci_score=None,
            tech_debt_level=None,
            last_analysis_at=None,
            pending_prs_count=0,
            open_issues_count=0,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to connect repository: {e}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to connect repository",
        )


@router.get("/{repo_id}", response_model=RepositoryDetail)
async def get_repository(
    repo_id: UUID,
    current_user: CurrentUser,
    db: DbSession,
) -> RepositoryDetail:
    """Get repository details."""
    result = await db.execute(
        select(Repository).where(
            Repository.id == repo_id,
            Repository.owner_id == current_user.id,
        )
    )
    repository = result.scalar_one_or_none()

    if not repository:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Repository not found",
        )

    return RepositoryDetail(
        id=repository.id,
        github_id=repository.github_id,
        name=repository.name,
        full_name=repository.full_name,
        default_branch=repository.default_branch,
        mode=repository.mode,
        is_active=repository.is_active,
        vci_score=float(repository.vci_score) if repository.vci_score else None,
        vci_trend=[],  # TODO: Load from analyses
        tech_debt_level=repository.tech_debt_level,
        last_analysis=None,  # TODO: Load last analysis
        stats=RepositoryStats(
            total_analyses=0,
            total_prs_created=0,
            prs_merged=0,
            prs_rejected=0,
        ),
        created_at=repository.created_at,
    )


@router.patch("/{repo_id}", response_model=RepositoryResponse)
async def update_repository(
    repo_id: UUID,
    update: RepositoryUpdate,
    current_user: CurrentUser,
    db: DbSession,
) -> RepositoryResponse:
    """Update repository settings."""
    result = await db.execute(
        select(Repository).where(
            Repository.id == repo_id,
            Repository.owner_id == current_user.id,
        )
    )
    repository = result.scalar_one_or_none()

    if not repository:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Repository not found",
        )

    if update.mode is not None:
        repository.mode = update.mode
    if update.is_active is not None:
        repository.is_active = update.is_active

    return RepositoryResponse(
        id=repository.id,
        github_id=repository.github_id,
        name=repository.name,
        full_name=repository.full_name,
        default_branch=repository.default_branch,
        mode=repository.mode,
        is_active=repository.is_active,
        vci_score=float(repository.vci_score) if repository.vci_score else None,
        tech_debt_level=repository.tech_debt_level,
        last_analysis_at=repository.last_analysis_at,
        pending_prs_count=0,
        open_issues_count=0,
    )


@router.delete("/{repo_id}", status_code=status.HTTP_204_NO_CONTENT)
async def disconnect_repository(
    repo_id: UUID,
    current_user: CurrentUser,
    db: DbSession,
) -> None:
    """Disconnect a repository."""
    result = await db.execute(
        select(Repository).where(
            Repository.id == repo_id,
            Repository.owner_id == current_user.id,
        )
    )
    repository = result.scalar_one_or_none()

    if not repository:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Repository not found",
        )

    await db.delete(repository)


@router.get("/{repo_id}/files")
async def get_repository_files(
    repo_id: UUID,
    current_user: CurrentUser,
    db: DbSession,
    path: str = Query(default="", description="Path within the repository"),
    ref: str | None = Query(default=None, description="Git reference (branch/commit)"),
) -> dict:
    """Get file tree of a repository path."""
    # Get repository
    result = await db.execute(
        select(Repository).where(
            Repository.id == repo_id,
            Repository.owner_id == current_user.id,
        )
    )
    repository = result.scalar_one_or_none()

    if not repository:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Repository not found",
        )

    github_token = require_github_token(current_user)

    try:
        github = GitHubService(github_token)

        # Parse owner/repo from full_name
        owner, repo_name = repository.full_name.split("/")

        contents = await github.get_repository_contents(
            owner=owner,
            repo=repo_name,
            path=path,
            ref=ref or repository.default_branch,
        )

        # Handle single file case
        if isinstance(contents, dict):
            contents = [contents]

        items = []
        for item in contents:
            items.append(
                FileTreeItem(
                    name=item["name"],
                    path=item["path"],
                    type="directory" if item["type"] == "dir" else "file",
                    size=item.get("size"),
                )
            )

        # Sort: directories first, then files
        items.sort(key=lambda x: (x.type != "directory", x.name.lower()))

        return {"data": items}

    except Exception as e:
        logger.error(f"Failed to get repository files: {e}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to fetch files from GitHub",
        )


@router.get("/{repo_id}/files/{file_path:path}", response_model=FileContent)
async def get_repository_file_content(
    repo_id: UUID,
    file_path: str,
    current_user: CurrentUser,
    db: DbSession,
    ref: str | None = Query(default=None, description="Git reference (branch/commit)"),
) -> FileContent:
    """Get content of a specific file."""
    # Get repository
    result = await db.execute(
        select(Repository).where(
            Repository.id == repo_id,
            Repository.owner_id == current_user.id,
        )
    )
    repository = result.scalar_one_or_none()

    if not repository:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Repository not found",
        )

    github_token = require_github_token(current_user)

    try:
        github = GitHubService(github_token)

        # Parse owner/repo from full_name
        owner, repo_name = repository.full_name.split("/")

        # First, get file metadata to check size
        try:
            file_info = await github.get_repository_contents(
                owner=owner,
                repo=repo_name,
                path=file_path,
                ref=ref or repository.default_branch,
            )

            # Check if path is a directory
            if isinstance(file_info, list):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Path '{file_path}' is a directory, not a file",
                )

            file_size = file_info.get("size", 0)

            # Check for large files (GitHub limits to 1MB for content API)
            if file_size > 1_000_000:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"File is too large ({file_size:,} bytes). Files over 1MB cannot be displayed in the IDE.",
                )

            # Check for binary files - GitHub returns empty content for binary files
            file_content = file_info.get("content", "")
            if not file_content and file_size > 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="This file appears to be binary and cannot be displayed as text.",
                )

        except HTTPException:
            raise
        except Exception as e:
            logger.warning(f"Could not get file metadata, trying direct content: {e}")

        content = await github.get_file_content(
            owner=owner,
            repo=repo_name,
            path=file_path,
            ref=ref or repository.default_branch,
        )

        # Detect language from file extension
        language = None
        if "." in file_path:
            ext = file_path.rsplit(".", 1)[1].lower()
            language_map = {
                "py": "python",
                "js": "javascript",
                "ts": "typescript",
                "tsx": "typescript",
                "jsx": "javascript",
                "java": "java",
                "rb": "ruby",
                "go": "go",
                "rs": "rust",
                "c": "c",
                "cpp": "cpp",
                "h": "c",
                "hpp": "cpp",
                "cs": "csharp",
                "php": "php",
                "swift": "swift",
                "kt": "kotlin",
                "scala": "scala",
                "sql": "sql",
                "html": "html",
                "css": "css",
                "scss": "scss",
                "json": "json",
                "yaml": "yaml",
                "yml": "yaml",
                "xml": "xml",
                "md": "markdown",
                "sh": "bash",
                "bash": "bash",
                "dockerfile": "dockerfile",
            }
            language = language_map.get(ext)

        return FileContent(
            path=file_path,
            content=content,
            encoding="utf-8",
            size=len(content),
            language=language,
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except UnicodeDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This file appears to be binary and cannot be displayed as text.",
        )
    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except Exception as e:
        logger.error(f"Failed to get file content: {e}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to fetch file from GitHub",
        )


@router.get("/{repo_id}/branches", response_model=BranchListResponse)
async def list_branches(
    repo_id: UUID,
    current_user: CurrentUser,
    db: DbSession,
) -> BranchListResponse:
    """List branches for a repository.

    Requirements: 1.1, 1.2, 1.3, 6.1, 6.4
    """
    # Verify repository ownership
    result = await db.execute(
        select(Repository).where(
            Repository.id == repo_id,
            Repository.owner_id == current_user.id,
        )
    )
    repository = result.scalar_one_or_none()

    if not repository:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Repository not found",
        )

    github_token = require_github_token(current_user)

    try:
        github = GitHubService(github_token)

        # Parse owner/repo from full_name
        owner, repo_name = repository.full_name.split("/")

        # Fetch branches via GitHubService
        branches = await github.list_branches(
            owner=owner,
            repo=repo_name,
            per_page=100,
        )

        # Transform to response format, identifying default branch
        branch_responses = [
            BranchResponse(
                name=branch["name"],
                commit_sha=branch["commit_sha"],
                is_default=(branch["name"] == repository.default_branch),
                is_protected=branch.get("protected", False),
            )
            for branch in branches
        ]

        return BranchListResponse(data=branch_responses)

    except GitHubTimeoutError as e:
        logger.warning(f"GitHub API timeout for user {current_user.id} on repo {repo_id}")
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=e.message,
        )
    except GitHubRateLimitError as e:
        logger.warning(f"GitHub rate limit exceeded for user {current_user.id}: {e.message}")
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=e.message,
        )
    except GitHubAuthenticationError as e:
        logger.warning(f"GitHub authentication failed for user {current_user.id}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=e.message,
        )
    except GitHubPermissionError as e:
        logger.warning(f"GitHub permission denied for user {current_user.id} on repo {repo_id}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=e.message,
        )
    except GitHubAPIError as e:
        logger.error(f"GitHub API error listing branches: {e.message}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=e.message,
        )
    except Exception as e:
        logger.error(f"Failed to list branches: {e}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to fetch branches from GitHub",
        )


@router.get("/{repo_id}/commits", response_model=CommitListResponse)
async def list_commits(
    repo_id: UUID,
    current_user: CurrentUser,
    db: DbSession,
    branch: str | None = Query(default=None, description="Branch name (defaults to repository's default branch)"),
    per_page: int = Query(default=30, le=100, description="Number of commits to return"),
    page: int = Query(default=1, ge=1, description="Page number for pagination"),
) -> CommitListResponse:
    """List commits for a repository branch with analysis status.

    Requirements: 2.1, 2.2, 3.1, 3.2, 3.3, 3.4, 6.1, 6.4
    """
    from app.models.analysis import Analysis

    # Verify repository ownership
    result = await db.execute(
        select(Repository).where(
            Repository.id == repo_id,
            Repository.owner_id == current_user.id,
        )
    )
    repository = result.scalar_one_or_none()

    if not repository:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Repository not found",
        )

    # Default to repository's default branch
    target_branch = branch or repository.default_branch

    github_token = require_github_token(current_user)

    try:
        github = GitHubService(github_token)

        # Parse owner/repo from full_name
        owner, repo_name = repository.full_name.split("/")

        # Fetch commits via GitHubService (request one extra to detect has_more)
        commits = await github.list_commits(
            owner=owner,
            repo=repo_name,
            sha=target_branch,
            per_page=per_page + 1,
            page=page,
        )

        # Check if there are more commits
        has_more = len(commits) > per_page
        if has_more:
            commits = commits[:per_page]

        # Get commit SHAs for analysis lookup
        commit_shas = [commit["sha"] for commit in commits]

        # Query Analysis table for matching commit SHAs
        analysis_result = await db.execute(
            select(Analysis).where(
                Analysis.repository_id == repo_id,
                Analysis.commit_sha.in_(commit_shas),
            )
        )
        analyses = analysis_result.scalars().all()

        # Build lookup dict by commit SHA
        analysis_by_sha: dict[str, Analysis] = {
            analysis.commit_sha: analysis for analysis in analyses
        }

        # Enrich commits with analysis info
        commit_responses = []
        for commit in commits:
            analysis = analysis_by_sha.get(commit["sha"])

            commit_responses.append(
                CommitResponse(
                    sha=commit["sha"],
                    message=commit["message"],
                    author_name=commit["author_name"],
                    author_login=commit.get("author_login"),
                    author_avatar_url=commit.get("author_avatar_url"),
                    committed_at=commit["committed_at"],
                    # Analysis info (if analyzed)
                    analysis_id=analysis.id if analysis else None,
                    vci_score=float(analysis.vci_score) if analysis and analysis.vci_score else None,
                    analysis_status=analysis.status if analysis else None,
                )
            )

        return CommitListResponse(
            commits=commit_responses,
            branch=target_branch,
            page=page,
            has_more=has_more,
        )

    except GitHubTimeoutError as e:
        logger.warning(f"GitHub API timeout for user {current_user.id} on repo {repo_id}")
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=e.message,
        )
    except GitHubRateLimitError as e:
        logger.warning(f"GitHub rate limit exceeded for user {current_user.id}: {e.message}")
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=e.message,
        )
    except GitHubAuthenticationError as e:
        logger.warning(f"GitHub authentication failed for user {current_user.id}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=e.message,
        )
    except GitHubPermissionError as e:
        logger.warning(f"GitHub permission denied for user {current_user.id} on repo {repo_id}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=e.message,
        )
    except GitHubAPIError as e:
        logger.error(f"GitHub API error listing commits: {e.message}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=e.message,
        )
    except Exception as e:
        import traceback
        logger.error(f"Failed to list commits: {e}\n{traceback.format_exc()}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to fetch commits from GitHub: {str(e) or type(e).__name__}",
        )
