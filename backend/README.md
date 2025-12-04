# n9r Backend

AI Code Detox & Auto-Healing Platform - Backend API

## Quick Start

```bash
# Install uv if not installed
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install dependencies
uv sync

# Start infrastructure
docker compose up -d

# Initialize database and services
uv run python scripts/init_all.py

# Run server
uv run uvicorn main:app --reload --port 8000
```

## Development

```bash
# Run with dev dependencies
uv sync --dev

# Run tests
uv run pytest

# Run linters
uv run ruff check .
uv run mypy .

# Start Celery worker (all queues including ai_scan)
uv run celery -A app.core.celery worker -Q default,analysis,embeddings,healing,notifications,ai_scan --loglevel=info

# Start Celery beat scheduler
uv run celery -A app.core.celery beat --loglevel=info

```
## API Documentation

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## Production Deployment (Docker)

For production deployment with all services containerized:

### Prerequisites

1. Build the backend Docker image:
```bash
docker build -t n9r-backend ./backend
```

2. Create sandbox data directory:
```bash
mkdir -p ./sandbox_data
```

3. Configure environment variables in `.env`:
```bash
# Set absolute path to sandbox_data directory
HOST_SANDBOX_PATH=$(pwd)/sandbox_data
```

### Start Production Stack

```bash
# Start infrastructure + backend services
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

### Services Started

| Service | Description | Port |
|---------|-------------|------|
| `backend` | FastAPI API server | 8000 |
| `celery-worker` | Celery worker (all queues) | - |
| `celery-beat` | Celery scheduler | - |
| `postgres` | PostgreSQL database | 5432 |
| `redis` | Redis cache/broker | 6379 |
| `qdrant` | Vector database | 6333 |
| `minio` | Object storage | 9000 |

### Sandbox & Docker-in-Docker

The healing pipeline requires spawning sandbox containers for code validation.
When Celery runs in Docker, this requires:

1. **Docker socket mount** - `/var/run/docker.sock` is mounted into the worker
2. **Shared volume** - `sandbox_data` directory is shared between host and container
3. **Path translation** - `HOST_SANDBOX_PATH` maps container paths to host paths

See `docs/sandbox_security_research.md` for security implications.

## Project Structure

```
backend/
├── app/
│   ├── api/v1/       # API endpoints
│   ├── core/         # Configuration, security, database
│   ├── models/       # SQLAlchemy models
│   ├── schemas/      # Pydantic schemas
│   ├── services/     # Business logic
│   └── workers/      # Celery tasks
├── alembic/          # Database migrations
├── scripts/          # Utility scripts
└── tests/            # Test files
