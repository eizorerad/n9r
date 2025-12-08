"""Pydantic schemas for request/response validation."""

from app.schemas.ai_scan import (
    AIScanCacheResponse,
    AIScanConfidence,
    AIScanDimension,
    AIScanIssue,
    AIScanProgressEvent,
    AIScanRequest,
    AIScanSeverity,
    AIScanStatus,
    AIScanTriggerResponse,
    FileLocation,
    InvestigationStatus,
    RepoOverview,
)
from app.schemas.analysis import (
    AnalysisCreate,
    AnalysisDetail,
    AnalysisResponse,
    AnalysisSummary,
)
from app.schemas.architecture_findings import (
    ArchitectureFindingsResponse,
    ArchitectureSummarySchema,
    DeadCodeFindingSchema,
    DismissDeadCodeRequest,
    DismissInsightRequest,
    HotSpotFindingSchema,
    SemanticAIInsightSchema,
)
from app.schemas.architecture_llm import (
    ArchitectureIssue,
    ArchitectureSummary,
    DeadCodeFinding,
    HotSpotFinding,
    LLMReadyArchitectureData,
)
from app.schemas.auth import (
    AuthCallback,
    AuthResponse,
    TokenRefresh,
)
from app.schemas.chat import (
    ChatMessageCreate,
    ChatMessageResponse,
    ChatThreadCreate,
    ChatThreadResponse,
)
from app.schemas.issue import (
    IssueDetail,
    IssueResponse,
    IssueUpdate,
)
from app.schemas.organization import (
    MemberCreate,
    MemberResponse,
    OrganizationCreate,
    OrganizationDetail,
    OrganizationResponse,
)
from app.schemas.repository import (
    BranchListResponse,
    BranchResponse,
    CommitListResponse,
    CommitResponse,
    FileContent,
    FileTreeItem,
    RepositoryConnect,
    RepositoryDetail,
    RepositoryResponse,
    RepositoryUpdate,
)
from app.schemas.user import (
    UserResponse,
    UserUpdate,
)

__all__ = [
    # AI Scan
    "AIScanRequest",
    "AIScanIssue",
    "AIScanCacheResponse",
    "AIScanTriggerResponse",
    "AIScanProgressEvent",
    "AIScanDimension",
    "AIScanSeverity",
    "AIScanConfidence",
    "AIScanStatus",
    "InvestigationStatus",
    "FileLocation",
    "RepoOverview",
    # Architecture Findings (API responses)
    "ArchitectureFindingsResponse",
    "ArchitectureSummarySchema",
    "DeadCodeFindingSchema",
    "HotSpotFindingSchema",
    "SemanticAIInsightSchema",
    "DismissDeadCodeRequest",
    "DismissInsightRequest",
    # Architecture LLM (internal dataclasses)
    "ArchitectureSummary",
    "DeadCodeFinding",
    "HotSpotFinding",
    "ArchitectureIssue",
    "LLMReadyArchitectureData",
    # Auth
    "AuthCallback",
    "AuthResponse",
    "TokenRefresh",
    # User
    "UserResponse",
    "UserUpdate",
    # Organization
    "OrganizationCreate",
    "OrganizationResponse",
    "OrganizationDetail",
    "MemberCreate",
    "MemberResponse",
    # Repository
    "RepositoryConnect",
    "RepositoryResponse",
    "RepositoryDetail",
    "RepositoryUpdate",
    "FileTreeItem",
    "FileContent",
    "BranchResponse",
    "BranchListResponse",
    "CommitResponse",
    "CommitListResponse",
    # Analysis
    "AnalysisCreate",
    "AnalysisResponse",
    "AnalysisSummary",
    "AnalysisDetail",
    # Issue
    "IssueResponse",
    "IssueDetail",
    "IssueUpdate",
    # Chat
    "ChatThreadCreate",
    "ChatThreadResponse",
    "ChatMessageCreate",
    "ChatMessageResponse",
]
