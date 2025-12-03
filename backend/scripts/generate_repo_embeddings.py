#!/usr/bin/env python3
"""
Script to manually generate embeddings for a repository.

Usage:
    uv run python scripts/generate_repo_embeddings.py <repository_id>
    
This will:
1. Fetch the repository from the database
2. Clone it
3. Collect code files
4. Generate embeddings and store in Qdrant
"""

import logging
import subprocess
import sys
import tempfile
from pathlib import Path
from uuid import UUID

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select

from app.core.database import get_sync_session
from app.core.encryption import decrypt_token
from app.models.repository import Repository
from app.models.user import User


def get_repo_info(repository_id: str) -> tuple[str, str | None]:
    """Get repository URL and access token."""
    with get_sync_session() as db:
        result = db.execute(
            select(Repository).where(Repository.id == repository_id)
        )
        repo = result.scalar_one_or_none()

        if not repo:
            raise ValueError(f"Repository {repository_id} not found")

        # Get owner's access token
        access_token = None
        if repo.owner_id:
            user_result = db.execute(
                select(User).where(User.id == repo.owner_id)
            )
            user = user_result.scalar_one_or_none()
            if user and user.access_token_encrypted:
                try:
                    access_token = decrypt_token(user.access_token_encrypted)
                except Exception as e:
                    logger.warning(f"Could not decrypt access token: {e}")

        repo_url = f"https://github.com/{repo.full_name}"
        return repo_url, access_token


def clone_repo(repo_url: str, access_token: str | None, dest_dir: Path) -> bool:
    """Clone repository to destination directory."""
    if access_token:
        # Insert token into URL for private repos
        auth_url = repo_url.replace("https://", f"https://x-access-token:{access_token}@")
    else:
        auth_url = repo_url

    try:
        subprocess.run(
            ["git", "clone", "--depth", "1", auth_url, str(dest_dir)],
            check=True,
            capture_output=True,
            timeout=120,
        )
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"Git clone failed: {e.stderr.decode()}")
        return False


def collect_files(repo_path: Path) -> list[dict]:
    """Collect code files from repository."""
    files = []

    code_extensions = {
        ".py", ".js", ".jsx", ".ts", ".tsx",
        ".java", ".go", ".rs", ".rb", ".php",
        ".c", ".cpp", ".h", ".hpp", ".cs",
        ".swift", ".kt", ".scala",
    }

    skip_dirs = {
        "node_modules", "vendor", "__pycache__", ".git",
        "dist", "build", ".next", "coverage", ".venv", "venv",
    }

    max_file_size = 100 * 1024  # 100KB

    for root, dirs, filenames in repo_path.walk():
        dirs[:] = [d for d in dirs if d not in skip_dirs and not d.startswith(".")]

        for filename in filenames:
            file_path = root / filename

            if file_path.suffix.lower() not in code_extensions:
                continue

            try:
                if file_path.stat().st_size > max_file_size:
                    continue
            except OSError:
                continue

            try:
                content = file_path.read_text(encoding="utf-8", errors="ignore")
                if len(content) < 50:
                    continue

                rel_path = str(file_path.relative_to(repo_path))
                files.append({"path": rel_path, "content": content})
            except Exception as e:
                logger.debug(f"Could not read {file_path}: {e}")

    return files


def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/generate_repo_embeddings.py <repository_id>")
        sys.exit(1)

    repository_id = sys.argv[1]

    # Validate UUID
    try:
        UUID(repository_id)
    except ValueError:
        print(f"Invalid repository ID: {repository_id}")
        sys.exit(1)

    logger.info(f"Generating embeddings for repository {repository_id}")

    # Get repo info
    try:
        repo_url, access_token = get_repo_info(repository_id)
        logger.info(f"Repository URL: {repo_url}")
    except Exception as e:
        logger.error(f"Failed to get repository info: {e}")
        sys.exit(1)

    # Clone to temp directory
    with tempfile.TemporaryDirectory(prefix="n9r_embed_") as temp_dir:
        temp_path = Path(temp_dir)

        logger.info(f"Cloning repository to {temp_path}")
        if not clone_repo(repo_url, access_token, temp_path):
            sys.exit(1)

        logger.info("Repository cloned successfully")

        # Collect files
        files = collect_files(temp_path)
        logger.info(f"Collected {len(files)} code files")

        if not files:
            logger.warning("No code files found!")
            sys.exit(1)

        # Generate embeddings directly (without Celery)
        logger.info("Generating embeddings...")

        import asyncio

        from qdrant_client import QdrantClient
        from qdrant_client.models import PointStruct

        from app.core.config import settings
        from app.services.code_chunker import get_code_chunker
        from app.services.llm_gateway import get_llm_gateway

        def run_async(coro):
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            return loop.run_until_complete(coro)

        chunker = get_code_chunker()
        llm = get_llm_gateway()
        qdrant = QdrantClient(host=settings.qdrant_host, port=settings.qdrant_port)

        COLLECTION_NAME = "code_embeddings"

        # Chunk all files
        all_chunks = []
        for file_info in files:
            file_path = file_info.get("path", "")
            content = file_info.get("content", "")

            if not content or len(content) < 10:
                continue

            try:
                chunks = chunker.chunk_file(file_path, content)
                all_chunks.extend(chunks)
            except Exception as e:
                logger.warning(f"Failed to chunk {file_path}: {e}")

        logger.info(f"Created {len(all_chunks)} chunks from {len(files)} files")

        if not all_chunks:
            logger.warning("No chunks created!")
            sys.exit(1)

        # Generate embeddings in batches
        batch_size = 20
        points = []

        for i in range(0, len(all_chunks), batch_size):
            batch = all_chunks[i:i + batch_size]

            texts = []
            for chunk in batch:
                text = f"File: {chunk.file_path}\n"
                if chunk.name:
                    text += f"Name: {chunk.name}\n"
                if chunk.chunk_type:
                    text += f"Type: {chunk.chunk_type}\n"
                if chunk.docstring:
                    text += f"Description: {chunk.docstring}\n"
                text += f"\n{chunk.content}"
                texts.append(text)

            try:
                embeddings = run_async(llm.embed(texts))
            except Exception as e:
                logger.error(f"Failed to generate embeddings: {e}")
                continue

            for chunk, embedding in zip(batch, embeddings):
                point_id = f"{repository_id}_{chunk.file_path}_{chunk.line_start}".replace("/", "_").replace(".", "_")

                points.append(PointStruct(
                    id=hash(point_id) % (2**63),
                    vector=embedding,
                    payload={
                        "repository_id": repository_id,
                        "commit_sha": None,
                        "file_path": chunk.file_path,
                        "language": chunk.language,
                        "chunk_type": chunk.chunk_type,
                        "name": chunk.name,
                        "line_start": chunk.line_start,
                        "line_end": chunk.line_end,
                        "parent_name": chunk.parent_name,
                        "docstring": chunk.docstring,
                        "content": chunk.content[:2000],
                        "token_estimate": chunk.token_estimate,
                        "level": chunk.level,
                        "qualified_name": chunk.qualified_name,
                        "cyclomatic_complexity": chunk.cyclomatic_complexity,
                        "line_count": chunk.line_count,
                        "cluster_id": None,
                    }
                ))

            logger.info(f"Processed batch {i//batch_size + 1}/{(len(all_chunks) + batch_size - 1)//batch_size}")

        logger.info(f"Generated {len(points)} embedding vectors")

        # Store in Qdrant
        if points:
            # Delete old embeddings first
            try:
                qdrant.delete(
                    collection_name=COLLECTION_NAME,
                    points_selector={
                        "filter": {
                            "must": [
                                {"key": "repository_id", "match": {"value": repository_id}}
                            ]
                        }
                    }
                )
            except Exception as e:
                logger.warning(f"Failed to delete old embeddings: {e}")

            # Upsert new points
            upsert_batch_size = 100
            for i in range(0, len(points), upsert_batch_size):
                batch = points[i:i + upsert_batch_size]
                qdrant.upsert(collection_name=COLLECTION_NAME, points=batch)

            logger.info(f"✅ Successfully stored {len(points)} vectors in Qdrant!")
        else:
            logger.error("❌ No vectors generated!")


if __name__ == "__main__":
    main()
