"""Issue schemas."""

from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel

from app.schemas.common import BaseSchema


class IssueType(str, Enum):
    """Issue type enum for schemas."""
    CODE_QUALITY = "code_quality"
    DATABASE = "database"
    INTEGRATION = "integration"
    DOCUMENTATION = "documentation"
    COMPLEXITY = "complexity"
    DUPLICATION = "duplication"
    SECURITY = "security"


class IssueSeverity(str, Enum):
    """Issue severity enum for schemas."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class IssueStatus(str, Enum):
    """Issue status enum for schemas."""
    OPEN = "open"
    FIXED = "fixed"
    IGNORED = "ignored"
    WONT_FIX = "wont_fix"


class RelatedFile(BaseModel):
    """Related file info."""

    path: str
    line_start: int
    line_end: int


class AutoPRInfo(BaseSchema):
    """Auto-PR info in issue response."""

    id: UUID
    status: str
    github_pr_url: str | None = None


class RepositoryInfo(BaseSchema):
    """Repository info in issue response."""

    id: UUID
    full_name: str


class IssueResponse(BaseSchema):
    """Issue list response."""

    id: UUID
    type: IssueType
    category: str
    severity: IssueSeverity
    title: str
    file_path: str
    line_start: int | None = None
    line_end: int | None = None
    confidence: float
    status: IssueStatus
    created_at: datetime


class IssueDetail(BaseSchema):
    """Issue detail response."""

    id: UUID
    repository: RepositoryInfo
    analysis_id: UUID
    type: IssueType
    category: str
    severity: IssueSeverity
    title: str
    description: str
    file_path: str
    line_start: int | None = None
    line_end: int | None = None
    code_snippet: str | None = None
    related_files: list[RelatedFile] = []
    suggestion: str | None = None
    confidence: float
    status: IssueStatus
    auto_pr: AutoPRInfo | None = None
    created_at: datetime


class IssueUpdate(BaseModel):
    """Issue update request."""

    status: IssueStatus | None = None
    ignore_reason: str | None = None


class FixRequest(BaseModel):
    """Issue fix request response."""

    auto_pr_id: UUID
    status: str
