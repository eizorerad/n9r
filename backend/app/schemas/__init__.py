"""Pydantic schemas for request/response validation."""

from app.schemas.analysis import (
    AnalysisCreate,
    AnalysisDetail,
    AnalysisResponse,
    AnalysisSummary,
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
