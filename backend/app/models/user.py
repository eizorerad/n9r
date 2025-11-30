"""User model."""

from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.chat import ChatThread
    from app.models.organization import Member, Organization
    from app.models.repository import Repository


class User(BaseModel):
    """User model - authenticated via GitHub OAuth."""

    __tablename__ = "users"

    github_id: Mapped[int] = mapped_column(
        BigInteger,
        unique=True,
        nullable=False,
        index=True,
    )
    username: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    email: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )
    avatar_url: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    access_token_encrypted: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # Relationships
    owned_organizations: Mapped[list["Organization"]] = relationship(
        "Organization",
        back_populates="owner",
        cascade="all, delete-orphan",
    )
    memberships: Mapped[list["Member"]] = relationship(
        "Member",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    repositories: Mapped[list["Repository"]] = relationship(
        "Repository",
        back_populates="owner",
        cascade="all, delete-orphan",
    )
    chat_threads: Mapped[list["ChatThread"]] = relationship(
        "ChatThread",
        back_populates="user",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<User {self.username}>"
