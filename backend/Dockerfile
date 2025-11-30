# n9r Backend Dockerfile
#
# Multi-stage build for Python FastAPI backend with Celery workers.
# Includes git for repository cloning and Docker CLI for sandbox operations.

# =============================================================================
# Stage 1: Builder
# =============================================================================
FROM python:3.11-slim as builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv for fast Python package management
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.cargo/bin:$PATH"

# Copy dependency files
COPY pyproject.toml uv.lock* ./

# Install dependencies
RUN uv sync --frozen --no-dev

# =============================================================================
# Stage 2: Runtime
# =============================================================================
FROM python:3.11-slim as runtime

WORKDIR /app

# Install runtime dependencies
# - git: Required for cloning repositories (RepoAnalyzer, Sandbox)
# - curl: Health checks
# - docker-cli: Required for Celery workers to spawn sandbox containers
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    ca-certificates \
    gnupg \
    && rm -rf /var/lib/apt/lists/*

# Install Docker CLI (for sandbox container management)
# This allows Celery workers to spawn sibling containers for healing validation
RUN install -m 0755 -d /etc/apt/keyrings \
    && curl -fsSL https://download.docker.com/linux/debian/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg \
    && chmod a+r /etc/apt/keyrings/docker.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/debian $(. /etc/os-release && echo "$VERSION_CODENAME") stable" > /etc/apt/sources.list.d/docker.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends docker-ce-cli \
    && rm -rf /var/lib/apt/lists/*

# Copy virtual environment from builder
COPY --from=builder /app/.venv /app/.venv

# Set up environment
ENV VIRTUAL_ENV=/app/.venv
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Create non-root user for API server
# Note: Celery worker may need root for Docker socket access
RUN useradd -m -s /bin/bash n9r

# Create directories
RUN mkdir -p /app/sandbox_data && chown -R n9r:n9r /app

# Copy application code
COPY --chown=n9r:n9r . .

# Switch to non-root user (API server)
# For Celery with Docker, use `user: root` in docker-compose
USER n9r

# Health check endpoint
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Default command (FastAPI server)
# Override in docker-compose for Celery workers
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]

# Expose port
EXPOSE 8000
