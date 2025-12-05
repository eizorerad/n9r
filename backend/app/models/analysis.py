"""Analysis model."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text, func
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

    # AI Scan tracking columns (Requirements 2.1)
    # Valid values: 'none', 'pending', 'running', 'completed', 'failed', 'skipped'
    ai_scan_status: Mapped[str] = mapped_column(
        String(20),
        server_default="none",
        nullable=False,
    )
    # Progress percentage (0-100)
    ai_scan_progress: Mapped[int] = mapped_column(
        Integer,
        server_default="0",
        nullable=False,
    )
    # Current stage: 'initializing', 'cloning', 'generating_view', 'scanning', 'merging', 'investigating', 'completed'
    ai_scan_stage: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )
    # Human-readable progress message
    ai_scan_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    # Error message if ai_scan_status is 'failed'
    ai_scan_error: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    # Timestamp when AI scan started
    ai_scan_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    # Timestamp when AI scan completed
    ai_scan_completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Embeddings tracking columns (Requirements 2.1, 2.2, 2.3, 2.4)
    # Valid values: 'none', 'pending', 'running', 'completed', 'failed'
    embeddings_status: Mapped[str] = mapped_column(
        String(20),
        server_default="none",
        nullable=False,
    )
    # Progress percentage (0-100)
    embeddings_progress: Mapped[int] = mapped_column(
        Integer,
        server_default="0",
        nullable=False,
    )
    # Current stage: 'initializing', 'chunking', 'embedding', 'indexing', 'completed'
    embeddings_stage: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )
    # Human-readable progress message
    embeddings_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    # Error message if embeddings_status is 'failed'
    embeddings_error: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    # Timestamp when embeddings generation started
    embeddings_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    # Timestamp when embeddings generation completed
    embeddings_completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    # Number of vectors stored in Qdrant
    vectors_count: Mapped[int] = mapped_column(
        Integer,
        server_default="0",
        nullable=False,
    )

    # Semantic cache status tracking (Requirements 3.1, 3.2)
    # Valid values: 'none', 'pending', 'computing', 'completed', 'failed'
    semantic_cache_status: Mapped[str] = mapped_column(
        String(20),
        server_default="none",
        nullable=False,
    )

    # Timestamp for polling optimization (Requirements 1.4)
    state_updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
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
