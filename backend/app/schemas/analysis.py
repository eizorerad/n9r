"""Analysis schemas."""

from datetime import datetime
from enum import Enum
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel

from app.schemas.common import BaseSchema


class AnalysisStatus(str, Enum):
    """Analysis status enum for schemas."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class TriggerType(str, Enum):
    """Trigger type enum for schemas."""
    SCHEDULED = "scheduled"
    WEBHOOK = "webhook"
    MANUAL = "manual"


class AnalysisCreate(BaseModel):
    """Analysis creation request."""

    commit_sha: str | None = None


class RepositoryInfo(BaseSchema):
    """Repository info in analysis response."""

    id: UUID
    full_name: str


class IssuesSummary(BaseModel):
    """Issues summary by severity."""

    critical: int = 0
    high: int = 0
    medium: int = 0
    low: int = 0


class AnalysisSummary(BaseSchema):
    """Analysis list response."""

    id: UUID
    commit_sha: str
    status: AnalysisStatus
    trigger_type: TriggerType
    vci_score: float | None = None
    issues_found: int = 0
    started_at: datetime | None = None
    completed_at: datetime | None = None


class MetricsComplexity(BaseModel):
    """Complexity metrics."""

    avg: float
    max: int
    files_above_threshold: int


class MetricsDuplication(BaseModel):
    """Duplication metrics."""

    ratio: float
    total_lines: int = 0
    duplicate_blocks: int


class MetricsHeuristics(BaseModel):
    """Hard heuristics metrics."""

    long_functions: int = 0
    long_files: int = 0
    low_comment_density: int = 0


class MetricsArchitecture(BaseModel):
    """Architecture metrics."""

    consistency_score: float
    violations: list[str] = []


class AnalysisMetrics(BaseModel):
    """Full analysis metrics."""

    cyclomatic_complexity: MetricsComplexity | None = None
    duplication: MetricsDuplication | None = None
    hard_heuristics: MetricsHeuristics | None = None
    architecture: MetricsArchitecture | None = None


class AnalysisResponse(BaseSchema):
    """Analysis creation response."""

    id: UUID
    status: AnalysisStatus
    created_at: datetime


class AnalysisDetail(BaseSchema):
    """Analysis detail response."""

    id: UUID
    repository: RepositoryInfo
    commit_sha: str
    status: AnalysisStatus
    trigger_type: TriggerType
    vci_score: float | None = None
    metrics: AnalysisMetrics | None = None
    issues_summary: IssuesSummary
    report_url: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
