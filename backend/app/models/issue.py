"""Issue model."""

import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.analysis import Analysis
    from app.models.repository import Repository


class Issue(BaseModel):
    """Issue model for detected code problems."""

    __tablename__ = "issues"

    repository_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("repositories.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    analysis_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("analyses.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )
    severity: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    file_path: Mapped[str | None] = mapped_column(
        String(512),
        nullable=True,
    )
    line_start: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    line_end: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    status: Mapped[str] = mapped_column(
        String(50),
        server_default="open",
        nullable=False,
        index=True,
    )
    confidence: Mapped[float | None] = mapped_column(
        Numeric(3, 2),
        nullable=True,
    )
    issue_metadata: Mapped[dict[str, Any] | None] = mapped_column(
        "metadata",  # Column name in DB
        JSONB,
        nullable=True,
    )

    # Relationships
    analysis: Mapped["Analysis | None"] = relationship(
        "Analysis",
        back_populates="issues",
    )
    repository: Mapped["Repository"] = relationship(
        "Repository",
        back_populates="issues",
    )

    @property
    def auto_fixable(self) -> bool:
        """Check if issue has a suggested fix in metadata."""
        if self.issue_metadata:
            return bool(self.issue_metadata.get("suggestion"))
        return False

    def __repr__(self) -> str:
        return f"<Issue {self.title[:50] if self.title else 'Untitled'}>"
