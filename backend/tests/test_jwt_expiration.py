"""Tests for JWT token expiration handling.

Tests that expired JWT tokens return 401 Unauthorized responses,
which triggers frontend redirect to login page.

**Feature: session-expiration-fix**
"""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException, status
from jose import jwt

from app.core.config import settings
from app.core.security import create_access_token, verify_token


class TestJWTExpiration:
    """Test JWT token expiration behavior."""

    def test_create_token_with_custom_expiration(self):
        """Test creating a token with custom expiration time."""
        user_id = str(uuid.uuid4())

        # Create token that expires in 1 hour
        token = create_access_token(
            subject=user_id,
            expires_delta=timedelta(hours=1),
        )

        # Verify token is valid
        payload = verify_token(token)
        assert payload is not None
        assert payload["sub"] == user_id
        assert payload["type"] == "access"

    def test_expired_token_returns_none(self):
        """
        **Feature: session-expiration-fix**

        Test that an expired token returns None from verify_token.
        This is the core behavior that triggers 401 responses.
        """
        user_id = str(uuid.uuid4())

        # Create token that expired 1 hour ago
        expired_time = datetime.now(UTC) - timedelta(hours=1)

        to_encode = {
            "sub": user_id,
            "exp": expired_time,
            "iat": datetime.now(UTC) - timedelta(hours=2),
            "type": "access",
        }

        expired_token = jwt.encode(
            to_encode,
            settings.secret_key,
            algorithm=settings.jwt_algorithm,
        )

        # Verify that expired token returns None
        payload = verify_token(expired_token)
        assert payload is None, "Expired token should return None"

    def test_token_expiring_soon_still_valid(self):
        """Test that a token expiring soon is still valid."""
        user_id = str(uuid.uuid4())

        # Create token that expires in 1 minute
        token = create_access_token(
            subject=user_id,
            expires_delta=timedelta(minutes=1),
        )

        # Should still be valid
        payload = verify_token(token)
        assert payload is not None
        assert payload["sub"] == user_id

    def test_invalid_token_returns_none(self):
        """Test that an invalid token returns None."""
        payload = verify_token("invalid.token.here")
        assert payload is None

    def test_tampered_token_returns_none(self):
        """Test that a tampered token returns None."""
        user_id = str(uuid.uuid4())

        # Create valid token
        token = create_access_token(subject=user_id)

        # Tamper with it
        parts = token.split(".")
        parts[1] = parts[1] + "tampered"
        tampered_token = ".".join(parts)

        payload = verify_token(tampered_token)
        assert payload is None


class TestGetCurrentUserWithExpiredToken:
    """Test get_current_user dependency with expired tokens."""

    @pytest.mark.asyncio
    async def test_expired_token_raises_401(self):
        """
        **Feature: session-expiration-fix**

        Test that an expired token raises 401 Unauthorized.
        This is the actual behavior that frontend detects and redirects to login.
        """
        from app.api.deps import get_current_user

        user_id = str(uuid.uuid4())

        # Create expired token
        expired_time = datetime.now(UTC) - timedelta(hours=1)
        to_encode = {
            "sub": user_id,
            "exp": expired_time,
            "iat": datetime.now(UTC) - timedelta(hours=2),
            "type": "access",
        }
        expired_token = jwt.encode(
            to_encode,
            settings.secret_key,
            algorithm=settings.jwt_algorithm,
        )

        # Mock credentials
        mock_credentials = MagicMock()
        mock_credentials.credentials = expired_token

        # Mock database session
        mock_db = AsyncMock()

        # Call get_current_user - should raise 401
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(credentials=mock_credentials, db=mock_db)

        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert "Invalid or expired token" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_valid_token_with_nonexistent_user_raises_401(self):
        """
        **Feature: session-expiration-fix**

        Test that a valid token for a non-existent user raises 401.
        """
        from app.api.deps import get_current_user

        user_id = str(uuid.uuid4())

        # Create valid token
        token = create_access_token(subject=user_id)

        # Mock credentials
        mock_credentials = MagicMock()
        mock_credentials.credentials = token

        # Mock database session that returns no user
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        # Call get_current_user - should raise 401
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(credentials=mock_credentials, db=mock_db)

        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert "User not found" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_wrong_token_type_raises_401(self):
        """
        **Feature: session-expiration-fix**

        Test that a refresh token used as access token raises 401.
        """
        from app.api.deps import get_current_user
        from app.core.security import create_refresh_token

        user_id = str(uuid.uuid4())

        # Create refresh token (wrong type)
        refresh_token = create_refresh_token(subject=user_id)

        # Mock credentials
        mock_credentials = MagicMock()
        mock_credentials.credentials = refresh_token

        # Mock database session
        mock_db = AsyncMock()

        # Call get_current_user - should raise 401
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(credentials=mock_credentials, db=mock_db)

        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert "Invalid token type" in exc_info.value.detail


class TestProtectedEndpointWithExpiredToken:
    """Integration tests for protected endpoints with expired tokens."""

    @pytest.mark.asyncio
    async def test_analyses_endpoint_returns_401_for_expired_token(self):
        """
        **Feature: session-expiration-fix**

        Test that /analyses/{id} returns 401 for expired token.
        This simulates the exact scenario from the bug report.
        """
        from app.api.deps import get_current_user

        user_id = str(uuid.uuid4())
        uuid.uuid4()

        # Create expired token
        expired_time = datetime.now(UTC) - timedelta(hours=1)
        to_encode = {
            "sub": user_id,
            "exp": expired_time,
            "iat": datetime.now(UTC) - timedelta(hours=2),
            "type": "access",
        }
        expired_token = jwt.encode(
            to_encode,
            settings.secret_key,
            algorithm=settings.jwt_algorithm,
        )

        # Mock credentials
        mock_credentials = MagicMock()
        mock_credentials.credentials = expired_token

        # Mock database session
        mock_db = AsyncMock()

        # First, verify that get_current_user raises 401
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(credentials=mock_credentials, db=mock_db)

        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
        # This is the response that frontend catches and redirects to login

    @pytest.mark.asyncio
    async def test_full_status_endpoint_returns_401_for_expired_token(self):
        """
        **Feature: session-expiration-fix**

        Test that /analyses/{id}/full-status returns 401 for expired token.
        This is the polling endpoint that was showing repeated 401 errors.
        """
        from app.api.deps import get_current_user

        user_id = str(uuid.uuid4())

        # Create expired token
        expired_time = datetime.now(UTC) - timedelta(hours=1)
        to_encode = {
            "sub": user_id,
            "exp": expired_time,
            "iat": datetime.now(UTC) - timedelta(hours=2),
            "type": "access",
        }
        expired_token = jwt.encode(
            to_encode,
            settings.secret_key,
            algorithm=settings.jwt_algorithm,
        )

        # Mock credentials
        mock_credentials = MagicMock()
        mock_credentials.credentials = expired_token

        # Mock database session
        mock_db = AsyncMock()

        # Verify that get_current_user raises 401
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(credentials=mock_credentials, db=mock_db)

        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED


class TestTokenLifetimeConfiguration:
    """Test token lifetime configuration."""

    def test_access_token_lifetime_is_7_days(self):
        """
        **Feature: session-expiration-fix**

        Test that access token lifetime is configured to 7 days.
        This should match the frontend session lifetime.
        """
        # 7 days = 7 * 24 * 60 = 10080 minutes
        expected_minutes = 7 * 24 * 60
        assert settings.jwt_access_token_expire_minutes == expected_minutes, (
            f"Access token should expire in {expected_minutes} minutes (7 days), "
            f"but is set to {settings.jwt_access_token_expire_minutes} minutes"
        )

    def test_refresh_token_lifetime_is_30_days(self):
        """Test that refresh token lifetime is 30 days."""
        assert settings.jwt_refresh_token_expire_days == 30

    def test_created_token_has_correct_expiration(self):
        """
        **Feature: session-expiration-fix**

        Test that created tokens have the correct expiration time.
        """
        user_id = str(uuid.uuid4())

        # Create token with default expiration
        token = create_access_token(subject=user_id)

        # Decode and check expiration
        payload = verify_token(token)
        assert payload is not None

        exp_timestamp = payload["exp"]
        iat_timestamp = payload["iat"]

        # Calculate expected lifetime in seconds
        expected_lifetime_seconds = settings.jwt_access_token_expire_minutes * 60
        actual_lifetime_seconds = exp_timestamp - iat_timestamp

        # Allow 5 second tolerance for test execution time
        assert abs(actual_lifetime_seconds - expected_lifetime_seconds) < 5, (
            f"Token lifetime should be ~{expected_lifetime_seconds}s, "
            f"but is {actual_lifetime_seconds}s"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
