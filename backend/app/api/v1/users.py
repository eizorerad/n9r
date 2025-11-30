"""User endpoints."""

from fastapi import APIRouter

from app.api.deps import CurrentUser, DbSession
from app.schemas.user import UserResponse, UserUpdate

router = APIRouter()


@router.get("/me", response_model=UserResponse)
async def get_current_user(current_user: CurrentUser) -> UserResponse:
    """Get current authenticated user."""
    return UserResponse(
        id=current_user.id,
        github_id=current_user.github_id,
        username=current_user.username,
        email=current_user.email,
        avatar_url=current_user.avatar_url,
        created_at=current_user.created_at,
        organizations=[],  # TODO: Load organizations
    )


@router.patch("/me", response_model=UserResponse)
async def update_current_user(
    update: UserUpdate,
    current_user: CurrentUser,
    db: DbSession,
) -> UserResponse:
    """Update current user settings."""
    # TODO: Implement user settings update
    return UserResponse(
        id=current_user.id,
        github_id=current_user.github_id,
        username=current_user.username,
        email=current_user.email,
        avatar_url=current_user.avatar_url,
        created_at=current_user.created_at,
        organizations=[],
    )
