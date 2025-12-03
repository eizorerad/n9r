"""Token encryption/decryption utilities for secrets management."""

import base64

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from app.core.config import settings


def _get_key() -> bytes:
    """Derive encryption key from SECRET_KEY."""
    # Use PBKDF2 to derive a proper Fernet key from the secret
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=b"n9r_token_salt_v1",  # Static salt for consistent derivation
        iterations=100000,
    )
    key = base64.urlsafe_b64encode(kdf.derive(settings.secret_key.encode()))
    return key


def encrypt_token(token: str) -> str:
    """Encrypt a token (e.g., GitHub access token).
    
    Args:
        token: The plaintext token to encrypt.
        
    Returns:
        Base64-encoded encrypted token.
    """
    if not token:
        return ""

    key = _get_key()
    f = Fernet(key)
    encrypted = f.encrypt(token.encode())
    return base64.urlsafe_b64encode(encrypted).decode()


def decrypt_token(encrypted_token: str) -> str:
    """Decrypt an encrypted token.
    
    Args:
        encrypted_token: Base64-encoded encrypted token.
        
    Returns:
        The decrypted plaintext token.
        
    Raises:
        InvalidToken: If the token cannot be decrypted.
    """
    if not encrypted_token:
        return ""

    key = _get_key()
    f = Fernet(key)
    encrypted = base64.urlsafe_b64decode(encrypted_token.encode())
    decrypted = f.decrypt(encrypted)
    return decrypted.decode()


def encrypt_token_or_none(token: str | None) -> str | None:
    """Encrypt a token if it exists, otherwise return None."""
    if token is None:
        return None
    return encrypt_token(token)


def decrypt_token_or_none(encrypted_token: str | None) -> str | None:
    """Decrypt a token if it exists, otherwise return None."""
    if encrypted_token is None:
        return None
    try:
        return decrypt_token(encrypted_token)
    except Exception:
        # If decryption fails, return None instead of raising
        return None
