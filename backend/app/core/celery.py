"""Celery configuration and app."""

from celery import Celery
from celery.schedules import crontab

from app.core.config import settings

celery_app = Celery(
    "n9r",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)

# Celery configuration
celery_app.conf.update(
    # Serialization
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",

    # Timezone
    timezone="UTC",
    enable_utc=True,

    # Task settings
    task_track_started=True,
    task_time_limit=30 * 60,  # 30 minutes max
    task_soft_time_limit=25 * 60,  # 25 minutes soft limit

    # Result settings
    result_expires=3600,  # Results expire after 1 hour

    # Worker settings
    worker_prefetch_multiplier=1,  # One task at a time per worker
    worker_concurrency=4,

    # Task routing
    task_routes={
        "app.workers.ai_scan.*": {"queue": "ai_scan"},
        "app.workers.analysis.*": {"queue": "analysis"},
        "app.workers.embeddings.*": {"queue": "embeddings"},
        "app.workers.healing.*": {"queue": "healing"},
        "app.workers.notifications.*": {"queue": "notifications"},
    },

    # Default queue
    task_default_queue="default",

    # Task acknowledgement
    task_acks_late=True,
    task_reject_on_worker_lost=True,

    # Beat scheduler configuration
    beat_schedule={
        # Daily analysis of all active repositories
        "daily-repo-analysis": {
            "task": "app.workers.scheduled.analyze_all_repositories",
            "schedule": crontab(hour=2, minute=0),  # Run at 2:00 AM UTC
            "options": {"queue": "analysis"},
        },
        # Weekly cleanup of old data
        "weekly-cleanup": {
            "task": "app.workers.scheduled.cleanup_old_data",
            "schedule": crontab(hour=4, minute=0, day_of_week=0),  # Sunday 4:00 AM
            "options": {"queue": "default"},
        },
        # Hourly health check
        "hourly-health-check": {
            "task": "app.workers.scheduled.health_check",
            "schedule": crontab(minute=0),  # Every hour
            "options": {"queue": "default"},
        },
        # Cleanup stuck analyses every 10 minutes
        "cleanup-stuck-analyses": {
            "task": "app.workers.scheduled.cleanup_stuck_analyses",
            "schedule": crontab(minute="*/10"),  # Every 10 minutes
            "options": {"queue": "default"},
        },
    },
)

# Explicitly import each worker module to register tasks with Celery.
# Note: We import modules directly instead of using autodiscover_tasks()
# because we need to control the import order and avoid loading LiteLLM
# at module level (it's not fork-safe on macOS).
import app.workers.ai_scan  # noqa: F401, E402
import app.workers.analysis  # noqa: F401, E402
import app.workers.embeddings  # noqa: F401, E402
import app.workers.healing  # noqa: F401, E402
import app.workers.notifications  # noqa: F401, E402
import app.workers.scheduled  # noqa: F401, E402
