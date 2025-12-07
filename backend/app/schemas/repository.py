"""Repository schemas."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, model_validator

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


class BranchResponse(BaseSchema):
    """Branch information response.

    Requirements: 1.1, 1.2
    """

    name: str
    commit_sha: str
    is_default: bool
    is_protected: bool


class BranchListResponse(BaseSchema):
    """List of branches response.

    Requirements: 1.1, 1.2
    """

    data: list[BranchResponse]


class CommitResponse(BaseSchema):
    """Commit with analysis status response.

    Requirements: 2.1, 2.2, 2.3, 3.1, 3.2
    """

    sha: str
    short_sha: str  # First 7 characters of SHA
    message: str
    message_headline: str  # First line, max 80 chars
    author_name: str
    author_login: str | None = None
    author_avatar_url: str | None = None
    committed_at: datetime
    # Analysis info (if analyzed)
    analysis_id: UUID | None = None
    vci_score: float | None = None
    analysis_status: str | None = None

    @model_validator(mode="before")
    @classmethod
    def derive_short_sha_and_headline(cls, data: dict) -> dict:
        """Derive short_sha from sha and truncate message_headline.

        Property 4: Short SHA derivation - short_sha equals first 7 chars of sha
        Property 5: Message headline truncation - truncate to 80 chars if needed
        """
        if isinstance(data, dict):
            # Derive short_sha from sha if not provided
            if "sha" in data and "short_sha" not in data:
                data["short_sha"] = data["sha"][:7]

            # Derive message_headline from message if not provided
            if "message" in data and "message_headline" not in data:
                # Get first line of message
                first_line = data["message"].split("\n")[0]
                # Truncate to 80 characters
                if len(first_line) > 80:
                    data["message_headline"] = first_line[:80]
                else:
                    data["message_headline"] = first_line
            # If message_headline is provided, ensure it's truncated
            elif "message_headline" in data:
                headline = data["message_headline"]
                if len(headline) > 80:
                    data["message_headline"] = headline[:80]

        return data


class CommitListResponse(BaseSchema):
    """List of commits response.

    Requirements: 2.1, 2.2, 3.1, 3.2
    """

    commits: list[CommitResponse]
    branch: str
