"""Scheduled tasks for periodic operations."""

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.core.celery import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="app.workers.scheduled.cleanup_stuck_analyses")
def cleanup_stuck_analyses() -> dict:
    """
    Clean up stuck analyses using heartbeat-based detection.

    This task runs every 10 minutes via Celery Beat and marks stuck analyses as failed.

    Stuck detection policy (same as trigger_analysis):
    - For `pending` status: stuck if `created_at` is older than
      `settings.analysis_pending_stuck_minutes` (default 30 min)
    - For `running` status: stuck if `state_updated_at` is older than
      `settings.analysis_running_heartbeat_timeout_minutes` (default 15 min)

    Pinned analyses are never cleaned up.

    Returns:
        dict with cleanup statistics including reasons for each cleanup.

    **Feature: heartbeat-stuck-detection**
    **Validates: Section 6.2 and 6.9 of analysis-status-contract.md**
    """
    from app.api.v1.analyses import get_stuck_reason, is_analysis_stuck
    from app.core.config import settings
    from app.core.database import get_sync_session
    from app.models.analysis import Analysis

    logger.info(
        f"Starting stuck analyses cleanup (pending_timeout={settings.analysis_pending_stuck_minutes}min, "
        f"heartbeat_timeout={settings.analysis_running_heartbeat_timeout_minutes}min)"
    )

    cleaned_ids: list[str] = []
    pending_timeout_count = 0
    heartbeat_timeout_count = 0
    skipped_pinned_count = 0

    try:
        with get_sync_session() as db:
            # Query all non-terminal, non-pinned analyses
            result = db.execute(
                select(Analysis).where(
                    Analysis.status.in_(["pending", "running"]),
                    Analysis.pinned.is_(False),  # Skip pinned analyses
                )
            )
            analyses = result.scalars().all()

            now = datetime.now(UTC)

            for analysis in analyses:
                # Use the same stuck detection logic as trigger_analysis
                if not is_analysis_stuck(analysis):
                    continue

                stuck_reason = get_stuck_reason(analysis)
                if not stuck_reason:
                    continue  # Shouldn't happen, but be safe

                # Get repository info for logging
                repo_info = f"repo_id={analysis.repository_id}"

                # Set error message based on reason (same as trigger_analysis)
                if stuck_reason == "pending_timeout":
                    error_message = "Analysis timed out waiting for worker (pending-stuck)"
                    pending_timeout_count += 1
                    logger.warning(
                        f"Marking analysis {analysis.id} as failed: pending_timeout "
                        f"({repo_info}, status={analysis.status}, "
                        f"created_at={analysis.created_at.isoformat() if analysis.created_at else 'N/A'})"
                    )
                else:  # heartbeat_timeout
                    error_message = "Analysis timed out (no heartbeat - running-stuck)"
                    heartbeat_timeout_count += 1
                    logger.warning(
                        f"Marking analysis {analysis.id} as failed: heartbeat_timeout "
                        f"({repo_info}, status={analysis.status}, "
                        f"state_updated_at={analysis.state_updated_at.isoformat() if analysis.state_updated_at else 'N/A'})"
                    )

                # Update analysis status
                analysis.status = "failed"
                analysis.error_message = error_message
                analysis.completed_at = now
                analysis.state_updated_at = now

                cleaned_ids.append(str(analysis.id))

            # Also count pinned analyses that would have been cleaned
            pinned_result = db.execute(
                select(Analysis).where(
                    Analysis.status.in_(["pending", "running"]),
                    Analysis.pinned.is_(True),
                )
            )
            pinned_analyses = pinned_result.scalars().all()
            for analysis in pinned_analyses:
                if is_analysis_stuck(analysis):
                    skipped_pinned_count += 1
                    logger.info(
                        f"Skipping pinned stuck analysis {analysis.id} "
                        f"(repo_id={analysis.repository_id}, status={analysis.status})"
                    )

            db.commit()

            if cleaned_ids:
                logger.warning(
                    f"Cleaned up {len(cleaned_ids)} stuck analyses: "
                    f"pending_timeout={pending_timeout_count}, heartbeat_timeout={heartbeat_timeout_count}"
                )
            else:
                logger.debug("No stuck analyses found")

            if skipped_pinned_count > 0:
                logger.info(f"Skipped {skipped_pinned_count} pinned stuck analyses")

    except Exception as e:
        logger.error(f"Failed to cleanup stuck analyses: {e}")
        raise

    return {
        "status": "completed",
        "cleaned_count": len(cleaned_ids),
        "cleaned_ids": cleaned_ids,
        "pending_timeout_count": pending_timeout_count,
        "heartbeat_timeout_count": heartbeat_timeout_count,
        "skipped_pinned_count": skipped_pinned_count,
        "timestamp": datetime.now(UTC).isoformat(),
    }


@celery_app.task(name="app.workers.scheduled.analyze_all_repositories")
def analyze_all_repositories() -> dict:
    """
    Analyze all active repositories.

    This task runs daily via Celery Beat and queues analysis
    for each active repository.

    Returns:
        dict with statistics about queued analyses.
    """
    from app.core.database import get_sync_session
    from app.models.repository import Repository
    from app.workers.analysis import analyze_repository

    logger.info("Starting daily repository analysis sweep")

    queued_count = 0
    skipped_count = 0
    error_count = 0

    try:
        with get_sync_session() as db:
            # Get all active repositories
            result = db.execute(
                select(Repository).where(Repository.is_active)
            )
            repositories = result.scalars().all()

            for repo in repositories:
                try:
                    # Skip if analyzed recently (within last 12 hours)
                    if repo.last_analysis_at:
                        time_since = datetime.now(UTC) - repo.last_analysis_at
                        if time_since < timedelta(hours=12):
                            logger.debug(
                                f"Skipping repo {repo.id}: analyzed {time_since} ago"
                            )
                            skipped_count += 1
                            continue

                    # Create analysis record first
                    from app.models.analysis import Analysis
                    analysis = Analysis(
                        repository_id=repo.id,
                        commit_sha="HEAD",
                        branch=repo.default_branch,
                        status="pending",
                    )
                    db.add(analysis)
                    db.flush()

                    # Queue analysis task with analysis_id
                    analyze_repository.delay(
                        repository_id=str(repo.id),
                        analysis_id=str(analysis.id),
                        commit_sha=None,  # Analyze latest commit
                        triggered_by="scheduled",
                    )
                    queued_count += 1
                    logger.info(f"Queued analysis for repository {repo.id}")

                except Exception as e:
                    logger.error(f"Failed to queue analysis for repo {repo.id}: {e}")
                    error_count += 1

            # Commit all analysis records
            db.commit()

    except Exception as e:
        logger.error(f"Failed to run daily analysis sweep: {e}")
        raise

    result = {
        "status": "completed",
        "queued": queued_count,
        "skipped": skipped_count,
        "errors": error_count,
        "timestamp": datetime.now(UTC).isoformat(),
    }

    logger.info(f"Daily analysis sweep completed: {result}")
    return result


@celery_app.task(name="app.workers.scheduled.cleanup_old_data")
def cleanup_old_data() -> dict:
    """
    Clean up old data to maintain storage efficiency.

    This task runs weekly and removes:
    - Old analysis logs (> 30 days)
    - Orphaned embeddings
    - Expired cache entries

    Returns:
        dict with cleanup statistics.
    """
    from datetime import datetime

    logger.info("Starting weekly data cleanup")

    deleted_logs = 0
    deleted_embeddings = 0

    try:
        # TODO: Implement actual cleanup logic
        # - Delete old agent logs from MinIO
        # - Remove embeddings for deleted repositories
        # - Clean up Redis cache

        # Placeholder implementation
        logger.info("Cleanup tasks placeholder - implement actual cleanup")

    except Exception as e:
        logger.error(f"Failed to run cleanup: {e}")
        raise

    result = {
        "status": "completed",
        "deleted_logs": deleted_logs,
        "deleted_embeddings": deleted_embeddings,
        "timestamp": datetime.now(UTC).isoformat(),
    }

    logger.info(f"Weekly cleanup completed: {result}")
    return result


@celery_app.task(name="app.workers.scheduled.cleanup_vector_retention")
def cleanup_vector_retention() -> dict:
    """
    Clean up vectors for analyses that exceed the retention policy.

    Retention policy (configurable via settings):
    - Keep last N completed analyses per repository (vector_retention_max_analyses)
    - Keep analyses newer than X days (vector_retention_max_days)
    - Never delete pinned analyses

    An analysis is pruned if it exceeds BOTH conditions (i.e., it's outside
    the top N AND older than X days). This OR logic means generous retention.

    This task runs daily via Celery Beat.

    Returns:
        dict with cleanup statistics.
    """

    from sqlalchemy import select

    from app.core.config import settings
    from app.core.database import get_sync_session
    from app.models.repository import Repository
    from app.services.vector_store import VectorStoreService

    logger.info("Starting vector retention cleanup")

    if not settings.vector_retention_enabled:
        logger.info("Vector retention cleanup is disabled")
        return {
            "status": "skipped",
            "reason": "retention disabled",
            "timestamp": datetime.now(UTC).isoformat(),
        }

    max_analyses = settings.vector_retention_max_analyses
    max_days = settings.vector_retention_max_days

    # If both are 0 (unlimited), skip cleanup
    if max_analyses == 0 and max_days == 0:
        logger.info("Vector retention: both limits are unlimited, skipping cleanup")
        return {
            "status": "skipped",
            "reason": "unlimited retention",
            "timestamp": datetime.now(UTC).isoformat(),
        }

    cutoff_date = datetime.now(UTC) - timedelta(days=max_days) if max_days > 0 else None

    pruned_count = 0
    vectors_deleted = 0
    repos_processed = 0
    errors: list[str] = []

    try:
        vs = VectorStoreService()

        with get_sync_session() as db:
            # Get all repositories
            repos = db.execute(select(Repository.id)).scalars().all()

            for repo_id in repos:
                repos_processed += 1
                try:
                    analyses_to_prune = _find_analyses_to_prune(
                        db=db,
                        repository_id=repo_id,
                        max_analyses=max_analyses,
                        cutoff_date=cutoff_date,
                    )

                    for analysis in analyses_to_prune:
                        if not analysis.commit_sha:
                            logger.warning(
                                f"Analysis {analysis.id} has no commit_sha, skipping vector delete"
                            )
                            continue

                        try:
                            # Count vectors before delete for telemetry
                            count_before = vs.count_vectors(
                                repository_id=str(repo_id),
                                commit_sha=analysis.commit_sha,
                            )

                            if count_before > 0:
                                vs.delete_vectors(
                                    repository_id=str(repo_id),
                                    commit_sha=analysis.commit_sha,
                                )
                                vectors_deleted += count_before
                                logger.info(
                                    f"Deleted {count_before} vectors for analysis {analysis.id} "
                                    f"(repo={repo_id}, commit={analysis.commit_sha[:8]})"
                                )

                            # Reset vectors_count on the analysis record
                            analysis.vectors_count = 0
                            pruned_count += 1

                        except Exception as e:
                            error_msg = (
                                f"Failed to delete vectors for analysis {analysis.id}: {e}"
                            )
                            logger.error(error_msg)
                            errors.append(error_msg)

                    db.commit()

                except Exception as e:
                    error_msg = f"Failed to process repository {repo_id}: {e}"
                    logger.error(error_msg)
                    errors.append(error_msg)
                    db.rollback()

    except Exception as e:
        logger.error(f"Vector retention cleanup failed: {e}")
        raise

    result = {
        "status": "completed" if not errors else "completed_with_errors",
        "repos_processed": repos_processed,
        "analyses_pruned": pruned_count,
        "vectors_deleted": vectors_deleted,
        "errors": errors[:10] if errors else [],  # Limit error list size
        "error_count": len(errors),
        "timestamp": datetime.now(UTC).isoformat(),
    }

    logger.info(f"Vector retention cleanup completed: {result}")
    return result


def _find_analyses_to_prune(
    db,
    repository_id,
    max_analyses: int,
    cutoff_date: datetime | None,
) -> list:
    """Find analyses that should have their vectors pruned.

    Logic:
    - Never prune pinned analyses
    - Keep the most recent N completed analyses (if max_analyses > 0)
    - Keep analyses newer than cutoff_date (if cutoff_date is set)
    - Prune analyses that fail BOTH conditions (outside top N AND older than cutoff)

    Args:
        db: Database session
        repository_id: Repository UUID
        max_analyses: Number of recent analyses to keep (0 = no limit)
        cutoff_date: Prune analyses older than this (None = no time limit)

    Returns:
        List of Analysis objects to prune
    """
    from sqlalchemy import select

    from app.models.analysis import Analysis

    # Build base query for completed, non-pinned analyses with vectors
    base_query = (
        select(Analysis)
        .where(
            Analysis.repository_id == repository_id,
            Analysis.status == "completed",
            Analysis.pinned.is_(False),  # Never prune pinned
            Analysis.vectors_count > 0,  # Only consider analyses with vectors
        )
        .order_by(Analysis.created_at.desc())
    )

    all_eligible = db.execute(base_query).scalars().all()

    if not all_eligible:
        return []

    # Determine which analyses to keep
    to_keep_ids = set()

    # Keep top N if max_analyses > 0
    if max_analyses > 0:
        top_n = all_eligible[:max_analyses]
        to_keep_ids.update(a.id for a in top_n)

    # Keep analyses newer than cutoff_date
    if cutoff_date:
        for a in all_eligible:
            if a.created_at and a.created_at >= cutoff_date:
                to_keep_ids.add(a.id)

    # If both limits are set, we keep the UNION (OR logic = generous retention)
    # Prune = those NOT in to_keep
    to_prune = [a for a in all_eligible if a.id not in to_keep_ids]

    return to_prune


@celery_app.task(name="app.workers.scheduled.health_check")
def health_check() -> dict:
    """
    Perform hourly health check of system components.

    Checks:
    - Database connectivity
    - Redis connectivity
    - Qdrant connectivity
    - MinIO connectivity

    Returns:
        dict with health status of each component.
    """
    from datetime import datetime

    logger.info("Running health check")

    health_status = {
        "timestamp": datetime.now(UTC).isoformat(),
        "components": {},
    }

    # Check PostgreSQL
    try:
        from sqlalchemy import text

        from app.core.database import get_sync_session
        with get_sync_session() as db:
            db.execute(text("SELECT 1"))
        health_status["components"]["postgresql"] = "healthy"
    except Exception as e:
        logger.error(f"PostgreSQL health check failed: {e}")
        health_status["components"]["postgresql"] = f"unhealthy: {str(e)}"

    # Check Redis
    try:
        import redis

        from app.core.config import settings
        r = redis.from_url(str(settings.redis_url))
        r.ping()
        health_status["components"]["redis"] = "healthy"
    except Exception as e:
        logger.error(f"Redis health check failed: {e}")
        health_status["components"]["redis"] = f"unhealthy: {str(e)}"

    # Check Qdrant
    try:
        from qdrant_client import QdrantClient

        from app.core.config import settings
        client = QdrantClient(
            host=settings.qdrant_host,
            port=settings.qdrant_port,
            timeout=settings.qdrant_timeout,
        )
        client.get_collections()
        health_status["components"]["qdrant"] = "healthy"
    except Exception as e:
        logger.error(f"Qdrant health check failed: {e}")
        health_status["components"]["qdrant"] = f"unhealthy: {str(e)}"

    # Check MinIO
    try:
        from minio import Minio

        from app.core.config import settings
        client = Minio(
            settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure,
        )
        client.list_buckets()
        health_status["components"]["minio"] = "healthy"
    except Exception as e:
        logger.error(f"MinIO health check failed: {e}")
        health_status["components"]["minio"] = f"unhealthy: {str(e)}"

    # Determine overall status
    unhealthy = [k for k, v in health_status["components"].items()
                 if "unhealthy" in str(v)]
    health_status["status"] = "unhealthy" if unhealthy else "healthy"

    logger.info(f"Health check completed: {health_status['status']}")
    return health_status


@celery_app.task(name="app.workers.scheduled.send_weekly_digest")
def send_weekly_digest() -> dict:
    """
    Send weekly digest emails to users.

    Summarizes:
    - VCI changes across repositories
    - Auto-PRs created and merged
    - New issues detected

    Returns:
        dict with digest send statistics.
    """
    logger.info("Starting weekly digest send")

    # TODO: Implement email sending logic
    # - Get users with weekly_digest enabled
    # - Generate summary for each user's repositories
    # - Send email via email service

    result = {
        "status": "completed",
        "emails_sent": 0,
        "errors": 0,
        "timestamp": datetime.now(UTC).isoformat(),
    }

    logger.info(f"Weekly digest completed: {result}")
    return result
