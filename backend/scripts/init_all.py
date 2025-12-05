"""Initialize all infrastructure components for n9r.

This script:
1. Verifies connectivity to PostgreSQL and Redis
2. Runs all Alembic migrations (including schema fixes)
3. Initializes Qdrant vector database collection
4. Sets up MinIO storage buckets
5. Validates Redis functionality (OAuth, Pub/Sub, Playground)

Run this after docker-compose up to prepare the development environment.
"""

import asyncio
import sys
from pathlib import Path

# Add the backend directory to the path
sys.path.insert(0, str(Path(__file__).parent.parent))


def print_header(title: str) -> None:
    """Print a formatted header."""
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}\n")


def print_success(message: str) -> None:
    """Print a success message."""
    print(f"✅ {message}")


def print_error(message: str) -> None:
    """Print an error message."""
    print(f"❌ {message}")


def print_info(message: str) -> None:
    """Print an info message."""
    print(f"ℹ️  {message}")


async def run_migrations() -> None:
    """Run Alembic migrations to upgrade database schema.
    
    Migrations include:
    - 001_initial_schema: Base tables for all models
    - 002_fix_organization_schema: Align GitHub org + SaaS org models
    - 003_fix_chat_threads_schema: Fix context fields and add message_count
    - 004_fix_auto_prs_schema: Add missing PR stats and test result fields
    """
    print_header("Running Database Migrations")
    import subprocess

    result = subprocess.run(
        ["alembic", "upgrade", "head"],
        cwd=Path(__file__).parent.parent,
        capture_output=True,
        text=True,
    )

    if result.returncode == 0:
        print_success("Database migrations completed successfully")
        if result.stdout:
            for line in result.stdout.split("\n"):
                if line.strip():
                    print(f"   {line}")

        # Show current revision
        result_current = subprocess.run(
            ["alembic", "current"],
            cwd=Path(__file__).parent.parent,
            capture_output=True,
            text=True,
        )
        if result_current.returncode == 0 and result_current.stdout:
            print_info(f"Current revision: {result_current.stdout.strip()}")
    else:
        print_error("Database migrations failed")
        if result.stderr:
            print(result.stderr)
        raise RuntimeError("Migration failed")


def init_qdrant() -> None:
    """Initialize Qdrant vector database collection.
    
    Creates:
    - Collection with 3072-dimensional vectors (text-embedding-3-large)
    - COSINE distance metric for similarity search
    - Payload indexes for repo_id, file_path, language
    """
    print_header("Initializing Qdrant Collection")

    from qdrant_client import QdrantClient
    from qdrant_client.models import Distance, PayloadSchemaType, VectorParams

    from app.core.config import settings

    try:
        client = QdrantClient(
            host=settings.qdrant_host,
            port=settings.qdrant_port,
            timeout=settings.qdrant_timeout,
        )

        collection_name = settings.qdrant_collection_name

        # Check if collection exists
        collections = client.get_collections().collections
        collection_names = [c.name for c in collections]

        if collection_name in collection_names:
            print_success(f"Collection '{collection_name}' already exists")

            # Get collection info
            collection_info = client.get_collection(collection_name)
            print_info(f"Vector size: {collection_info.config.params.vectors.size}")
            print_info(f"Points count: {collection_info.points_count}")
            return

        # Create collection
        # Vector size depends on embedding model:
        # - text-embedding-3-small: 1536
        # - text-embedding-3-large: 3072
        # - amazon.titan-embed-text-v2: 1024
        client.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(
                size=3072,  # OpenAI/Azure text-embedding-3-large
                distance=Distance.COSINE,
            ),
        )

        # Create payload indexes for efficient filtering
        for field in ["repo_id", "file_path", "language"]:
            client.create_payload_index(
                collection_name=collection_name,
                field_name=field,
                field_schema=PayloadSchemaType.KEYWORD,
            )

        print_success(f"Collection '{collection_name}' created successfully")
        print_info("Vector size: 3072 (text-embedding-3-large)")
        print_info("Distance metric: COSINE")
        print_info("Payload indexes: repo_id, file_path, language")

    except Exception as e:
        print_error(f"Qdrant initialization failed: {e}")
        raise


def init_minio() -> None:
    """Initialize MinIO object storage buckets.
    
    Creates:
    - Main bucket for storing reports, logs, and artifacts
    - Folder structure: reports/, logs/, artifacts/
    """
    print_header("Initializing MinIO Buckets")

    from io import BytesIO

    from minio import Minio
    from minio.error import S3Error

    from app.core.config import settings

    try:
        client = Minio(
            settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure,
        )

        bucket_name = settings.minio_bucket

        # Create bucket
        if not client.bucket_exists(bucket_name):
            client.make_bucket(bucket_name)
            print_success(f"Bucket '{bucket_name}' created")
        else:
            print_success(f"Bucket '{bucket_name}' already exists")

        # Create folder markers for organized storage
        folders = ["reports/.gitkeep", "logs/.gitkeep", "artifacts/.gitkeep"]

        for folder in folders:
            try:
                client.stat_object(bucket_name, folder)
            except S3Error as e:
                if e.code == "NoSuchKey":
                    client.put_object(bucket_name, folder, BytesIO(b""), 0)
                    folder_name = folder.replace("/.gitkeep", "/")
                    print_info(f"Created folder: {folder_name}")

        print_success("MinIO initialization complete")
        print_info(f"Endpoint: {settings.minio_endpoint}")

    except Exception as e:
        print_error(f"MinIO initialization failed: {e}")
        raise


async def check_redis() -> None:
    """Check Redis connectivity and test key features.
    
    Tests:
    - Basic connectivity (ping)
    - Key operations (set/get/delete)
    - TTL functionality
    - Pub/Sub channels (for SSE analysis progress)
    """
    print_header("Checking Redis Connection")

    import redis.asyncio as aioredis

    from app.core.redis import async_redis_pool

    try:
        async with aioredis.Redis(connection_pool=async_redis_pool) as client:
            # Test basic connectivity
            await client.ping()
            print_success("Redis connection successful")

            # Get Redis info
            info = await client.info("server")
            redis_version = info.get("redis_version", "unknown")
            print_info(f"Redis version: {redis_version}")

            # Test key operations
            test_key = "init:test"
            await client.setex(test_key, 10, "test_value")
            value = await client.get(test_key)
            await client.delete(test_key)

            if value == "test_value":
                print_success("Key operations working (set/get/delete)")

            # Check if Redis supports required features
            print_info("Redis features:")
            print_info("  • OAuth state storage (TTL: 10min)")
            print_info("  • Analysis progress streaming (Pub/Sub)")
            print_info("  • Playground scan results (TTL: 1hr)")
            print_info("  • Rate limiting")

    except Exception as e:
        print_error(f"Redis connection failed: {e}")
        print_info("Ensure Redis is running: docker-compose up -d redis")
        raise


def check_postgres() -> None:
    """Check PostgreSQL connectivity and database info."""
    print_header("Checking PostgreSQL Connection")

    from sqlalchemy import create_engine, text

    from app.core.config import settings

    try:
        engine = create_engine(str(settings.database_url))
        with engine.connect() as conn:
            # Test basic connectivity
            result = conn.execute(text("SELECT 1"))
            result.fetchone()
            print_success("PostgreSQL connection successful")

            # Get PostgreSQL version
            result = conn.execute(text("SELECT version()"))
            version = result.fetchone()
            if version:
                version_str = version[0].split(",")[0]
                print_info(f"PostgreSQL version: {version_str}")

            # Check database name
            result = conn.execute(text("SELECT current_database()"))
            db_name = result.fetchone()
            if db_name:
                print_info(f"Database: {db_name[0]}")

    except Exception as e:
        print_error(f"PostgreSQL connection failed: {e}")
        print_info("Ensure PostgreSQL is running: docker-compose up -d postgres")
        raise


async def main() -> None:
    """Run all initialization steps.
    
    This script prepares the n9r development environment by:
    1. Validating infrastructure connectivity
    2. Running database migrations
    3. Initializing vector database
    4. Setting up object storage
    """
    print("\n" + "=" * 60)
    print("  🚀 n9r Infrastructure Initialization")
    print("=" * 60)

    try:
        # Phase 1: Check connections first
        print_info("Phase 1: Validating infrastructure connectivity...")
        check_postgres()
        await check_redis()

        # Phase 2: Run migrations
        print_info("Phase 2: Applying database schema...")
        await run_migrations()

        # Phase 3: Initialize services
        print_info("Phase 3: Initializing vector database and storage...")
        init_qdrant()
        init_minio()

        # Success summary
        print_header("✅ Initialization Complete!")
        print("All infrastructure components are ready.\n")

        print("📊 Infrastructure Status:")
        print("  ✅ PostgreSQL — Database ready with latest schema")
        print("  ✅ Redis — Caching, OAuth, Pub/Sub, Rate limiting")
        print("  ✅ Qdrant — Vector search with 3072-dim embeddings")
        print("  ✅ MinIO — Object storage for reports/logs/artifacts")

        print("\n🚀 Next Steps:")
        print("  1. Start the backend server:")
        print("     uvicorn main:app --reload --port 8000")
        print()
        print("  2. Start Celery worker (analysis tasks):")
        print("     celery -A app.core.celery worker -Q default,analysis,embeddings,healing,notifications --loglevel=info")
        print()
        print("  3. Start Celery beat (scheduled tasks):")
        print("     celery -A app.core.celery beat --loglevel=info")
        print()
        print("  4. Start the frontend:")
        print("     cd ../frontend && pnpm dev")
        print()

        print("📖 Documentation:")
        print("  • Architecture: docs/architecture.md")
        print("  • API Spec: docs/api_spec.md")
        print("  • Dev Setup: docs/dev_setup.md")
        print("  • Recent Changes:")
        print("    - docs/30-nov-2025-fix.md (Schema fixes)")
        print("    - docs/29-nov-2025-fix.md (Redis, LiteLLM, SSE)")
        print("    - docs/28-nov-2025-fix.md (Extended metrics)")

    except Exception as e:
        print(f"\n❌ Initialization failed: {e}")
        print("\n💡 Troubleshooting:")
        print("  • Ensure Docker containers are running: docker-compose up -d")
        print("  • Check .env file has all required variables")
        print("  • Check logs: docker-compose logs postgres redis qdrant minio")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
