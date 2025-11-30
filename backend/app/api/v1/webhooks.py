"""GitHub Webhook handlers."""

import hashlib
import hmac
import logging

from fastapi import APIRouter, Header, HTTPException, Request, status
from sqlalchemy import select

from app.api.deps import DbSession
from app.core.config import settings
from app.models.repository import Repository
from app.workers.analysis import analyze_repository

router = APIRouter()
logger = logging.getLogger(__name__)


def verify_webhook_signature(payload: bytes, signature: str | None) -> bool:
    """Verify GitHub webhook signature."""
    if not settings.github_webhook_secret:
        logger.warning("Webhook secret not configured, skipping verification")
        return True
    
    if not signature:
        return False
    
    # GitHub sends signature as 'sha256=...'
    if signature.startswith("sha256="):
        signature = signature[7:]
    
    expected = hmac.new(
        settings.github_webhook_secret.encode(),
        payload,
        hashlib.sha256,
    ).hexdigest()
    
    return hmac.compare_digest(expected, signature)


@router.post("/github")
async def github_webhook(
    request: Request,
    db: DbSession,
    x_hub_signature_256: str | None = Header(None),
    x_github_event: str | None = Header(None),
    x_github_delivery: str | None = Header(None),
) -> dict:
    """
    Handle GitHub webhook events.
    
    Supported events:
    - push: Trigger analysis on new commits
    - pull_request: Update PR status
    - installation: Handle app installation/uninstallation
    """
    # Get raw payload for signature verification
    payload = await request.body()
    
    # Verify signature
    if not verify_webhook_signature(payload, x_hub_signature_256):
        logger.warning(f"Invalid webhook signature for delivery {x_github_delivery}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid signature",
        )
    
    # Parse JSON payload
    try:
        data = await request.json()
    except Exception as e:
        logger.error(f"Failed to parse webhook payload: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON payload",
        )
    
    logger.info(
        f"Received GitHub webhook: event={x_github_event}, "
        f"delivery={x_github_delivery}"
    )
    
    # Route to appropriate handler
    if x_github_event == "push":
        return await handle_push_event(data, db)
    elif x_github_event == "pull_request":
        return await handle_pull_request_event(data, db)
    elif x_github_event == "installation":
        return await handle_installation_event(data, db)
    elif x_github_event == "installation_repositories":
        return await handle_installation_repositories_event(data, db)
    elif x_github_event == "ping":
        return {"status": "pong", "zen": data.get("zen")}
    else:
        logger.info(f"Ignoring unhandled event type: {x_github_event}")
        return {"status": "ignored", "event": x_github_event}


async def handle_push_event(data: dict, db: DbSession) -> dict:
    """Handle push events - trigger analysis on default branch pushes."""
    repo_data = data.get("repository", {})
    github_repo_id = repo_data.get("id")
    ref = data.get("ref", "")
    default_branch = repo_data.get("default_branch", "main")
    
    # Only process pushes to default branch
    if ref != f"refs/heads/{default_branch}":
        logger.info(f"Ignoring push to non-default branch: {ref}")
        return {"status": "ignored", "reason": "non-default branch"}
    
    # Find repository in our database
    result = await db.execute(
        select(Repository).where(Repository.github_id == github_repo_id)
    )
    repository = result.scalar_one_or_none()
    
    if not repository:
        logger.info(f"Repository {github_repo_id} not connected, ignoring push")
        return {"status": "ignored", "reason": "repository not connected"}
    
    if not repository.is_active:
        logger.info(f"Repository {repository.id} is inactive, ignoring push")
        return {"status": "ignored", "reason": "repository inactive"}
    
    # Get commit info
    head_commit = data.get("head_commit", {})
    commit_sha = head_commit.get("id") or data.get("after")
    
    logger.info(
        f"Triggering analysis for repository {repository.id}, "
        f"commit {commit_sha}"
    )
    
    # Create analysis record first
    from app.models.analysis import Analysis
    analysis = Analysis(
        repository_id=repository.id,
        commit_sha=commit_sha or "HEAD",
        branch=default_branch,
        status="pending",
    )
    db.add(analysis)
    await db.flush()
    
    # Queue analysis task with analysis_id
    task = analyze_repository.delay(
        repository_id=str(repository.id),
        analysis_id=str(analysis.id),
        commit_sha=commit_sha,
        triggered_by="webhook",
    )
    
    return {
        "status": "queued",
        "repository_id": str(repository.id),
        "analysis_id": str(analysis.id),
        "commit_sha": commit_sha,
        "task_id": task.id,
    }


async def handle_pull_request_event(data: dict, db: DbSession) -> dict:
    """Handle pull request events."""
    action = data.get("action")
    pr_data = data.get("pull_request", {})
    repo_data = data.get("repository", {})
    github_repo_id = repo_data.get("id")
    
    logger.info(
        f"Pull request event: action={action}, "
        f"pr_number={pr_data.get('number')}"
    )
    
    # Find repository
    result = await db.execute(
        select(Repository).where(Repository.github_id == github_repo_id)
    )
    repository = result.scalar_one_or_none()
    
    if not repository:
        return {"status": "ignored", "reason": "repository not connected"}
    
    # Handle different PR actions
    if action in ["opened", "synchronize", "reopened"]:
        # Could trigger PR-specific analysis
        return {
            "status": "acknowledged",
            "action": action,
            "pr_number": pr_data.get("number"),
        }
    elif action == "closed":
        # PR was closed or merged
        merged = pr_data.get("merged", False)
        return {
            "status": "acknowledged",
            "action": action,
            "merged": merged,
            "pr_number": pr_data.get("number"),
        }
    
    return {"status": "ignored", "action": action}


async def handle_installation_event(data: dict, db: DbSession) -> dict:
    """Handle GitHub App installation events."""
    action = data.get("action")
    installation = data.get("installation", {})
    
    logger.info(
        f"Installation event: action={action}, "
        f"installation_id={installation.get('id')}"
    )
    
    if action == "created":
        # New installation - could send welcome notification
        return {"status": "acknowledged", "action": "installed"}
    elif action == "deleted":
        # App uninstalled - could mark repos as inactive
        return {"status": "acknowledged", "action": "uninstalled"}
    elif action == "suspend":
        return {"status": "acknowledged", "action": "suspended"}
    elif action == "unsuspend":
        return {"status": "acknowledged", "action": "unsuspended"}
    
    return {"status": "ignored", "action": action}


async def handle_installation_repositories_event(data: dict, db: DbSession) -> dict:
    """Handle changes to repository access."""
    action = data.get("action")
    repos_added = data.get("repositories_added", [])
    repos_removed = data.get("repositories_removed", [])
    
    logger.info(
        f"Installation repositories event: action={action}, "
        f"added={len(repos_added)}, removed={len(repos_removed)}"
    )
    
    # Could update repository status based on access changes
    return {
        "status": "acknowledged",
        "action": action,
        "repos_added": len(repos_added),
        "repos_removed": len(repos_removed),
    }
