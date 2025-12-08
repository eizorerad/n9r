"""Repository model."""

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.analysis import Analysis
    from app.models.auto_pr import AutoPR
    from app.models.chat import ChatThread
    from app.models.dead_code import DeadCode
    from app.models.issue import Issue
    from app.models.organization import Organization
    from app.models.semantic_ai_insight import SemanticAIInsight
    from app.models.user import User


class RepositoryMode(str, enum.Enum):
    """Repository monitoring mode."""

    VIEW_ONLY = "view_only"
    SUGGEST_PR = "suggest_pr"
    AUTO_HEAL = "auto_heal"


class TechDebtLevel(str, enum.Enum):
    """Technical debt level."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Repository(BaseModel):
    """Repository model for connected GitHub repositories."""

    __tablename__ = "repositories"

    github_id: Mapped[int] = mapped_column(
        BigInteger,
        unique=True,
        nullable=False,
        index=True,
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    org_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    full_name: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    language: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )
    default_branch: Mapped[str] = mapped_column(
        String(100),
        default="main",
        nullable=False,
    )
    mode: Mapped[str] = mapped_column(
        String(50),
        default="view_only",
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        index=True,
    )
    webhook_id: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
    )
    installation_id: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
    )
    last_analysis_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    vci_score: Mapped[float | None] = mapped_column(
        Numeric(5, 2),
        nullable=True,
    )
    tech_debt_level: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
    )

    # Relationships
    owner: Mapped["User | None"] = relationship(
        "User",
        back_populates="repositories",
    )
    organization: Mapped["Organization | None"] = relationship(
        "Organization",
        back_populates="repositories",
    )
    analyses: Mapped[list["Analysis"]] = relationship(
        "Analysis",
        back_populates="repository",
        cascade="all, delete-orphan",
    )
    issues: Mapped[list["Issue"]] = relationship(
        "Issue",
        back_populates="repository",
        cascade="all, delete-orphan",
    )
    auto_prs: Mapped[list["AutoPR"]] = relationship(
        "AutoPR",
        back_populates="repository",
        cascade="all, delete-orphan",
    )
    chat_threads: Mapped[list["ChatThread"]] = relationship(
        "ChatThread",
        back_populates="repository",
        cascade="all, delete-orphan",
    )
    dead_code_findings: Mapped[list["DeadCode"]] = relationship(
        "DeadCode",
        back_populates="repository",
        cascade="all, delete-orphan",
    )
    semantic_ai_insights: Mapped[list["SemanticAIInsight"]] = relationship(
        "SemanticAIInsight",
        back_populates="repository",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Repository {self.full_name}>"
