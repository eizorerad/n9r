"""Organization and Member models."""

import enum
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Enum, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.repository import Repository
    from app.models.subscription import Subscription
    from app.models.user import User


class PlanType(str, enum.Enum):
    """Subscription plan types."""

    SOLO = "solo"
    TEAM = "team"
    PRO = "pro"
    ENTERPRISE = "enterprise"


class MemberRole(str, enum.Enum):
    """Organization member roles."""

    OWNER = "owner"
    MAINTAINER = "maintainer"
    VIEWER = "viewer"


class Organization(BaseModel):
    """Organization model for team workspaces.
    
    Supports both SaaS multi-tenancy (owner_id, slug, plan) and
    GitHub organization integration (github_id, installation_id).
    """

    __tablename__ = "organizations"

    # SaaS organization fields
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    slug: Mapped[str | None] = mapped_column(
        String(100),
        unique=True,
        nullable=True,
        index=True,
    )
    plan: Mapped[PlanType] = mapped_column(
        Enum(PlanType),
        default=PlanType.SOLO,
        nullable=False,
    )

    # GitHub organization fields (for org-level integrations)
    github_id: Mapped[int | None] = mapped_column(
        BigInteger,
        unique=True,
        nullable=True,
        index=True,
    )
    display_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    avatar_url: Mapped[str | None] = mapped_column(
        String(512),
        nullable=True,
    )
    installation_id: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
    )

    # Relationships
    owner: Mapped["User"] = relationship(
        "User",
        back_populates="owned_organizations",
    )
    members: Mapped[list["Member"]] = relationship(
        "Member",
        back_populates="organization",
        cascade="all, delete-orphan",
    )
    repositories: Mapped[list["Repository"]] = relationship(
        "Repository",
        back_populates="organization",
        cascade="all, delete-orphan",
    )
    subscriptions: Mapped[list["Subscription"]] = relationship(
        "Subscription",
        back_populates="organization",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Organization {self.name}>"


class Member(BaseModel):
    """Organization member model."""

    __tablename__ = "members"

    __table_args__ = (
        UniqueConstraint("org_id", "user_id", name="uq_member_org_user"),
    )

    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[MemberRole] = mapped_column(
        Enum(MemberRole),
        default=MemberRole.VIEWER,
        nullable=False,
    )

    # Relationships
    organization: Mapped["Organization"] = relationship(
        "Organization",
        back_populates="members",
    )
    user: Mapped["User"] = relationship(
        "User",
        back_populates="memberships",
    )

    def __repr__(self) -> str:
        return f"<Member {self.user_id} in {self.org_id}>"
