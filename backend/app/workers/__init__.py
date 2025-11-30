"""Celery workers and tasks.

Note: Tasks are NOT imported at module level to avoid fork-safety issues
with LiteLLM/aiohttp when used with Celery prefork pool on macOS.

Celery autodiscover_tasks() will find tasks in each submodule automatically.
"""

# Do NOT import tasks here - it causes SIGSEGV with Celery prefork on macOS
# because LiteLLM (used by embeddings) is not fork-safe.
#
# from app.workers.analysis import analyze_repository
# from app.workers.embeddings import generate_embeddings
# from app.workers.healing import heal_issue, retry_healing
# from app.workers.notifications import send_notification

__all__ = [
    "analyze_repository",
    "generate_embeddings",
    "heal_issue",
    "retry_healing",
    "send_notification",
]
