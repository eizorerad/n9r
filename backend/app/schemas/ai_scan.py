"""AI Scan schemas for request/response validation.

Implements Pydantic schemas for AI-powered code analysis feature.
"""

from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.schemas.common import BaseSchema

# =============================================================================
# Enums for AI Scan
# =============================================================================


class AIScanDimension(str, Enum):
    """Issue dimension categories for AI scan."""

    SECURITY = "security"
    DB_CONSISTENCY = "db_consistency"
    API_CORRECTNESS = "api_correctness"
    CODE_HEALTH = "code_health"
    OTHER = "other"


class AIScanSeverity(str, Enum):
    """Issue severity levels for AI scan."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class AIScanConfidence(str, Enum):
    """Confidence levels for AI-detected issues."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class AIScanStatus(str, Enum):
    """Status of an AI scan."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class InvestigationStatus(str, Enum):
    """Investigation status for validated issues."""

    CONFIRMED = "confirmed"
    LIKELY_REAL = "likely_real"
    UNCERTAIN = "uncertain"
    INVALID = "invalid"


# =============================================================================
# Request Schemas
# =============================================================================


class AIScanRequest(BaseModel):
    """Request to trigger AI scan.

    Allows configuration of which models to use and investigation parameters.
    """

    models: list[str] = Field(
        default=[
            "gemini/gemini-3-pro-preview",
            "bedrock/anthropic.claude-sonnet-4-5-20250929-v1:0",
        ],
        description="LLM models to use for scanning",
    )
    investigate_severity: list[AIScanSeverity] = Field(
        default=[AIScanSeverity.CRITICAL, AIScanSeverity.HIGH],
        description="Severity levels to investigate",
    )
    max_issues_to_investigate: int = Field(
        default=10,
        ge=0,
        le=50,
        description="Maximum number of issues to investigate",
    )

    @field_validator("models")
    @classmethod
    def validate_models(cls, v: list[str]) -> list[str]:
        """Ensure at least one model is specified."""
        if not v:
            raise ValueError("At least one model must be specified")
        return v


# =============================================================================
# File Location Schema
# =============================================================================


class FileLocation(BaseModel):
    """Location of an issue within a file."""

    path: str = Field(..., min_length=1, description="File path")
    line_start: int = Field(..., ge=1, description="Starting line number")
    line_end: int = Field(..., ge=1, description="Ending line number")

    @field_validator("line_end")
    @classmethod
    def validate_line_end(cls, v: int, info) -> int:
        """Ensure line_end >= line_start."""
        line_start = info.data.get("line_start")
        if line_start is not None and v < line_start:
            raise ValueError("line_end must be >= line_start")
        return v


# =============================================================================
# Issue Schemas
# =============================================================================


class AIScanIssue(BaseModel):
    """AI-detected issue in the codebase.

    Represents a consolidated issue found by one or more LLM models.
    """

    id: str = Field(..., min_length=1, description="Unique issue ID (e.g., 'sec-001')")
    dimension: AIScanDimension = Field(..., description="Issue category")
    severity: AIScanSeverity = Field(..., description="Issue severity level")
    title: str = Field(..., min_length=1, max_length=200, description="Issue title")
    summary: str = Field(..., min_length=1, description="Issue summary")
    files: list[FileLocation] = Field(
        ..., min_length=1, description="Affected file locations"
    )
    evidence_snippets: list[str] = Field(
        default_factory=list, description="Code snippets as evidence"
    )
    confidence: AIScanConfidence = Field(..., description="Detection confidence")
    found_by_models: list[str] = Field(
        ..., min_length=1, description="Models that detected this issue"
    )
    investigation_status: InvestigationStatus | None = Field(
        default=None, description="Investigation result status"
    )
    suggested_fix: str | None = Field(
        default=None, description="Suggested fix from investigation"
    )


# =============================================================================
# Repo Overview Schema
# =============================================================================


class RepoOverview(BaseModel):
    """Overview of the repository from AI analysis."""

    guessed_project_type: str = Field(
        ..., description="Guessed project type (e.g., 'FastAPI backend + Next.js frontend')"
    )
    main_languages: list[str] = Field(
        default_factory=list, description="Main programming languages detected"
    )
    main_components: list[str] = Field(
        default_factory=list, description="Main architectural components"
    )


# =============================================================================
# Response Schemas
# =============================================================================


class AIScanCacheResponse(BaseSchema):
    """Response for AI scan cache endpoint.

    Returns cached AI scan results tied to a specific analysis.
    """

    analysis_id: UUID = Field(..., description="Parent analysis ID")
    commit_sha: str = Field(..., description="Commit SHA the scan was run against")
    status: AIScanStatus = Field(..., description="Scan status")
    repo_overview: RepoOverview | None = Field(
        default=None, description="Repository overview from AI"
    )
    issues: list[AIScanIssue] = Field(
        default_factory=list, description="Detected issues"
    )
    computed_at: datetime | None = Field(
        default=None, description="When the scan completed"
    )
    is_cached: bool = Field(..., description="Whether results are from cache")
    total_tokens_used: int | None = Field(
        default=None, ge=0, description="Total tokens consumed"
    )
    total_cost_usd: float | None = Field(
        default=None, ge=0, description="Total cost in USD"
    )


class AIScanTriggerResponse(BaseModel):
    """Response when triggering an AI scan."""

    analysis_id: UUID = Field(..., description="Analysis ID")
    status: AIScanStatus = Field(
        default=AIScanStatus.PENDING, description="Initial scan status"
    )
    message: str = Field(..., description="Status message")


class AIScanProgressEvent(BaseModel):
    """SSE progress event for AI scan streaming."""

    stage: str = Field(..., description="Current stage of the scan")
    progress: int = Field(..., ge=0, le=100, description="Progress percentage")
    message: str = Field(..., description="Human-readable progress message")
