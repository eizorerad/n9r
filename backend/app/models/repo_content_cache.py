"""Repository content cache model for storing file metadata."""

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.repo_content_object import RepoContentObject
    from app.models.repo_content_tree import RepoContentTree
    from app.models.repository import Repository


class RepoContentCache(BaseModel):
    """Repository content cache metadata for a specific commit.

    Stores metadata about cached repository content in PostgreSQL,
    with actual file bytes stored in MinIO/S3.

    Status values: 'pending', 'uploading', 'ready', 'failed'
    """

    __tablename__ = "repo_content_cache"
    __table_args__ = (
        UniqueConstraint("repository_id", "commit_sha", name="uq_repo_content_cache_repo_commit"),
    )

    repository_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("repositories.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    commit_sha: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(20),
        server_default="pending",
        nullable=False,
    )
    file_count: Mapped[int] = mapped_column(
        Integer,
        server_default="0",
        nullable=False,
    )
    total_size_bytes: Mapped[int] = mapped_column(
        BigInteger,
        server_default="0",
        nullable=False,
    )
    version: Mapped[int] = mapped_column(
        Integer,
        server_default="1",
        nullable=False,
    )

    # Relationships
    repository: Mapped["Repository"] = relationship(
        "Repository",
        back_populates="content_caches",
    )
    objects: Mapped[list["RepoContentObject"]] = relationship(
        "RepoContentObject",
        back_populates="cache",
        cascade="all, delete-orphan",
    )
    tree: Mapped["RepoContentTree | None"] = relationship(
        "RepoContentTree",
        back_populates="cache",
        uselist=False,
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<RepoContentCache {self.repository_id}@{self.commit_sha[:7]} status={self.status}>"
