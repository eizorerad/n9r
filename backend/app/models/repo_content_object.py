"""Repository content object model for individual cached files."""

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModelNoUpdate

if TYPE_CHECKING:
    from app.models.repo_content_cache import RepoContentCache


class RepoContentObject(BaseModelNoUpdate):
    """Individual file object in the repository content cache.
    
    Stores metadata about each cached file in PostgreSQL,
    with actual file bytes stored in MinIO/S3 using object_key.
    
    Status values: 'uploading', 'ready', 'failed', 'deleted'
    """

    __tablename__ = "repo_content_objects"
    __table_args__ = (
        UniqueConstraint("cache_id", "path", name="uq_repo_content_objects_cache_path"),
    )

    cache_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("repo_content_cache.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    path: Mapped[str] = mapped_column(
        String(1024),
        nullable=False,
    )
    object_key: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    size_bytes: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    content_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(20),
        server_default="uploading",
        nullable=False,
    )

    # Relationships
    cache: Mapped["RepoContentCache"] = relationship(
        "RepoContentCache",
        back_populates="objects",
    )

    def __repr__(self) -> str:
        return f"<RepoContentObject {self.path} status={self.status}>"
