"""Application configuration settings."""

import logging
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, PostgresDsn, RedisDsn, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


def _find_env_file() -> str | None:
    """Find .env file in common locations.
    
    Checks (in order):
    1. ../.env (running from backend/ directory - local dev)
    2. .env (running from project root or Docker)
    3. None (rely on environment variables - production)
    """
    candidates = [
        Path("../.env"),      # Local dev: running from backend/
        Path(".env"),         # Docker or project root
        Path("/app/.env"),    # Docker alternative
    ]
    for path in candidates:
        if path.exists():
            return str(path)
    return None  # No .env file found, use env vars only


# Insecure default that should never be used in production
_INSECURE_SECRET_KEY = "change-me-in-production"


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=_find_env_file(),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_env: Literal["development", "staging", "production"] = "development"
    debug: bool = True
    secret_key: str = Field(default=_INSECURE_SECRET_KEY)
    api_v1_prefix: str = "/v1"

    # Database
    database_url: PostgresDsn = Field(
        default="postgresql://n9r:n9r_dev_password@localhost:5432/n9r"
    )

    # Redis
    redis_url: RedisDsn = Field(default="redis://localhost:6379/0")
    redis_host: str = "localhost"
    redis_port: int = 6379

    # Qdrant
    qdrant_host: str = "localhost"
    qdrant_port: int = 6333
    qdrant_collection_name: str = "code_embeddings"

    # MinIO
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_bucket: str = "n9r-dev"
    minio_secure: bool = False

    # GitHub App
    github_app_id: str = ""
    github_client_id: str = ""
    github_client_secret: str = ""
    github_private_key_path: str = "./github-app.pem"
    github_webhook_secret: str = ""

    # LLM Gateway (via LiteLLM)
    # OpenAI
    openai_api_key: str = ""

    # Anthropic
    anthropic_api_key: str = ""

    # Google (Gemini / Vertex AI)
    gemini_api_key: str = ""
    vertex_project: str = ""
    vertex_location: str = "us-central1"
    vertex_embedding_model: str = ""

    # Azure OpenAI
    azure_api_key: str = ""
    azure_api_base: str = ""
    azure_api_version: str = "2024-02-15-preview"
    azure_embedding_deployment: str = ""
    azure_chat_deployment: str = ""

    # AWS Bedrock
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    aws_region_name: str = "us-east-1"
    bedrock_embedding_model: str = ""

    # OpenRouter
    openrouter_api_key: str = ""

    # Default settings
    default_llm_provider: str = "openai"
    default_llm_model: str = "gpt-4o"
    embedding_model: str = ""  # Auto-detected if empty

    # Celery
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"

    # JWT Settings
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 60 * 24  # 24 hours
    jwt_refresh_token_expire_days: int = 7

    # CORS
    cors_origins: list[str] = ["http://localhost:3000"]

    # Sandbox Settings (for Docker deployment)
    # When running Celery inside Docker, these paths must be configured correctly:
    # - sandbox_root_dir: Base directory for sandbox workdirs (inside Celery container)
    # - host_sandbox_path: Corresponding path on Docker host (for volume mounting)
    # For local development, leave host_sandbox_path empty to use sandbox_root_dir directly.
    sandbox_root_dir: str = "/tmp"  # Override via SANDBOX_ROOT_DIR
    host_sandbox_path: str = ""  # Override via HOST_SANDBOX_PATH (empty = local dev mode)

    @model_validator(mode="after")
    def validate_security_settings(self) -> "Settings":
        """Validate critical security settings based on environment.
        
        In production:
        - secret_key MUST be set to a secure value
        - GitHub OAuth credentials MUST be set
        
        In development:
        - Warnings are logged for missing credentials
        - Insecure defaults are allowed but logged
        """
        warnings: list[str] = []
        errors: list[str] = []

        # Check secret_key
        if self.secret_key == _INSECURE_SECRET_KEY:
            if self.app_env == "production":
                errors.append(
                    "SECRET_KEY must be set to a secure value in production. "
                    "Generate one with: python -c \"import secrets; print(secrets.token_urlsafe(32))\""
                )
            else:
                warnings.append(
                    "Using insecure default SECRET_KEY. Set SECRET_KEY env var for security."
                )

        # Check GitHub OAuth (required for auth to work)
        if not self.github_client_id or not self.github_client_secret:
            if self.app_env == "production":
                errors.append(
                    "GITHUB_CLIENT_ID and GITHUB_CLIENT_SECRET must be set for OAuth."
                )
            else:
                warnings.append(
                    "GitHub OAuth credentials not set. Login will fail. "
                    "Set GITHUB_CLIENT_ID and GITHUB_CLIENT_SECRET."
                )

        # Check LLM keys (at least one should be set for analysis features)
        has_llm_key = any([
            self.openai_api_key,
            self.anthropic_api_key,
            self.gemini_api_key,
            self.azure_api_key,
            self.openrouter_api_key,
        ])
        if not has_llm_key:
            msg = (
                "No LLM API keys configured. AI features (analysis, healing, chat) "
                "will not work. Set at least one of: OPENAI_API_KEY, ANTHROPIC_API_KEY, "
                "GEMINI_API_KEY, AZURE_API_KEY, OPENROUTER_API_KEY."
            )
            if self.app_env == "production":
                errors.append(msg)
            else:
                warnings.append(msg)

        # Log warnings
        for warning in warnings:
            logger.warning(f"⚠️  CONFIG WARNING: {warning}")

        # Raise errors in production
        if errors:
            error_msg = "Configuration errors:\n" + "\n".join(f"  - {e}" for e in errors)
            raise ValueError(error_msg)

        return self

    @property
    def database_url_async(self) -> str:
        """Get async database URL."""
        return str(self.database_url).replace(
            "postgresql://", "postgresql+asyncpg://"
        )


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


settings = get_settings()
