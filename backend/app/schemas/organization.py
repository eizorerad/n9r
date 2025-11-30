"""Organization schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.models.organization import MemberRole, PlanType
from app.schemas.common import BaseSchema


class OrganizationCreate(BaseModel):
    """Organization creation request."""

    name: str
    slug: str


class OwnerInfo(BaseSchema):
    """Owner info in organization response."""

    id: UUID
    username: str


class SubscriptionInfo(BaseSchema):
    """Subscription info in organization response."""

    status: str
    current_period_end: datetime | None = None


class OrganizationLimits(BaseModel):
    """Organization limits."""

    max_repos: int
    used_repos: int


class OrganizationResponse(BaseSchema):
    """Organization list response."""

    id: UUID
    name: str
    slug: str
    plan: PlanType
    role: MemberRole
    members_count: int = 0
    repos_count: int = 0
    created_at: datetime


class OrganizationDetail(BaseSchema):
    """Organization detail response."""

    id: UUID
    name: str
    slug: str
    plan: PlanType
    owner: OwnerInfo
    subscription: SubscriptionInfo | None = None
    limits: OrganizationLimits
    created_at: datetime


class UserInfo(BaseSchema):
    """User info in member response."""

    id: UUID
    username: str
    avatar_url: str | None = None


class MemberResponse(BaseSchema):
    """Member response."""

    id: UUID
    user: UserInfo
    role: MemberRole
    joined_at: datetime


class MemberCreate(BaseModel):
    """Member creation request."""

    github_username: str
    role: MemberRole = MemberRole.VIEWER
