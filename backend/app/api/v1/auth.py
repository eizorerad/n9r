"""Authentication endpoints."""

import logging
import secrets
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import DbSession

logger = logging.getLogger(__name__)
from app.core.config import settings
from app.core.encryption import encrypt_token
from app.core.redis import delete_oauth_state, get_oauth_state, store_oauth_state
from app.core.security import create_access_token
from app.models.user import User
from app.schemas.auth import (
    AuthCallback,
    AuthCallbackSimple,
    AuthRequest,
    AuthResponse,
    AuthURL,
    TokenRefresh,
    UserInfo,
)

router = APIRouter()


@router.post("/github", response_model=AuthURL)
async def github_auth(request: AuthRequest) -> AuthURL:
    """Initiate GitHub OAuth flow."""
    state = secrets.token_urlsafe(32)
    await store_oauth_state(state, request.redirect_uri)

    params = {
        "client_id": settings.github_client_id,
        "redirect_uri": request.redirect_uri,
        "scope": "user:email read:org repo",
        "state": state,
    }

    authorization_url = f"https://github.com/login/oauth/authorize?{urlencode(params)}"
    return AuthURL(authorization_url=authorization_url)


@router.post("/github/callback", response_model=AuthResponse)
async def github_callback(callback: AuthCallback, db: DbSession) -> AuthResponse:
    """Handle GitHub OAuth callback."""
    # Verify state from Redis
    redirect_uri = await get_oauth_state(callback.state)
    if redirect_uri is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired state parameter",
        )
    await delete_oauth_state(callback.state)

    # Exchange code for access token
    async with httpx.AsyncClient() as client:
        token_response = await client.post(
            "https://github.com/login/oauth/access_token",
            data={
                "client_id": settings.github_client_id,
                "client_secret": settings.github_client_secret,
                "code": callback.code,
            },
            headers={"Accept": "application/json"},
        )

        if token_response.status_code != 200:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to exchange code for token",
            )

        token_data = token_response.json()
        github_token = token_data.get("access_token")

        if not github_token:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No access token in response",
            )

        # Get user info from GitHub
        user_response = await client.get(
            "https://api.github.com/user",
            headers={
                "Authorization": f"Bearer {github_token}",
                "Accept": "application/json",
            },
        )

        if user_response.status_code != 200:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to get user info from GitHub",
            )

        github_user = user_response.json()

    # Find or create user
    result = await db.execute(
        select(User).where(User.github_id == github_user["id"])
    )
    user = result.scalar_one_or_none()

    if user is None:
        user = User(
            github_id=github_user["id"],
            username=github_user["login"],
            email=github_user.get("email"),
            avatar_url=github_user.get("avatar_url"),
            access_token_encrypted=encrypt_token(github_token),
        )
        db.add(user)
        await db.flush()
    else:
        # Update user info
        user.username = github_user["login"]
        user.email = github_user.get("email")
        user.avatar_url = github_user.get("avatar_url")
        user.access_token_encrypted = encrypt_token(github_token)

    # Create JWT tokens
    access_token = create_access_token(str(user.id))

    return AuthResponse(
        access_token=access_token,
        token_type="Bearer",
        expires_in=settings.jwt_access_token_expire_minutes * 60,
        user=UserInfo(
            id=user.id,
            username=user.username,
            email=user.email,
            avatar_url=user.avatar_url,
        ),
    )


@router.post("/github/exchange", response_model=AuthResponse)
async def github_exchange(callback: AuthCallbackSimple, db: DbSession) -> AuthResponse:
    """Exchange GitHub OAuth code for tokens (frontend-initiated flow).

    This endpoint is used when OAuth is initiated from the frontend.
    State verification is handled on the frontend side.
    """
    # Log request details
    logger.info("=== GitHub Exchange Request ===")
    logger.info(f"Callback code: {callback.code[:10] if callback.code else 'None'}...")
    logger.info(f"GitHub client_id from settings: '{settings.github_client_id}'")
    logger.info(f"GitHub client_secret length: {len(settings.github_client_secret)}")

    # Exchange code for access token
    async with httpx.AsyncClient() as client:
        token_response = await client.post(
            "https://github.com/login/oauth/access_token",
            data={
                "client_id": settings.github_client_id,
                "client_secret": settings.github_client_secret,
                "code": callback.code,
            },
            headers={"Accept": "application/json"},
        )

        logger.info(f"GitHub token response status: {token_response.status_code}")
        token_data = token_response.json()
        logger.info(f"GitHub token response: {token_data}")

        if token_response.status_code != 200:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to exchange code for token: {token_data}",
            )

        if "error" in token_data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=token_data.get("error_description", token_data["error"]),
            )

        github_token = token_data.get("access_token")

        if not github_token:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No access token in response",
            )

        # Get user info from GitHub
        user_response = await client.get(
            "https://api.github.com/user",
            headers={
                "Authorization": f"Bearer {github_token}",
                "Accept": "application/json",
            },
        )

        if user_response.status_code != 200:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to get user info from GitHub",
            )

        github_user = user_response.json()

    # Find or create user
    result = await db.execute(
        select(User).where(User.github_id == github_user["id"])
    )
    user = result.scalar_one_or_none()

    if user is None:
        user = User(
            github_id=github_user["id"],
            username=github_user["login"],
            email=github_user.get("email"),
            avatar_url=github_user.get("avatar_url"),
            access_token_encrypted=encrypt_token(github_token),
        )
        db.add(user)
        await db.flush()
    else:
        # Update user info
        user.username = github_user["login"]
        user.email = github_user.get("email")
        user.avatar_url = github_user.get("avatar_url")
        user.access_token_encrypted = encrypt_token(github_token)

    await db.commit()

    # Create JWT tokens
    access_token = create_access_token(str(user.id))

    return AuthResponse(
        access_token=access_token,
        token_type="Bearer",
        expires_in=settings.jwt_access_token_expire_minutes * 60,
        user=UserInfo(
            id=user.id,
            username=user.username,
            email=user.email,
            avatar_url=user.avatar_url,
        ),
    )


@router.post("/refresh", response_model=TokenRefresh)
async def refresh_token(db: DbSession) -> TokenRefresh:
    """Refresh access token using refresh token."""
    # Note: In a real implementation, you'd get the refresh token from the request
    # This is a simplified version
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Refresh token endpoint not yet implemented",
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout() -> None:
    """Logout user (invalidate token)."""
    # In a stateless JWT system, logout is typically handled client-side
    # For proper logout, implement token blacklisting with Redis
    pass
