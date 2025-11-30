"""User schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr

from app.schemas.common import BaseSchema


class OrganizationMembership(BaseSchema):
    """Organization membership in user response."""

    id: UUID
    name: str
    slug: str
    role: str


class UserResponse(BaseSchema):
    """User response schema."""

    id: UUID
    github_id: int
    username: str
    email: EmailStr | None = None
    avatar_url: str | None = None
    created_at: datetime
    organizations: list[OrganizationMembership] = []


class UserUpdate(BaseModel):
    """User update request."""

    email_notifications: bool | None = None
    weekly_digest: bool | None = None
