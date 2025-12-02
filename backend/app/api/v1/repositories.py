"""Repository endpoints."""

import logging
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select

from app.api.deps import CurrentUser, DbSession
from app.models.repository import Repository
from app.schemas.common import PaginatedResponse, PaginationMeta
from app.schemas.repository import (
    AvailableRepository,
    RepositoryConnect,
    RepositoryDetail,
    RepositoryResponse,
    RepositoryStats,
    RepositoryUpdate,
)
from app.services.github import GitHubService
from app.core.encryption import decrypt_token_or_none

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
    # Get user's GitHub token
    github_token = decrypt_token_or_none(current_user.access_token_encrypted)
    
    if not github_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="GitHub token not found. Please re-authenticate.",
        )
    
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
    
    # Get user's GitHub token
    github_token = decrypt_token_or_none(current_user.access_token_encrypted)
    
    if not github_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="GitHub token not found. Please re-authenticate.",
        )
    
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
        
        # Create initial analysis record
        from app.models.analysis import Analysis
        analysis = Analysis(
            repository_id=repository.id,
            commit_sha="HEAD",
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
            commit_sha=None,
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
    from app.schemas.repository import FileTreeItem
    
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
    
    # Get user's GitHub token
    github_token = decrypt_token_or_none(current_user.access_token_encrypted)
    
    if not github_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="GitHub token not found. Please re-authenticate.",
        )
    
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


@router.get("/{repo_id}/files/{file_path:path}")
async def get_repository_file_content(
    repo_id: UUID,
    file_path: str,
    current_user: CurrentUser,
    db: DbSession,
    ref: str | None = Query(default=None, description="Git reference (branch/commit)"),
) -> dict:
    """Get content of a specific file."""
    from app.schemas.repository import FileContent
    
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
    
    # Get user's GitHub token
    github_token = decrypt_token_or_none(current_user.access_token_encrypted)
    
    if not github_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="GitHub token not found. Please re-authenticate.",
        )
    
    try:
        github = GitHubService(github_token)
        
        # Parse owner/repo from full_name
        owner, repo_name = repository.full_name.split("/")
        
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
    except Exception as e:
        logger.error(f"Failed to get file content: {e}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to fetch file from GitHub",
        )
