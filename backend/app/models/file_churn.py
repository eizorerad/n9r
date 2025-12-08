"""File churn (hot spot) model.

Stores file churn metrics and hot spot findings.
Part of the Semantic AI Insights feature.
"""

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModelNoUpdate

if TYPE_CHECKING:
    from app.models.analysis import Analysis


class FileChurn(BaseModelNoUpdate):
    """File churn (hot spot) finding model.

    Represents a file with high code churn, indicating potential risk.
    Includes coverage data when available.

    Requirements: 7.2
    """

    __tablename__ = "file_churn"
    __table_args__ = (
        UniqueConstraint("analysis_id", "file_path", name="uq_file_churn_analysis_file"),
    )

    analysis_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("analyses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    file_path: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )
    changes_90d: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default="0",
    )
    coverage_rate: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )
    unique_authors: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default="0",
    )
    risk_factors: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        server_default="'[]'::jsonb",
    )
    suggested_action: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    # Relationships
    analysis: Mapped["Analysis"] = relationship(
        "Analysis",
        back_populates="file_churn_findings",
    )

    @property
    def is_hot_spot(self) -> bool:
        """Check if this file qualifies as a hot spot (>10 changes in 90 days)."""
        return self.changes_90d > 10

    def __repr__(self) -> str:
        return f"<FileChurn {self.file_path} changes={self.changes_90d}>"
