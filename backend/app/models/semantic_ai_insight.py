"""Semantic AI Insight model.

Stores AI-generated recommendations from the SemanticAIInsightsService.
Part of the Semantic AI Insights feature (separate from AI Scan).
"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModelNoUpdate

if TYPE_CHECKING:
    from app.models.analysis import Analysis
    from app.models.repository import Repository


class SemanticAIInsight(BaseModelNoUpdate):
    """Semantic AI Insight model.

    Represents an AI-generated recommendation based on architecture analysis.
    Uses LiteLLM directly (NOT BroadScanAgent) and is stored separately
    from ai_scan_cache.

    Requirements: 5.4
    """

    __tablename__ = "semantic_ai_insights"

    analysis_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("analyses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    repository_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("repositories.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    insight_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )  # 'dead_code', 'hot_spot', 'architecture'
    title: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )
    description: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    priority: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )  # 'high', 'medium', 'low'
    affected_files: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        server_default="'[]'::jsonb",
    )
    evidence: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    suggested_action: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    is_dismissed: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default="false",
    )
    dismissed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Relationships
    analysis: Mapped["Analysis"] = relationship(
        "Analysis",
        back_populates="semantic_ai_insights",
    )
    repository: Mapped["Repository"] = relationship(
        "Repository",
        back_populates="semantic_ai_insights",
    )

    def __repr__(self) -> str:
        return f"<SemanticAIInsight {self.insight_type}: {self.title[:50]}>"
