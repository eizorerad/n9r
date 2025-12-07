"""Shared helper functions for worker tasks.

This module contains utility functions that are shared across multiple
Celery worker tasks, enabling code reuse and independent task execution.

**Feature: parallel-analysis-pipeline**
**Validates: Requirements 5.1, 5.2, 5.3**
"""

import logging
from pathlib import Path

from sqlalchemy import select

from app.core.database import get_sync_session

logger = logging.getLogger(__name__)


def get_repo_url(repository_id: str) -> tuple[str, str | None]:
    """Get repository URL and access token from database.
    
    This function retrieves the repository URL and the owner's decrypted
    access token for cloning private repositories.
    
    Args:
        repository_id: UUID of the repository (as string)
        
    Returns:
        Tuple of (repo_url, access_token) where access_token may be None
        for public repositories or if decryption fails.
        
    Raises:
        ValueError: If repository is not found
        
    **Feature: parallel-analysis-pipeline**
    **Validates: Requirements 5.1, 5.2, 5.3**
    """
    from app.core.encryption import decrypt_token
    from app.models.repository import Repository
    from app.models.user import User

    with get_sync_session() as db:
        result = db.execute(
            select(Repository).where(Repository.id == repository_id)
        )
        repo = result.scalar_one_or_none()

        if not repo:
            raise ValueError(f"Repository {repository_id} not found")

        # Get owner's access token for private repos
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


def collect_files_for_embedding(repo_path) -> list[dict]:
    """Collect code files from repository for embedding generation.
    
    Walks the repository directory and collects code files that are
    suitable for embedding generation, filtering by extension and size.
    
    Args:
        repo_path: Path to the cloned repository (str or Path)
        
    Returns:
        List of {path: str, content: str} dicts for each code file
        
    **Feature: parallel-analysis-pipeline**
    **Validates: Requirements 5.1**
    """
    if not repo_path:
        return []

    repo_path = Path(repo_path)
    files = []

    # Extensions to include for embedding
    code_extensions = {
        ".py", ".js", ".jsx", ".ts", ".tsx",
        ".java", ".go", ".rs", ".rb", ".php",
        ".c", ".cpp", ".h", ".hpp", ".cs",
        ".swift", ".kt", ".scala",
    }

    # Directories to skip
    skip_dirs = {
        "node_modules", "vendor", "__pycache__", ".git",
        "dist", "build", ".next", "coverage", ".venv", "venv",
    }

    # Max file size (100KB)
    max_file_size = 100 * 1024

    for root, dirs, filenames in repo_path.walk():
        # Skip excluded directories
        dirs[:] = [d for d in dirs if d not in skip_dirs and not d.startswith(".")]

        for filename in filenames:
            file_path = root / filename

            # Check extension
            if file_path.suffix.lower() not in code_extensions:
                continue

            # Check file size
            try:
                if file_path.stat().st_size > max_file_size:
                    continue
            except OSError:
                continue

            # Read content
            try:
                content = file_path.read_text(encoding="utf-8", errors="ignore")
                if len(content) < 50:  # Skip very small files
                    continue

                # Get relative path
                rel_path = str(file_path.relative_to(repo_path))

                files.append({
                    "path": rel_path,
                    "content": content,
                })
            except Exception as e:
                logger.debug(f"Could not read {file_path}: {e}")
                continue

    logger.info(f"Collected {len(files)} files for embedding")
    return files
