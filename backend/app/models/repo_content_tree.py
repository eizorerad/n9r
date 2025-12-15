"""Repository content tree model for cached directory structure."""

import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModelNoUpdate

if TYPE_CHECKING:
    from app.models.repo_content_cache import RepoContentCache


class RepoContentTree(BaseModelNoUpdate):
    """Cached tree structure for fast directory listings.
    
    Stores the complete file/directory tree as JSONB for fast retrieval
    without needing to query individual file objects.
    
    Tree format: ["src/", "src/main.py", "src/utils/", ...]
    """

    __tablename__ = "repo_content_tree"
    __table_args__ = (
        UniqueConstraint("cache_id", name="uq_repo_content_tree_cache"),
    )

    cache_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("repo_content_cache.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tree: Mapped[list[Any]] = mapped_column(
        JSONB,
        nullable=False,
    )

    # Relationships
    cache: Mapped["RepoContentCache"] = relationship(
        "RepoContentCache",
        back_populates="tree",
    )

    def __repr__(self) -> str:
        tree_len = len(self.tree) if self.tree else 0
        return f"<RepoContentTree cache_id={self.cache_id} entries={tree_len}>"
