"""Repository schemas."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

from app.models.repository import RepositoryMode, TechDebtLevel
from app.schemas.common import BaseSchema


class RepositoryConnect(BaseModel):
    """Repository connection request."""

    github_id: int
    org_id: UUID | None = None
    mode: RepositoryMode = RepositoryMode.VIEW_ONLY


class VCITrendPoint(BaseModel):
    """VCI trend data point."""

    date: str
    score: float


class LastAnalysisInfo(BaseSchema):
    """Last analysis info."""

    id: UUID
    status: str
    completed_at: datetime | None = None


class RepositoryStats(BaseModel):
    """Repository statistics."""

    total_analyses: int
    total_prs_created: int
    prs_merged: int
    prs_rejected: int


class RepositoryResponse(BaseSchema):
    """Repository list response."""

    id: UUID
    github_id: int
    name: str
    full_name: str
    default_branch: str
    mode: RepositoryMode
    is_active: bool
    vci_score: float | None = None
    tech_debt_level: TechDebtLevel | None = None
    last_analysis_at: datetime | None = None
    pending_prs_count: int = 0
    open_issues_count: int = 0


class RepositoryDetail(BaseSchema):
    """Repository detail response."""

    id: UUID
    github_id: int
    name: str
    full_name: str
    default_branch: str
    mode: RepositoryMode
    is_active: bool
    vci_score: float | None = None
    vci_trend: list[VCITrendPoint] = []
    tech_debt_level: TechDebtLevel | None = None
    last_analysis: LastAnalysisInfo | None = None
    stats: RepositoryStats
    created_at: datetime


class RepositoryUpdate(BaseModel):
    """Repository update request."""

    mode: RepositoryMode | None = None
    is_active: bool | None = None


class AvailableRepository(BaseModel):
    """Available GitHub repository."""

    github_id: int
    name: str
    full_name: str
    private: bool
    default_branch: str
    language: str | None = None
    description: str | None = None
    is_connected: bool


class FileTreeItem(BaseModel):
    """File tree item."""

    name: str
    path: str
    type: Literal["file", "directory"]
    size: int | None = None


class FileContent(BaseModel):
    """File content response."""

    path: str
    content: str
    encoding: str = "utf-8"
    size: int
    language: str | None = None
