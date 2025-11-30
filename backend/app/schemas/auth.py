"""Authentication schemas."""

from uuid import UUID

from pydantic import BaseModel, EmailStr

from app.schemas.common import BaseSchema


class AuthRequest(BaseModel):
    """OAuth initiation request."""

    redirect_uri: str


class AuthURL(BaseModel):
    """OAuth authorization URL response."""

    authorization_url: str


class AuthCallback(BaseModel):
    """OAuth callback request (with state for backend-initiated flow)."""

    code: str
    state: str


class AuthCallbackSimple(BaseModel):
    """OAuth callback request (frontend-initiated flow, state checked on frontend)."""

    code: str


class UserInfo(BaseSchema):
    """User info in auth response."""

    id: UUID
    username: str
    email: EmailStr | None = None
    avatar_url: str | None = None


class AuthResponse(BaseModel):
    """Authentication response with tokens."""

    access_token: str
    token_type: str = "Bearer"
    expires_in: int
    user: UserInfo


class TokenRefresh(BaseModel):
    """Token refresh response."""

    access_token: str
    expires_in: int
