"""Healing tasks for auto-fixing issues."""

import asyncio
import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.celery import celery_app
from app.core.database import get_sync_session
from app.core.encryption import decrypt_token
from app.core.redis import get_sync_redis_context
from app.models.auto_pr import AutoPR
from app.models.issue import Issue
from app.models.repository import Repository
from app.models.user import User
from app.services.agents.orchestrator import HealingOrchestrator, HealingStatus
from app.services.github import GitHubService

logger = logging.getLogger(__name__)

# Redis channel for healing progress
HEALING_CHANNEL_PREFIX = "healing:progress:"


def run_async(coro):
    """Run async coroutine in sync Celery task context."""
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


def publish_healing_progress(
    issue_id: str,
    stage: str,
    progress: int,
    message: str | None = None,
    status: str = "running",
) -> None:
    """Publish healing progress to Redis for SSE streaming.
    
    Args:
        issue_id: Issue UUID string
        stage: Current healing stage
        progress: Progress percentage (0-100)
        message: Optional status message
        status: Overall status (running, completed, failed)
        
    Uses connection pool to prevent connection leaks.
    """
    import json

    try:
        with get_sync_redis_context() as redis:
            channel = f"{HEALING_CHANNEL_PREFIX}{issue_id}"
            data = {
                "stage": stage,
                "progress": progress,
                "message": message,
                "status": status,
                "timestamp": datetime.utcnow().isoformat(),
            }
            redis.publish(channel, json.dumps(data))
    except Exception as e:
        logger.warning(f"Failed to publish healing progress: {e}")


def _get_issue_with_context(issue_id: str) -> tuple[Issue, Repository, str | None]:
    """Load issue with repository and user access token.
    
    Args:
        issue_id: UUID string of the issue
        
    Returns:
        Tuple of (Issue, Repository, access_token or None)
        
    Raises:
        ValueError: If issue or repository not found
    """
    with get_sync_session() as db:
        # Load issue with repository relationship
        result = db.execute(
            select(Issue)
            .options(selectinload(Issue.repository))
            .where(Issue.id == issue_id)
        )
        issue = result.scalar_one_or_none()

        if not issue:
            raise ValueError(f"Issue {issue_id} not found")

        repository = issue.repository
        if not repository:
            raise ValueError(f"Repository not found for issue {issue_id}")

        # Get owner's access token
        access_token = None
        if repository.owner_id:
            user_result = db.execute(
                select(User).where(User.id == repository.owner_id)
            )
            user = user_result.scalar_one_or_none()
            if user and user.access_token_encrypted:
                try:
                    access_token = decrypt_token(user.access_token_encrypted)
                except Exception as e:
                    logger.warning(f"Could not decrypt access token: {e}")

        # Detach objects from session for use outside
        db.expunge(issue)
        db.expunge(repository)

        return issue, repository, access_token


def _get_file_content(
    owner: str,
    repo: str,
    file_path: str,
    access_token: str,
    ref: str | None = None,
) -> str:
    """Fetch file content from GitHub.
    
    Args:
        owner: Repository owner
        repo: Repository name
        file_path: Path to file in repository
        access_token: GitHub access token
        ref: Optional git reference (branch/tag/commit)
        
    Returns:
        File content as string
    """
    github = GitHubService(access_token)
    return run_async(github.get_file_content(owner, repo, file_path, ref))


def _create_auto_pr_record(
    db,
    issue: Issue,
    repository: Repository,
    status: str = "pending",
) -> AutoPR:
    """Create AutoPR database record.
    
    Args:
        db: Database session
        issue: Issue being fixed
        repository: Target repository
        status: Initial PR status
        
    Returns:
        Created AutoPR instance
    """
    auto_pr = AutoPR(
        repository_id=repository.id,
        issue_id=issue.id,
        title=f"fix: {issue.title[:100]}",
        description=f"Automated fix for issue: {issue.description or issue.title}",
        status=status,
    )
    db.add(auto_pr)
    db.commit()
    db.refresh(auto_pr)
    return auto_pr


def _update_auto_pr(
    auto_pr_id: str,
    status: str,
    github_pr_number: int | None = None,
    github_pr_url: str | None = None,
    branch_name: str | None = None,
    diff_content: str | None = None,
    test_code: str | None = None,
    validation_result: dict | None = None,
    agent_logs: list | None = None,
) -> None:
    """Update AutoPR record with healing results.
    
    Args:
        auto_pr_id: UUID of the AutoPR
        status: New status
        github_pr_number: GitHub PR number if created
        github_pr_url: GitHub PR URL if created
        branch_name: Branch name used
        diff_content: Generated diff
        test_code: Generated test code
        validation_result: Sandbox validation results
        agent_logs: Healing process logs
    """
    with get_sync_session() as db:
        result = db.execute(
            select(AutoPR).where(AutoPR.id == auto_pr_id)
        )
        auto_pr = result.scalar_one_or_none()

        if auto_pr:
            auto_pr.status = status
            if github_pr_number is not None:
                auto_pr.github_pr_number = github_pr_number
            if github_pr_url is not None:
                auto_pr.github_pr_url = github_pr_url
            if branch_name is not None:
                auto_pr.branch_name = branch_name
            if diff_content is not None:
                auto_pr.diff_content = diff_content
            if test_code is not None:
                auto_pr.test_code = test_code
            if validation_result is not None:
                auto_pr.validation_result = validation_result
            if agent_logs is not None:
                auto_pr.agent_logs = {"logs": [
                    {
                        "timestamp": log.timestamp.isoformat(),
                        "stage": log.stage,
                        "message": log.message,
                        "details": log.details,
                    }
                    for log in agent_logs
                ]}

            db.commit()


def _update_issue_status(issue_id: str, status: str) -> None:
    """Update issue status in database.
    
    Args:
        issue_id: UUID of the issue
        status: New status (fixing, fixed, fix_failed)
    """
    with get_sync_session() as db:
        result = db.execute(
            select(Issue).where(Issue.id == issue_id)
        )
        issue = result.scalar_one_or_none()

        if issue:
            issue.status = status
            db.commit()


async def _create_github_pr(
    access_token: str,
    owner: str,
    repo: str,
    default_branch: str,
    fix_result,
    test_result,
    issue_title: str,
) -> dict:
    """Create a GitHub PR with the fix.
    
    Args:
        access_token: GitHub access token
        owner: Repository owner
        repo: Repository name
        default_branch: Base branch for PR
        fix_result: FixResult from healing orchestrator
        test_result: TestResult from healing orchestrator
        issue_title: Title of the issue being fixed
        
    Returns:
        Dict with pr_number, pr_url, branch_name
    """
    github = GitHubService(access_token)

    # Generate unique branch name
    import hashlib
    import time
    branch_suffix = hashlib.md5(f"{time.time()}".encode()).hexdigest()[:8]
    branch_name = f"n9r/fix-{branch_suffix}"

    # Get base branch SHA
    base_branch = await github.get_branch(owner, repo, default_branch)
    base_sha = base_branch["commit"]["sha"]

    # Create feature branch
    await github.create_branch(owner, repo, branch_name, base_sha)

    # Commit the fix
    await github.create_or_update_file(
        owner=owner,
        repo=repo,
        path=fix_result.file_path.lstrip("/"),
        content=fix_result.fixed_content,
        message=f"fix: {issue_title[:50]}",
        branch=branch_name,
    )

    # Commit test if generated
    if test_result and test_result.success and test_result.test_content:
        try:
            await github.create_or_update_file(
                owner=owner,
                repo=repo,
                path=test_result.test_file_path.lstrip("/"),
                content=test_result.test_content,
                message=f"test: Add regression test for {issue_title[:40]}",
                branch=branch_name,
            )
        except Exception as e:
            logger.warning(f"Failed to commit test file: {e}")

    # Create Pull Request
    pr_body = f"""## 🤖 Automated Fix by n9r

### Issue
{issue_title}

### Changes
{fix_result.changes_summary or "See diff for details"}

### Validation
✅ Syntax check passed
{"✅ Tests passed" if test_result and test_result.success else "⚠️ No tests generated"}

---
*This PR was automatically generated by n9r healing pipeline.*
*Review carefully before merging.*
"""

    pr = await github.create_pull_request(
        owner=owner,
        repo=repo,
        title=f"fix: {issue_title[:80]}",
        body=pr_body,
        head=branch_name,
        base=default_branch,
    )

    return {
        "pr_number": pr["number"],
        "pr_url": pr["html_url"],
        "branch_name": branch_name,
    }


@celery_app.task(bind=True, name="app.workers.healing.heal_issue")
def heal_issue(
    self,
    issue_id: str,
    auto_pr_id: str | None = None,
    max_iterations: int = 3,
) -> dict:
    """
    Heal an issue by generating and validating a fix.
    
    This task:
    1. Loads issue and repository context
    2. Fetches file content from GitHub
    3. Runs HealingOrchestrator (diagnosis → fix → test → validate)
    4. Creates GitHub PR if successful
    5. Updates AutoPR record with results
    
    Args:
        issue_id: UUID of the issue to heal
        auto_pr_id: Optional existing AutoPR ID to update
        max_iterations: Maximum healing retry attempts
        
    Returns:
        Dict with healing results
    """
    logger.info(f"Starting healing for issue {issue_id}")

    def publish_progress(stage: str, progress: int, message: str | None = None):
        """Helper to publish progress updates."""
        publish_healing_progress(
            issue_id=issue_id,
            stage=stage,
            progress=progress,
            message=message,
            status="running",
        )
        self.update_state(state="PROGRESS", meta={"stage": stage, "progress": progress})

    try:
        # Step 1: Load issue and context
        publish_progress("initializing", 5, "Loading issue context...")
        issue, repository, access_token = _get_issue_with_context(issue_id)

        if not access_token:
            raise ValueError("No access token available for repository owner")

        if not issue.file_path:
            raise ValueError("Issue has no file_path - cannot determine file to fix")

        # Update issue status to "fixing"
        _update_issue_status(issue_id, "fixing")

        # Create or get AutoPR record
        if not auto_pr_id:
            with get_sync_session() as db:
                # Re-attach objects to this session
                repo_result = db.execute(
                    select(Repository).where(Repository.id == repository.id)
                )
                repo = repo_result.scalar_one()

                issue_result = db.execute(
                    select(Issue).where(Issue.id == issue.id)
                )
                iss = issue_result.scalar_one()

                auto_pr = _create_auto_pr_record(db, iss, repo, "healing")
                auto_pr_id = str(auto_pr.id)

        # Step 2: Fetch file content from GitHub
        publish_progress("fetching", 15, "Fetching file content...")
        owner, repo_name = repository.full_name.split("/")

        file_content = _get_file_content(
            owner=owner,
            repo=repo_name,
            file_path=issue.file_path,
            access_token=access_token,
            ref=repository.default_branch,
        )

        # Step 3: Prepare context for orchestrator
        publish_progress("diagnosing", 25, "Analyzing issue...")

        issue_dict = {
            "id": str(issue.id),
            "type": issue.type,
            "severity": issue.severity,
            "title": issue.title,
            "description": issue.description,
            "file_path": issue.file_path,
            "line_start": issue.line_start,
            "line_end": issue.line_end,
            "metadata": issue.issue_metadata,
        }

        repository_dict = {
            "id": str(repository.id),
            "full_name": repository.full_name,
            "clone_url": f"https://github.com/{repository.full_name}",
            "default_branch": repository.default_branch,
        }

        # Callback for orchestrator logs
        healing_logs = []

        def on_log(log_entry):
            healing_logs.append(log_entry)
            # Map orchestrator stages to progress percentages
            stage_progress = {
                "diagnosis": 35,
                "fix": 50,
                "test": 65,
                "validation": 80,
                "retry": 70,
            }
            progress = stage_progress.get(log_entry.stage, 50)
            publish_progress(log_entry.stage, progress, log_entry.message)

        # Step 4: Run healing orchestrator
        orchestrator = HealingOrchestrator(max_iterations=max_iterations)

        result = run_async(orchestrator.heal_issue(
            issue=issue_dict,
            repository=repository_dict,
            file_content=file_content,
            related_files=None,
            on_log=on_log,
            access_token=access_token,
        ))

        # Step 5: Process result
        if result.status == HealingStatus.COMPLETED:
            publish_progress("creating_pr", 90, "Creating pull request...")

            # Create GitHub PR
            pr_result = run_async(_create_github_pr(
                access_token=access_token,
                owner=owner,
                repo=repo_name,
                default_branch=repository.default_branch,
                fix_result=result.fix,
                test_result=result.test,
                issue_title=issue.title,
            ))

            # Update AutoPR with success
            _update_auto_pr(
                auto_pr_id=auto_pr_id,
                status="pending_review",
                github_pr_number=pr_result["pr_number"],
                github_pr_url=pr_result["pr_url"],
                branch_name=pr_result["branch_name"],
                diff_content=result.fix.fixed_content if result.fix else None,
                test_code=result.test.test_content if result.test and result.test.success else None,
                validation_result={"passed": True, "iterations": result.iterations_used},
                agent_logs=result.logs,
            )

            # Update issue status
            _update_issue_status(issue_id, "fix_pending")

            # Publish completion
            publish_healing_progress(
                issue_id=issue_id,
                stage="completed",
                progress=100,
                message=f"PR created: {pr_result['pr_url']}",
                status="completed",
            )

            logger.info(f"Healing completed for issue {issue_id}, PR: {pr_result['pr_url']}")

            return {
                "issue_id": issue_id,
                "auto_pr_id": auto_pr_id,
                "status": "completed",
                "pr_number": pr_result["pr_number"],
                "pr_url": pr_result["pr_url"],
                "branch_name": pr_result["branch_name"],
                "iterations_used": result.iterations_used,
            }

        elif result.status == HealingStatus.MANUAL_REQUIRED:
            _update_auto_pr(
                auto_pr_id=auto_pr_id,
                status="manual_required",
                agent_logs=result.logs,
            )
            _update_issue_status(issue_id, "manual_required")

            publish_healing_progress(
                issue_id=issue_id,
                stage="manual_required",
                progress=100,
                message="Issue requires manual intervention",
                status="manual_required",
            )

            return {
                "issue_id": issue_id,
                "auto_pr_id": auto_pr_id,
                "status": "manual_required",
                "message": "Issue cannot be auto-fixed, requires manual intervention",
            }

        else:
            # Healing failed
            _update_auto_pr(
                auto_pr_id=auto_pr_id,
                status="failed",
                validation_result={"passed": False, "error": result.error_message},
                agent_logs=result.logs,
            )
            _update_issue_status(issue_id, "fix_failed")

            publish_healing_progress(
                issue_id=issue_id,
                stage="failed",
                progress=100,
                message=result.error_message,
                status="failed",
            )

            logger.warning(f"Healing failed for issue {issue_id}: {result.error_message}")

            return {
                "issue_id": issue_id,
                "auto_pr_id": auto_pr_id,
                "status": "failed",
                "error": result.error_message,
                "iterations_used": result.iterations_used,
            }

    except Exception as e:
        error_msg = str(e)
        logger.error(f"Healing failed for issue {issue_id}: {error_msg}")

        # Update records on failure
        if auto_pr_id:
            _update_auto_pr(
                auto_pr_id=auto_pr_id,
                status="failed",
                validation_result={"passed": False, "error": error_msg},
            )

        _update_issue_status(issue_id, "fix_failed")

        publish_healing_progress(
            issue_id=issue_id,
            stage="error",
            progress=0,
            message=error_msg,
            status="failed",
        )

        self.update_state(state="FAILURE", meta={"error": error_msg})
        raise


@celery_app.task(name="app.workers.healing.retry_healing")
def retry_healing(
    auto_pr_id: str,
    feedback: str | None = None,
) -> dict:
    """
    Retry healing for a failed or rejected AutoPR.
    
    Args:
        auto_pr_id: UUID of the AutoPR to retry
        feedback: Optional user feedback to incorporate
        
    Returns:
        Dict with new healing task info
    """
    logger.info(f"Retrying healing for AutoPR {auto_pr_id}")

    with get_sync_session() as db:
        result = db.execute(
            select(AutoPR)
            .options(selectinload(AutoPR.issue))
            .where(AutoPR.id == auto_pr_id)
        )
        auto_pr = result.scalar_one_or_none()

        if not auto_pr:
            raise ValueError(f"AutoPR {auto_pr_id} not found")

        if not auto_pr.issue:
            raise ValueError(f"No issue linked to AutoPR {auto_pr_id}")

        issue_id = str(auto_pr.issue.id)

        # Reset status
        auto_pr.status = "healing"
        if feedback:
            auto_pr.review_feedback = feedback
        db.commit()

    # Queue new healing task
    task = heal_issue.delay(
        issue_id=issue_id,
        auto_pr_id=auto_pr_id,
        max_iterations=3,
    )

    return {
        "auto_pr_id": auto_pr_id,
        "issue_id": issue_id,
        "task_id": task.id,
        "status": "queued",
    }
