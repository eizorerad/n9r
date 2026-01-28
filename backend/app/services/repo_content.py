"""Repository content cache service.

This module provides a production-grade content cache for repository files
using PostgreSQL for metadata and MinIO for file storage.

The cache is commit-centric, meaning each cache entry is tied to a specific
commit SHA. This ensures consistency between chat responses and analysis results.

**Feature: repo-content-cache**
**Validates: Requirements 1.1, 1.2, 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 3.1, 3.2, 4.1, 4.2**
"""

from __future__ import annotations

import hashlib
import logging
import os
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError

from app.models.repo_content_cache import RepoContentCache
from app.models.repo_content_object import RepoContentObject
from app.models.repo_content_tree import RepoContentTree
from app.services.object_storage import (
    MinIOClient,
    ObjectStorageError,
    get_object_storage_client,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# Bucket name for repository content
REPO_CONTENT_BUCKET = "repo-content"


# =============================================================================
# Data Classes
# =============================================================================


@dataclass
class FileToUpload:
    """Represents a file to be uploaded to the content cache."""
    path: str           # Human-readable path (e.g., "src/main.py")
    content: bytes      # File content as bytes
    content_hash: str   # SHA-256 hash of content


@dataclass
class CacheStatus:
    """Status information for a content cache entry."""
    status: str         # 'pending', 'uploading', 'ready', 'failed'
    file_count: int
    total_size_bytes: int
    created_at: datetime


@dataclass
class UploadResult:
    """Result of a file upload operation."""
    uploaded: int       # New files uploaded
    skipped: int        # Files already existed (same hash)
    failed: int         # Files that failed to upload
    errors: list[str]   # Error messages


# =============================================================================
# File Collection Configuration
# =============================================================================

# Extensions to include for caching (same as embeddings)
CODE_EXTENSIONS = {
    ".py", ".js", ".jsx", ".ts", ".tsx",
    ".java", ".go", ".rs", ".rb", ".php",
    ".c", ".cpp", ".h", ".hpp", ".cs",
    ".swift", ".kt", ".scala",
}

# Directories to skip
SKIP_DIRS = {
    "node_modules", "vendor", "__pycache__", ".git",
    "dist", "build", ".next", "coverage", ".venv", "venv",
}

# Max file size (100KB) - same as embeddings
MAX_FILE_SIZE = 100 * 1024

# Minimum file size (50 bytes) - skip very small files
MIN_FILE_SIZE = 50


# =============================================================================
# Helper Functions
# =============================================================================


def compute_content_hash(content: bytes) -> str:
    """Compute SHA-256 hash of file content.

    Args:
        content: File content as bytes

    Returns:
        64-character hex string (SHA-256 hash)
    """
    return hashlib.sha256(content).hexdigest()


def generate_object_key(repository_id: uuid.UUID, commit_sha: str) -> str:
    """Generate a stable UUID-based object key for MinIO.

    Args:
        repository_id: Repository UUID
        commit_sha: Git commit SHA

    Returns:
        Object key in format: {repository_id}/{commit_sha}/{uuid}
    """
    object_id = uuid.uuid4()
    return f"{repository_id}/{commit_sha}/{object_id}"


# =============================================================================
# RepoContentService
# =============================================================================


class RepoContentService:
    """Production-grade repository content cache service.

    Provides methods for:
    - Cache management (get_or_create_cache, get_cache_status)
    - File collection (collect_files_from_repo)
    - File upload (upload_files)
    - File retrieval (get_tree, get_file, get_files_batch)
    - Lifecycle management (mark_cache_ready, mark_cache_failed, save_tree)

    **Feature: repo-content-cache**
    **Validates: Requirements 1.1, 1.2, 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 3.1, 3.2, 4.1, 4.2**
    """

    def __init__(self, storage_client: MinIOClient | None = None):
        """Initialize the service.

        Args:
            storage_client: Optional MinIO client (uses default if not provided)
        """
        self._storage = storage_client or get_object_storage_client()

    # =========================================================================
    # Cache Management
    # =========================================================================

    async def get_or_create_cache(
        self,
        db: AsyncSession,
        repository_id: uuid.UUID,
        commit_sha: str,
    ) -> RepoContentCache:
        """Get existing cache or create new one with 'pending' status.

        Uses PostgreSQL UNIQUE constraint to prevent duplicate entries
        when multiple processes attempt to create cache simultaneously.

        Args:
            db: Database session
            repository_id: Repository UUID
            commit_sha: Git commit SHA (40 characters)

        Returns:
            RepoContentCache instance (existing or newly created)

        **Feature: repo-content-cache**
        **Validates: Requirements 3.1**
        """
        # Try to get existing cache first
        result = await db.execute(
            select(RepoContentCache).where(
                RepoContentCache.repository_id == repository_id,
                RepoContentCache.commit_sha == commit_sha,
            )
        )
        cache = result.scalar_one_or_none()

        if cache:
            logger.debug(f"Found existing cache for {commit_sha[:7]}: {cache.status}")
            return cache

        # Create new cache entry
        cache = RepoContentCache(
            repository_id=repository_id,
            commit_sha=commit_sha,
            status="pending",
            file_count=0,
            total_size_bytes=0,
            version=1,
        )

        try:
            db.add(cache)
            await db.flush()
            logger.info(f"Created new cache for {commit_sha[:7]}")
            return cache
        except IntegrityError:
            # Another process created the cache - fetch it
            await db.rollback()
            result = await db.execute(
                select(RepoContentCache).where(
                    RepoContentCache.repository_id == repository_id,
                    RepoContentCache.commit_sha == commit_sha,
                )
            )
            cache = result.scalar_one_or_none()
            if cache:
                logger.debug(f"Cache created by another process for {commit_sha[:7]}")
                return cache
            raise

    async def get_cache_status(
        self,
        db: AsyncSession,
        repository_id: uuid.UUID,
        commit_sha: str,
    ) -> CacheStatus | None:
        """Get cache status without loading file data.

        Args:
            db: Database session
            repository_id: Repository UUID
            commit_sha: Git commit SHA

        Returns:
            CacheStatus if cache exists, None otherwise

        **Feature: repo-content-cache**
        **Validates: Requirements 4.2**
        """
        result = await db.execute(
            select(
                RepoContentCache.status,
                RepoContentCache.file_count,
                RepoContentCache.total_size_bytes,
                RepoContentCache.created_at,
            ).where(
                RepoContentCache.repository_id == repository_id,
                RepoContentCache.commit_sha == commit_sha,
            )
        )
        row = result.one_or_none()

        if not row:
            return None

        return CacheStatus(
            status=row.status,
            file_count=row.file_count,
            total_size_bytes=row.total_size_bytes,
            created_at=row.created_at,
        )


    # =========================================================================
    # File Collection
    # =========================================================================

    def collect_files_from_repo(
        self,
        repo_path: Path | str,
    ) -> list[FileToUpload]:
        """Collect files from cloned repository for caching.

        Applies the same filters as the embeddings system:
        - Code file extensions only
        - Max file size limit (100KB)
        - Min file size limit (50 bytes)
        - Skips excluded directories

        Args:
            repo_path: Path to the cloned repository

        Returns:
            List of FileToUpload objects with path, content, and hash

        **Feature: repo-content-cache**
        **Validates: Requirements 2.1, 2.2, 2.6**
        """
        if not repo_path:
            return []

        repo_path = Path(repo_path)
        if not repo_path.exists():
            logger.warning(f"Repository path does not exist: {repo_path}")
            return []

        files: list[FileToUpload] = []

        for root_str, dirs, filenames in os.walk(repo_path):
            root = Path(root_str)
            # Skip excluded directories (modify in-place to prevent descent)
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")]

            for filename in filenames:
                file_path = root / filename

                # Check extension
                if file_path.suffix.lower() not in CODE_EXTENSIONS:
                    continue

                # Check file size
                try:
                    file_size = file_path.stat().st_size
                    if file_size > MAX_FILE_SIZE:
                        logger.debug(f"Skipping large file: {file_path} ({file_size} bytes)")
                        continue
                    if file_size < MIN_FILE_SIZE:
                        logger.debug(f"Skipping small file: {file_path} ({file_size} bytes)")
                        continue
                except OSError as e:
                    logger.debug(f"Could not stat {file_path}: {e}")
                    continue

                # Read content
                try:
                    content = file_path.read_bytes()

                    # Double-check size after reading (in case of race)
                    if len(content) < MIN_FILE_SIZE:
                        continue

                    # Compute hash
                    content_hash = compute_content_hash(content)

                    # Get relative path
                    rel_path = str(file_path.relative_to(repo_path))

                    files.append(FileToUpload(
                        path=rel_path,
                        content=content,
                        content_hash=content_hash,
                    ))
                except Exception as e:
                    logger.debug(f"Could not read {file_path}: {e}")
                    continue

        logger.info(f"Collected {len(files)} files for caching")
        return files

    def collect_full_tree(
        self,
        repo_path: Path | str,
    ) -> list[dict]:
        """Collect complete directory tree from cloned repository.

        Unlike collect_files_from_repo which only collects code files,
        this method collects ALL files and directories for the file explorer.

        Args:
            repo_path: Path to the cloned repository

        Returns:
            List of file/directory entries with metadata:
            [{"name": "src", "path": "src", "type": "directory", "size": null}, ...]

        **Feature: commit-centric-explorer**
        """
        if not repo_path:
            return []

        repo_path = Path(repo_path)
        if not repo_path.exists():
            logger.warning(f"Repository path does not exist: {repo_path}")
            return []

        entries: list[dict] = []
        seen_dirs: set[str] = set()

        for root_str, dirs, filenames in os.walk(repo_path):
            root = Path(root_str)
            # Skip .git and other specific system directories
            # We want to show .github, .vscode, etc., so only exclude .git and noise
            dirs[:] = [d for d in dirs if d not in {".git", "__pycache__"}]

            rel_root = root.relative_to(repo_path)

            # Add directories
            for dirname in dirs:
                dir_path = rel_root / dirname if str(rel_root) != "." else Path(dirname)
                dir_path_str = str(dir_path)

                if dir_path_str not in seen_dirs:
                    seen_dirs.add(dir_path_str)
                    entries.append({
                        "name": dirname,
                        "path": dir_path_str,
                        "type": "directory",
                        "size": None,
                    })

            # Add files
            for filename in filenames:
                # Skip specific system files, but allow .gitignore, .env, .github/*
                if filename in {".DS_Store"}:
                    continue

                file_path = root / filename
                rel_file_path = file_path.relative_to(repo_path)

                try:
                    file_size = file_path.stat().st_size
                except OSError:
                    file_size = None

                entries.append({
                    "name": filename,
                    "path": str(rel_file_path),
                    "type": "file",
                    "size": file_size,
                })

        # Sort: directories first, then by path
        entries.sort(key=lambda x: (x["type"] != "directory", x["path"].lower()))

        logger.info(f"Collected full tree: {len(entries)} entries")
        return entries


    # =========================================================================
    # File Upload
    # =========================================================================

    async def upload_files(
        self,
        db: AsyncSession,
        cache: RepoContentCache,
        files: list[FileToUpload],
    ) -> UploadResult:
        """Upload files to MinIO and record in PostgreSQL.

        Idempotent: skips files that already exist with the same content hash.
        Updates cache status to 'uploading' during the operation.

        Args:
            db: Database session
            cache: RepoContentCache instance
            files: List of files to upload

        Returns:
            UploadResult with counts of uploaded, skipped, and failed files

        **Feature: repo-content-cache**
        **Validates: Requirements 2.3, 3.2**
        """
        if not files:
            return UploadResult(uploaded=0, skipped=0, failed=0, errors=[])

        # Update cache status to 'uploading'
        await db.execute(
            update(RepoContentCache)
            .where(RepoContentCache.id == cache.id)
            .values(status="uploading")
        )
        await db.flush()

        uploaded = 0
        skipped = 0
        failed = 0
        errors: list[str] = []

        # Get existing objects for this cache to check for duplicates
        result = await db.execute(
            select(RepoContentObject.path, RepoContentObject.content_hash)
            .where(RepoContentObject.cache_id == cache.id)
        )
        existing_objects = {row.path: row.content_hash for row in result.all()}

        for file in files:
            try:
                # Check if file already exists with same hash (idempotency)
                if file.path in existing_objects:
                    if existing_objects[file.path] == file.content_hash:
                        logger.debug(f"Skipping duplicate file: {file.path}")
                        skipped += 1
                        continue
                    else:
                        # File exists but hash changed - this shouldn't happen
                        # for immutable commits, but handle it gracefully
                        logger.warning(
                            f"File {file.path} exists with different hash, skipping"
                        )
                        skipped += 1
                        continue

                # Generate object key
                object_key = generate_object_key(cache.repository_id, cache.commit_sha)

                # Upload to MinIO
                await self._storage.put_object(
                    bucket=REPO_CONTENT_BUCKET,
                    key=object_key,
                    data=file.content,
                    content_type="application/octet-stream",
                )

                # Record in PostgreSQL
                obj = RepoContentObject(
                    cache_id=cache.id,
                    path=file.path,
                    object_key=object_key,
                    size_bytes=len(file.content),
                    content_hash=file.content_hash,
                    status="ready",
                )
                db.add(obj)

                uploaded += 1
                logger.debug(f"Uploaded file: {file.path}")

            except ObjectStorageError as e:
                failed += 1
                error_msg = f"Failed to upload {file.path}: {e}"
                errors.append(error_msg)
                logger.error(error_msg)

            except Exception as e:
                failed += 1
                error_msg = f"Unexpected error uploading {file.path}: {e}"
                errors.append(error_msg)
                logger.error(error_msg)

        # Flush to ensure all objects are persisted
        await db.flush()

        logger.info(
            f"Upload complete: {uploaded} uploaded, {skipped} skipped, {failed} failed"
        )

        return UploadResult(
            uploaded=uploaded,
            skipped=skipped,
            failed=failed,
            errors=errors,
        )


    # =========================================================================
    # Cache Lifecycle
    # =========================================================================

    async def mark_cache_ready(
        self,
        db: AsyncSession,
        cache_id: uuid.UUID,
    ) -> None:
        """Mark cache as ready after all files uploaded.

        Updates the cache status to 'ready' and computes final metadata
        (file_count, total_size_bytes) from the uploaded objects.

        Args:
            db: Database session
            cache_id: Cache UUID

        **Feature: repo-content-cache**
        **Validates: Requirements 2.4**
        """
        # Compute metadata from 'ready' objects
        from sqlalchemy import func

        result = await db.execute(
            select(
                func.count(RepoContentObject.id).label("file_count"),
                func.coalesce(func.sum(RepoContentObject.size_bytes), 0).label("total_size"),
            ).where(
                RepoContentObject.cache_id == cache_id,
                RepoContentObject.status == "ready",
            )
        )
        row = result.one()

        # Update cache with computed metadata
        await db.execute(
            update(RepoContentCache)
            .where(RepoContentCache.id == cache_id)
            .values(
                status="ready",
                file_count=row.file_count,
                total_size_bytes=row.total_size,
                version=RepoContentCache.version + 1,
            )
        )
        await db.flush()

        logger.info(
            f"Cache {cache_id} marked ready: {row.file_count} files, "
            f"{row.total_size} bytes"
        )

    async def mark_cache_failed(
        self,
        db: AsyncSession,
        cache_id: uuid.UUID,
        error: str,
    ) -> None:
        """Mark cache as failed with error message.

        Args:
            db: Database session
            cache_id: Cache UUID
            error: Error message describing the failure

        **Feature: repo-content-cache**
        **Validates: Requirements 2.5**
        """
        await db.execute(
            update(RepoContentCache)
            .where(RepoContentCache.id == cache_id)
            .values(
                status="failed",
                version=RepoContentCache.version + 1,
            )
        )
        await db.flush()

        logger.error(f"Cache {cache_id} marked failed: {error}")

    async def save_tree(
        self,
        db: AsyncSession,
        cache_id: uuid.UUID,
        tree: list[str],
        full_tree: list[dict] | None = None,
    ) -> None:
        """Save tree structure for fast directory listings.

        Uses PostgreSQL upsert to handle concurrent saves.

        Args:
            db: Database session
            cache_id: Cache UUID
            tree: List of code file paths (e.g., ["src/main.py", "src/utils.py"])
            full_tree: Complete directory tree with metadata for file explorer

        **Feature: repo-content-cache**
        **Validates: Requirements 1.1**
        """
        # Use upsert to handle concurrent saves
        values = {"cache_id": cache_id, "tree": tree}
        update_values = {"tree": tree}

        if full_tree is not None:
            values["full_tree"] = full_tree
            update_values["full_tree"] = full_tree

        stmt = pg_insert(RepoContentTree).values(**values)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_repo_content_tree_cache",
            set_=update_values,
        )

        await db.execute(stmt)
        await db.flush()

        full_tree_len = len(full_tree) if full_tree else 0
        logger.debug(f"Saved tree for cache {cache_id}: {len(tree)} code files, {full_tree_len} full tree entries")

    # =========================================================================
    # File Retrieval
    # =========================================================================

    async def get_tree(
        self,
        db: AsyncSession,
        repository_id: uuid.UUID,
        commit_sha: str,
    ) -> list[str] | None:
        """Get cached tree structure for a repository commit.

        Returns the list of file paths from the cache if the cache is ready.
        Returns None if cache doesn't exist or is not ready.

        Args:
            db: Database session
            repository_id: Repository UUID
            commit_sha: Git commit SHA

        Returns:
            List of file paths if cache is ready, None otherwise

        **Feature: repo-content-cache**
        **Validates: Requirements 1.1, 6.3**
        """
        # First check if cache exists and is ready
        result = await db.execute(
            select(RepoContentCache.id, RepoContentCache.status)
            .where(
                RepoContentCache.repository_id == repository_id,
                RepoContentCache.commit_sha == commit_sha,
            )
        )
        cache_row = result.one_or_none()

        if not cache_row:
            logger.debug(f"No cache found for {commit_sha[:7]}")
            return None

        # Return None if cache is not ready (pending, uploading, or failed)
        if cache_row.status != "ready":
            logger.debug(f"Cache not ready for {commit_sha[:7]}: {cache_row.status}")
            return None

        # Fetch tree from repo_content_tree
        result = await db.execute(
            select(RepoContentTree.tree)
            .where(RepoContentTree.cache_id == cache_row.id)
        )
        tree_row = result.scalar_one_or_none()

        if tree_row is None:
            logger.warning(f"Cache ready but no tree found for {commit_sha[:7]}")
            return None

        logger.debug(f"Retrieved tree for {commit_sha[:7]}: {len(tree_row)} entries")
        return tree_row

    async def has_full_tree(
        self,
        db: AsyncSession,
        cache_id: uuid.UUID,
    ) -> bool:
        """Check if cache has full_tree populated.

        Args:
            db: Database session
            cache_id: Cache UUID

        Returns:
            True if full_tree is not null, False otherwise
        """
        result = await db.execute(
            select(RepoContentTree.full_tree)
            .where(RepoContentTree.cache_id == cache_id)
        )
        row = result.one_or_none()
        return row is not None and row.full_tree is not None

    async def get_full_tree(
        self,
        db: AsyncSession,
        repository_id: uuid.UUID,
        commit_sha: str,
        path: str = "",
    ) -> list[dict] | None:
        """Get full directory tree for file explorer.

        Returns the complete directory structure with metadata for the
        commit-centric file explorer. Optionally filters by path prefix.

        Args:
            db: Database session
            repository_id: Repository UUID
            commit_sha: Git commit SHA
            path: Optional path prefix to filter (e.g., "src" for src/ contents)

        Returns:
            List of file/directory entries if cache is ready, None otherwise

        **Feature: commit-centric-explorer**
        """
        # First check if cache exists and is ready
        result = await db.execute(
            select(RepoContentCache.id, RepoContentCache.status)
            .where(
                RepoContentCache.repository_id == repository_id,
                RepoContentCache.commit_sha == commit_sha,
            )
        )
        cache_row = result.one_or_none()

        if not cache_row:
            logger.debug(f"No cache found for {commit_sha[:7]}")
            return None

        # Return None if cache is not ready
        if cache_row.status != "ready":
            logger.debug(f"Cache not ready for {commit_sha[:7]}: {cache_row.status}")
            return None

        # Fetch full_tree from repo_content_tree
        result = await db.execute(
            select(RepoContentTree.full_tree)
            .where(RepoContentTree.cache_id == cache_row.id)
        )
        full_tree = result.scalar_one_or_none()

        if full_tree is None:
            logger.debug(f"No full_tree found for {commit_sha[:7]}")
            return None

        # Filter by path if specified
        if path:
            # Normalize path (remove trailing slash)
            path = path.rstrip("/")

            # Filter entries that are direct children of the path
            filtered = []
            for entry in full_tree:
                entry_path = entry["path"]

                # Check if entry is a direct child of the requested path
                if "/" in entry_path:
                    parent = entry_path.rsplit("/", 1)[0]
                else:
                    parent = ""

                if parent == path:
                    filtered.append(entry)

            logger.debug(f"Retrieved full_tree for {commit_sha[:7]} path={path}: {len(filtered)} entries")
            return filtered
        else:
            # Return root level entries only
            root_entries = [
                entry for entry in full_tree
                if "/" not in entry["path"]
            ]
            logger.debug(f"Retrieved full_tree for {commit_sha[:7]} (root): {len(root_entries)} entries")
            return root_entries

    async def get_file(
        self,
        db: AsyncSession,
        repository_id: uuid.UUID,
        commit_sha: str,
        file_path: str,
    ) -> str | None:
        """Get file content from cache.

        Retrieves file content from MinIO and verifies the content hash
        matches the stored hash for integrity.

        Args:
            db: Database session
            repository_id: Repository UUID
            commit_sha: Git commit SHA
            file_path: Path to the file (e.g., "src/main.py")

        Returns:
            File content as string if found and valid, None otherwise

        **Feature: repo-content-cache**
        **Validates: Requirements 1.2, 1.4**
        """
        # First check if cache exists and is ready
        result = await db.execute(
            select(RepoContentCache.id, RepoContentCache.status)
            .where(
                RepoContentCache.repository_id == repository_id,
                RepoContentCache.commit_sha == commit_sha,
            )
        )
        cache_row = result.one_or_none()

        if not cache_row:
            logger.debug(f"No cache found for {commit_sha[:7]}")
            return None

        # Return None if cache is not ready
        if cache_row.status != "ready":
            logger.debug(f"Cache not ready for {commit_sha[:7]}: {cache_row.status}")
            return None

        # Find the file object
        result = await db.execute(
            select(
                RepoContentObject.object_key,
                RepoContentObject.content_hash,
                RepoContentObject.status,
            )
            .where(
                RepoContentObject.cache_id == cache_row.id,
                RepoContentObject.path == file_path,
            )
        )
        obj_row = result.one_or_none()

        if not obj_row:
            logger.debug(f"File not found in cache: {file_path}")
            return None

        # Check object status
        if obj_row.status != "ready":
            logger.debug(f"File object not ready: {file_path} ({obj_row.status})")
            return None

        # Fetch content from MinIO
        try:
            content_bytes = await self._storage.get_object(
                bucket=REPO_CONTENT_BUCKET,
                key=obj_row.object_key,
            )

            if content_bytes is None:
                logger.warning(f"File not found in MinIO: {file_path}")
                return None

            # Verify content hash for integrity
            actual_hash = compute_content_hash(content_bytes)
            if actual_hash != obj_row.content_hash:
                logger.error(
                    f"Content hash mismatch for {file_path}: "
                    f"expected {obj_row.content_hash}, got {actual_hash}"
                )
                return None

            # Decode content as UTF-8 (code files are text)
            try:
                content = content_bytes.decode("utf-8")
            except UnicodeDecodeError:
                # Try with latin-1 as fallback
                content = content_bytes.decode("latin-1")

            logger.debug(f"Retrieved file from cache: {file_path}")
            return content

        except ObjectStorageError as e:
            logger.error(f"Failed to retrieve file from MinIO: {file_path}: {e}")
            return None

    async def get_files_batch(
        self,
        db: AsyncSession,
        repository_id: uuid.UUID,
        commit_sha: str,
        file_paths: list[str],
    ) -> dict[str, str]:
        """Get multiple files from cache in batch (parallel MinIO requests).

        Retrieves multiple files in parallel for better performance.
        Files that are not found or fail validation are omitted from the result.

        Args:
            db: Database session
            repository_id: Repository UUID
            commit_sha: Git commit SHA
            file_paths: List of file paths to retrieve

        Returns:
            Dict mapping file paths to their content (only successful retrievals)

        **Feature: repo-content-cache**
        **Validates: Requirements 1.2**
        """
        import asyncio

        if not file_paths:
            return {}

        # First check if cache exists and is ready
        result = await db.execute(
            select(RepoContentCache.id, RepoContentCache.status)
            .where(
                RepoContentCache.repository_id == repository_id,
                RepoContentCache.commit_sha == commit_sha,
            )
        )
        cache_row = result.one_or_none()

        if not cache_row:
            logger.debug(f"No cache found for {commit_sha[:7]}")
            return {}

        # Return empty if cache is not ready
        if cache_row.status != "ready":
            logger.debug(f"Cache not ready for {commit_sha[:7]}: {cache_row.status}")
            return {}

        # Find all requested file objects
        result = await db.execute(
            select(
                RepoContentObject.path,
                RepoContentObject.object_key,
                RepoContentObject.content_hash,
                RepoContentObject.status,
            )
            .where(
                RepoContentObject.cache_id == cache_row.id,
                RepoContentObject.path.in_(file_paths),
                RepoContentObject.status == "ready",
            )
        )
        objects = {row.path: row for row in result.all()}

        if not objects:
            logger.debug("No files found in cache for batch request")
            return {}

        async def fetch_single_file(path: str, obj) -> tuple[str, str | None]:
            """Fetch a single file from MinIO and verify hash."""
            try:
                content_bytes = await self._storage.get_object(
                    bucket=REPO_CONTENT_BUCKET,
                    key=obj.object_key,
                )

                if content_bytes is None:
                    logger.warning(f"File not found in MinIO: {path}")
                    return path, None

                # Verify content hash
                actual_hash = compute_content_hash(content_bytes)
                if actual_hash != obj.content_hash:
                    logger.error(
                        f"Content hash mismatch for {path}: "
                        f"expected {obj.content_hash}, got {actual_hash}"
                    )
                    return path, None

                # Decode content
                try:
                    content = content_bytes.decode("utf-8")
                except UnicodeDecodeError:
                    content = content_bytes.decode("latin-1")

                return path, content

            except ObjectStorageError as e:
                logger.error(f"Failed to retrieve file from MinIO: {path}: {e}")
                return path, None

        # Fetch all files in parallel
        tasks = [
            fetch_single_file(path, obj)
            for path, obj in objects.items()
        ]
        results = await asyncio.gather(*tasks)

        # Build result dict (only successful retrievals)
        file_contents = {
            path: content
            for path, content in results
            if content is not None
        }

        logger.debug(
            f"Retrieved {len(file_contents)}/{len(file_paths)} files from cache"
        )
        return file_contents
