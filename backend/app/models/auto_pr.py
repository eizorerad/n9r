"""AutoPR model."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.issue import Issue
    from app.models.repository import Repository


class AutoPR(BaseModel):
    """AutoPR model for automatically created pull requests."""

    __tablename__ = "auto_prs"

    repository_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("repositories.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    issue_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("issues.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    github_pr_number: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    github_pr_url: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    branch_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    base_branch: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    diff_content: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    test_code: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    files_changed: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    additions: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    deletions: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    test_status: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )
    test_output: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    review_feedback: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    validation_result: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
    )
    agent_logs: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
    )
    status: Mapped[str] = mapped_column(
        String(50),
        server_default="pending",
        nullable=False,
        index=True,
    )
    merged_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Relationships
    repository: Mapped["Repository"] = relationship(
        "Repository",
        back_populates="auto_prs",
    )
    issue: Mapped["Issue | None"] = relationship(
        "Issue",
        foreign_keys=[issue_id],
        backref="auto_pr",
    )

    def __repr__(self) -> str:
        return f"<AutoPR {self.title[:50]}>"
