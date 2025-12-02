"""Scheduled tasks for periodic operations."""

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update

from app.core.celery import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="app.workers.scheduled.cleanup_stuck_analyses")
def cleanup_stuck_analyses() -> dict:
    """
    Clean up stuck analyses that have been pending/running too long.
    
    This task runs every 10 minutes via Celery Beat and marks
    analyses older than 10 minutes as failed.
    
    Returns:
        dict with cleanup statistics.
    """
    from app.core.database import get_sync_session
    from app.models.analysis import Analysis
    
    logger.info("Starting stuck analyses cleanup")
    
    stuck_threshold = datetime.now(timezone.utc) - timedelta(minutes=10)
    
    try:
        with get_sync_session() as db:
            # Find and update stuck analyses in one query
            result = db.execute(
                update(Analysis)
                .where(
                    Analysis.status.in_(["pending", "running"]),
                    Analysis.created_at < stuck_threshold,
                )
                .values(
                    status="failed",
                    error_message="Analysis timed out (auto-cleaned by scheduler)",
                    completed_at=datetime.now(timezone.utc),
                )
                .returning(Analysis.id)
            )
            cleaned_ids = [str(row[0]) for row in result.fetchall()]
            db.commit()
            
            if cleaned_ids:
                logger.warning(f"Cleaned up {len(cleaned_ids)} stuck analyses: {cleaned_ids}")
            else:
                logger.debug("No stuck analyses found")
                
    except Exception as e:
        logger.error(f"Failed to cleanup stuck analyses: {e}")
        raise
    
    return {
        "status": "completed",
        "cleaned_count": len(cleaned_ids),
        "cleaned_ids": cleaned_ids,
        "timestamp": datetime.now(timezone.utc).isoformat(),
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
    from sqlalchemy import select
    
    logger.info("Starting daily repository analysis sweep")
    
    queued_count = 0
    skipped_count = 0
    error_count = 0
    
    try:
        with get_sync_session() as db:
            # Get all active repositories
            result = db.execute(
                select(Repository).where(Repository.is_active == True)
            )
            repositories = result.scalars().all()
            
            for repo in repositories:
                try:
                    # Skip if analyzed recently (within last 12 hours)
                    if repo.last_analysis_at:
                        time_since = datetime.now(timezone.utc) - repo.last_analysis_at
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
        "timestamp": datetime.now(timezone.utc).isoformat(),
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
    from datetime import datetime, timedelta
    
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
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    
    logger.info(f"Weekly cleanup completed: {result}")
    return result


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
    from datetime import datetime, timezone
    
    logger.info("Running health check")
    
    health_status = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
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
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    
    logger.info(f"Weekly digest completed: {result}")
    return result
