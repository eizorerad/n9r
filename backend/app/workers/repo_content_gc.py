"""Repository content cache garbage collection worker.

This module handles cleanup of orphaned, failed, and old cache entries
for the repository content cache system.

**Feature: repo-content-cache**
**Validates: Requirements 4.4, 5.1, 5.2, 5.3**
"""

import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.celery import celery_app
from app.core.database import get_sync_session
from app.models.repo_content_cache import RepoContentCache
from app.models.repo_content_object import RepoContentObject
from app.services.object_storage import (
    MinIOClient,
    ObjectStorageError,
    get_object_storage_client,
)
from app.services.repo_content import REPO_CONTENT_BUCKET

logger = logging.getLogger(__name__)


# =============================================================================
# Configuration
# =============================================================================

# Default threshold for cleaning up failed/stuck caches (24 hours)
FAILED_CACHE_THRESHOLD_HOURS = 24

# Default number of recent commits to keep per repository
MAX_CACHED_COMMITS_PER_REPO = 5


# =============================================================================
# Helper Functions
# =============================================================================


def _get_minio_objects_for_cache(
    db: Session,
    cache_id: UUID,
) -> list[str]:
    """Get all MinIO object keys for a cache entry.
    
    Args:
        db: Database session
        cache_id: Cache UUID
        
    Returns:
        List of MinIO object keys
    """
    result = db.execute(
        select(RepoContentObject.object_key)
        .where(RepoContentObject.cache_id == cache_id)
    )
    return [row[0] for row in result.fetchall()]


def _delete_minio_objects(
    storage: MinIOClient,
    object_keys: list[str],
) -> tuple[int, list[str]]:
    """Delete objects from MinIO.
    
    Args:
        storage: MinIO client
        object_keys: List of object keys to delete
        
    Returns:
        Tuple of (deleted_count, errors)
    """
    import asyncio
    
    deleted = 0
    errors: list[str] = []
    
    async def delete_objects():
        nonlocal deleted, errors
        for key in object_keys:
            try:
                await storage.delete_object(
                    bucket=REPO_CONTENT_BUCKET,
                    key=key,
                )
                deleted += 1
            except ObjectStorageError as e:
                error_msg = f"Failed to delete {key}: {e}"
                errors.append(error_msg)
                logger.warning(error_msg)
            except Exception as e:
                error_msg = f"Unexpected error deleting {key}: {e}"
                errors.append(error_msg)
                logger.error(error_msg)
    
    # Run async deletion
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    loop.run_until_complete(delete_objects())
    
    return deleted, errors


# =============================================================================
# Cleanup Functions
# =============================================================================


def cleanup_failed_caches(
    db: Session,
    storage: MinIOClient,
    threshold_hours: int = FAILED_CACHE_THRESHOLD_HOURS,
) -> dict:
    """Clean up caches stuck in 'uploading' or 'failed' status.
    
    Deletes cache entries that have been in 'uploading' or 'failed' status
    for longer than the threshold, along with their MinIO objects.
    
    Args:
        db: Database session
        storage: MinIO client
        threshold_hours: Hours after which to clean up failed caches
        
    Returns:
        Dict with cleanup statistics
        
    **Feature: repo-content-cache**
    **Validates: Requirements 5.1**
    """
    threshold = datetime.now(UTC) - timedelta(hours=threshold_hours)
    
    # Find stuck/failed caches
    result = db.execute(
        select(RepoContentCache)
        .where(
            RepoContentCache.status.in_(["uploading", "failed"]),
            RepoContentCache.created_at < threshold,
        )
    )
    stuck_caches = result.scalars().all()
    
    if not stuck_caches:
        logger.debug("No stuck/failed caches to clean up")
        return {
            "caches_deleted": 0,
            "objects_deleted": 0,
            "errors": [],
        }
    
    total_objects_deleted = 0
    all_errors: list[str] = []
    cache_ids_to_delete: list[UUID] = []
    
    for cache in stuck_caches:
        logger.info(
            f"Cleaning up stuck cache {cache.id} "
            f"(status={cache.status}, created={cache.created_at})"
        )
        
        # Get MinIO object keys for this cache
        object_keys = _get_minio_objects_for_cache(db, cache.id)
        
        # Delete from MinIO
        if object_keys:
            deleted, errors = _delete_minio_objects(storage, object_keys)
            total_objects_deleted += deleted
            all_errors.extend(errors)
        
        cache_ids_to_delete.append(cache.id)
    
    # Delete cache entries from PostgreSQL (CASCADE will delete objects)
    if cache_ids_to_delete:
        db.execute(
            delete(RepoContentCache)
            .where(RepoContentCache.id.in_(cache_ids_to_delete))
        )
        db.commit()
    
    logger.info(
        f"Cleaned up {len(cache_ids_to_delete)} stuck caches, "
        f"{total_objects_deleted} MinIO objects"
    )
    
    return {
        "caches_deleted": len(cache_ids_to_delete),
        "objects_deleted": total_objects_deleted,
        "errors": all_errors,
    }


def cleanup_old_commits(
    db: Session,
    storage: MinIOClient,
    keep_count: int = MAX_CACHED_COMMITS_PER_REPO,
) -> dict:
    """Clean up old cached commits, keeping only the most recent N per repository.
    
    For each repository, keeps only the `keep_count` most recent cached commits
    and deletes older ones along with their MinIO objects.
    
    Args:
        db: Database session
        storage: MinIO client
        keep_count: Number of recent commits to keep per repository
        
    Returns:
        Dict with cleanup statistics
        
    **Feature: repo-content-cache**
    **Validates: Requirements 5.2**
    """
    from app.models.repository import Repository
    
    # Get all repositories with cached content
    result = db.execute(
        select(RepoContentCache.repository_id)
        .distinct()
    )
    repo_ids = [row[0] for row in result.fetchall()]
    
    if not repo_ids:
        logger.debug("No repositories with cached content")
        return {
            "repos_processed": 0,
            "caches_deleted": 0,
            "objects_deleted": 0,
            "errors": [],
        }
    
    total_caches_deleted = 0
    total_objects_deleted = 0
    all_errors: list[str] = []
    
    for repo_id in repo_ids:
        # Get all caches for this repository, ordered by created_at desc
        result = db.execute(
            select(RepoContentCache)
            .where(RepoContentCache.repository_id == repo_id)
            .order_by(RepoContentCache.created_at.desc())
        )
        caches = result.scalars().all()
        
        # Skip if we have fewer than keep_count caches
        if len(caches) <= keep_count:
            continue
        
        # Caches to delete (all except the most recent keep_count)
        caches_to_delete = caches[keep_count:]
        
        logger.info(
            f"Repository {repo_id}: keeping {keep_count} caches, "
            f"deleting {len(caches_to_delete)} old caches"
        )
        
        cache_ids_to_delete: list[UUID] = []
        
        for cache in caches_to_delete:
            # Get MinIO object keys for this cache
            object_keys = _get_minio_objects_for_cache(db, cache.id)
            
            # Delete from MinIO
            if object_keys:
                deleted, errors = _delete_minio_objects(storage, object_keys)
                total_objects_deleted += deleted
                all_errors.extend(errors)
            
            cache_ids_to_delete.append(cache.id)
        
        # Delete cache entries from PostgreSQL
        if cache_ids_to_delete:
            db.execute(
                delete(RepoContentCache)
                .where(RepoContentCache.id.in_(cache_ids_to_delete))
            )
            total_caches_deleted += len(cache_ids_to_delete)
    
    db.commit()
    
    logger.info(
        f"Cleaned up {total_caches_deleted} old caches across {len(repo_ids)} repos, "
        f"{total_objects_deleted} MinIO objects"
    )
    
    return {
        "repos_processed": len(repo_ids),
        "caches_deleted": total_caches_deleted,
        "objects_deleted": total_objects_deleted,
        "errors": all_errors,
    }


def cleanup_deleted_repos(
    db: Session,
    storage: MinIOClient,
) -> dict:
    """Clean up MinIO objects for deleted repositories.
    
    PostgreSQL CASCADE handles metadata deletion when a repository is deleted,
    but MinIO objects need to be cleaned up separately. This function finds
    orphaned MinIO objects (objects whose cache entries no longer exist) and
    deletes them.
    
    Args:
        db: Database session
        storage: MinIO client
        
    Returns:
        Dict with cleanup statistics
        
    **Feature: repo-content-cache**
    **Validates: Requirements 4.4, 5.3**
    """
    import asyncio
    
    # Get all object keys tracked in PostgreSQL
    result = db.execute(
        select(RepoContentObject.object_key)
    )
    tracked_object_keys = {row[0] for row in result.fetchall()}
    
    logger.info(f"Found {len(tracked_object_keys)} tracked objects in PostgreSQL")
    
    # List all objects in MinIO bucket
    async def list_minio_objects():
        try:
            return await storage.list_objects(
                bucket=REPO_CONTENT_BUCKET,
                prefix="",
            )
        except ObjectStorageError as e:
            logger.warning(f"Could not list MinIO objects: {e}")
            return []
    
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    minio_object_keys = set(loop.run_until_complete(list_minio_objects()))
    
    logger.info(f"Found {len(minio_object_keys)} objects in MinIO bucket")
    
    # Find orphaned objects (in MinIO but not in PostgreSQL)
    orphaned_keys = minio_object_keys - tracked_object_keys
    
    if not orphaned_keys:
        logger.debug("No orphaned MinIO objects found")
        return {
            "tracked_objects": len(tracked_object_keys),
            "minio_objects": len(minio_object_keys),
            "orphaned_objects_deleted": 0,
            "errors": [],
        }
    
    logger.info(f"Found {len(orphaned_keys)} orphaned MinIO objects to delete")
    
    # Delete orphaned objects
    deleted, errors = _delete_minio_objects(storage, list(orphaned_keys))
    
    logger.info(f"Deleted {deleted} orphaned MinIO objects")
    
    return {
        "tracked_objects": len(tracked_object_keys),
        "minio_objects": len(minio_object_keys),
        "orphaned_objects_deleted": deleted,
        "errors": errors,
    }


# =============================================================================
# Celery Tasks
# =============================================================================


@celery_app.task(
    bind=True,
    name="app.workers.repo_content_gc.cleanup_repo_content_cache",
)
def cleanup_repo_content_cache(self) -> dict:
    """
    Main garbage collection task for repository content cache.
    
    This task:
    1. Cleans up caches stuck in 'uploading' or 'failed' status (24h threshold)
    2. Cleans up old commits (keeps 5 most recent per repository)
    3. Cleans up orphaned MinIO objects from deleted repositories
    
    Runs periodically via Celery Beat (every 6 hours).
    
    Returns:
        Dict with cleanup statistics
        
    **Feature: repo-content-cache**
    **Validates: Requirements 4.4, 5.1, 5.2, 5.3**
    """
    logger.info("Starting repository content cache garbage collection")
    
    results = {
        "timestamp": datetime.now(UTC).isoformat(),
        "failed_caches": {},
        "old_commits": {},
        "deleted_repos": {},
        "status": "completed",
    }
    
    try:
        storage = get_object_storage_client()
        
        with get_sync_session() as db:
            # Step 1: Clean up failed/stuck caches
            logger.info("Step 1: Cleaning up failed/stuck caches")
            results["failed_caches"] = cleanup_failed_caches(db, storage)
            
            # Step 2: Clean up old commits
            logger.info("Step 2: Cleaning up old commits")
            results["old_commits"] = cleanup_old_commits(db, storage)
            
            # Step 3: Clean up orphaned objects from deleted repos
            logger.info("Step 3: Cleaning up orphaned objects")
            results["deleted_repos"] = cleanup_deleted_repos(db, storage)
        
        # Compute totals
        total_caches = (
            results["failed_caches"].get("caches_deleted", 0) +
            results["old_commits"].get("caches_deleted", 0)
        )
        total_objects = (
            results["failed_caches"].get("objects_deleted", 0) +
            results["old_commits"].get("objects_deleted", 0) +
            results["deleted_repos"].get("orphaned_objects_deleted", 0)
        )
        
        results["total_caches_deleted"] = total_caches
        results["total_objects_deleted"] = total_objects
        
        logger.info(
            f"Repository content cache GC completed: "
            f"{total_caches} caches, {total_objects} objects deleted"
        )
        
    except Exception as e:
        logger.error(f"Repository content cache GC failed: {e}")
        results["status"] = "failed"
        results["error"] = str(e)
        raise
    
    return results
