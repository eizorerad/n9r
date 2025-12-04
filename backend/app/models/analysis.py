"""Analysis model."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModelNoUpdate

if TYPE_CHECKING:
    from app.models.issue import Issue
    from app.models.repository import Repository


class Analysis(BaseModelNoUpdate):
    """Analysis model for repository code analysis."""

    __tablename__ = "analyses"

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
    branch: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(50),
        server_default="pending",
        nullable=False,
    )
    vci_score: Mapped[float | None] = mapped_column(
        Numeric(5, 2),
        nullable=True,
    )
    tech_debt_level: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
    )
    metrics: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
    )
    ai_report: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    semantic_cache: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
    )
    ai_scan_cache: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
    )

    # Relationships
    repository: Mapped["Repository"] = relationship(
        "Repository",
        back_populates="analyses",
    )
    issues: Mapped[list["Issue"]] = relationship(
        "Issue",
        back_populates="analysis",
        cascade="all, delete-orphan",
    )

    @property
    def grade(self) -> str | None:
        """Calculate grade from VCI score."""
        if self.vci_score is None:
            return None
        score = float(self.vci_score)
        if score >= 90:
            return "A"
        if score >= 80:
            return "B"
        if score >= 70:
            return "C"
        if score >= 60:
            return "D"
        return "F"

    def __repr__(self) -> str:
        return f"<Analysis {self.id} status={self.status}>"
