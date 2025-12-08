"""Dead code finding model.

Stores dead code findings detected through call graph analysis.
Part of the Semantic AI Insights feature.
"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModelNoUpdate

if TYPE_CHECKING:
    from app.models.analysis import Analysis
    from app.models.repository import Repository


class DeadCode(BaseModelNoUpdate):
    """Dead code finding model.

    Represents a function/method that is unreachable from any entry point,
    detected through call graph analysis.

    Requirements: 7.1
    """

    __tablename__ = "dead_code"

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
    file_path: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )
    function_name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
    )
    line_start: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    line_end: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    line_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    confidence: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        server_default="1.0",
    )
    evidence: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )
    suggested_action: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
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
        back_populates="dead_code_findings",
    )
    repository: Mapped["Repository"] = relationship(
        "Repository",
        back_populates="dead_code_findings",
    )

    def __repr__(self) -> str:
        return f"<DeadCode {self.file_path}:{self.function_name}>"
