"""Architecture findings API response schemas.

Defines Pydantic schemas for architecture findings API endpoints.
These schemas are used for serializing database models to API responses.

Requirements: 6.1, 6.2
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import BaseSchema


class DeadCodeFindingSchema(BaseSchema):
    """Dead code finding response schema.

    Represents a function that is unreachable from any entry point.

    Requirements: 6.3
    """

    id: UUID
    file_path: str
    function_name: str
    line_start: int
    line_end: int
    line_count: int
    confidence: float = Field(..., ge=0.0, le=1.0, description="1.0 = call-graph proven")
    evidence: str
    suggested_action: str
    is_dismissed: bool
    dismissed_at: datetime | None = None
    created_at: datetime


class HotSpotFindingSchema(BaseSchema):
    """Hot spot finding response schema.

    Represents a file with high code churn and/or low test coverage.

    Requirements: 6.4
    """

    id: UUID
    file_path: str
    changes_90d: int = Field(..., ge=0, description="Number of changes in last 90 days")
    coverage_rate: float | None = Field(None, ge=0.0, le=1.0, description="Test coverage rate")
    unique_authors: int = Field(..., ge=0, description="Number of unique authors")
    risk_factors: list[str] = Field(default_factory=list, description="List of risk factors")
    suggested_action: str | None = None
    created_at: datetime


class SemanticAIInsightSchema(BaseSchema):
    """Semantic AI insight response schema.

    Represents an AI-generated recommendation based on architecture analysis.

    Requirements: 6.1, 6.2
    """

    id: UUID
    insight_type: str = Field(..., description="Type: 'dead_code', 'hot_spot', 'architecture'")
    title: str
    description: str
    priority: str = Field(..., description="Priority: 'high', 'medium', 'low'")
    affected_files: list[str] = Field(default_factory=list)
    evidence: str | None = None
    suggested_action: str | None = None
    is_dismissed: bool
    dismissed_at: datetime | None = None
    created_at: datetime


class ArchitectureSummarySchema(BaseModel):
    """Architecture summary response schema.

    Provides an overview of the repository's architecture health.

    Requirements: 6.1
    """

    health_score: int = Field(..., ge=0, le=100, description="Overall health score 0-100")
    main_concerns: list[str] = Field(default_factory=list, description="Main architecture concerns")
    dead_code_count: int = Field(..., ge=0, description="Number of dead code findings")
    hot_spot_count: int = Field(..., ge=0, description="Number of hot spot findings")
    insights_count: int = Field(..., ge=0, description="Number of AI insights")


class ArchitectureFindingsResponse(BaseModel):
    """Complete architecture findings response.

    Contains all architecture analysis findings for a repository/analysis.

    Requirements: 6.1, 6.2
    """

    summary: ArchitectureSummarySchema
    dead_code: list[DeadCodeFindingSchema] = Field(default_factory=list)
    hot_spots: list[HotSpotFindingSchema] = Field(default_factory=list)
    insights: list[SemanticAIInsightSchema] = Field(default_factory=list)


class DismissDeadCodeRequest(BaseModel):
    """Request to dismiss a dead code finding."""

    pass  # No body needed, just the endpoint call


class DismissInsightRequest(BaseModel):
    """Request to dismiss a semantic AI insight."""

    pass  # No body needed, just the endpoint call
