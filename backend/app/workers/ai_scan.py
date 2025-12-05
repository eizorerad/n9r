"""AI Scan Celery task for AI-powered code analysis.

Orchestrates the AI scan pipeline:
1. Clone repository at specific commit
2. Generate LLM-friendly repo view
3. Run multi-model broad scan
4. Merge and deduplicate issues
5. Cache results in Analysis.ai_scan_cache

State is managed through AnalysisStateService with PostgreSQL as the single source of truth.

**Feature: ai-scan-progress-fix**
**Validates: Requirements 1.3, 1.4, 2.2, 4.1, 4.3**
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.core.celery import celery_app
from app.core.config import settings
from app.core.database import get_sync_session
from app.models.analysis import Analysis
from app.models.repository import Repository
from app.models.user import User

logger = logging.getLogger(__name__)


# =============================================================================
# Constants
# =============================================================================

# AI Scan progress channel prefix
AI_SCAN_PROGRESS_PREFIX = "ai_scan:progress:"
AI_SCAN_STATE_PREFIX = "ai_scan:state:"
AI_SCAN_STATE_TTL = 3600  # 1 hour


# =============================================================================
# Helper Functions
# =============================================================================


def _get_db_session() -> Session:
    """Create a new database session for worker tasks.
    
    Returns:
        SQLAlchemy Session instance
    """
    engine = create_engine(str(settings.database_url))
    return Session(engine)


def _update_ai_scan_state(
    analysis_id: str,
    status: str | None = None,
    progress: int | None = None,
    stage: str | None = None,
    message: str | None = None,
    error: str | None = None,
    cache_data: dict[str, Any] | None = None,
) -> None:
    """Update AI scan state in PostgreSQL via AnalysisStateService.
    
    This is the primary state update mechanism. Redis pub/sub is used for
    real-time updates but PostgreSQL is the single source of truth.
    
    Follows the same pattern as _update_embeddings_state in embeddings.py.
    
    Args:
        analysis_id: UUID of the analysis (as string)
        status: New ai_scan_status (if changing status)
        progress: Progress percentage (0-100)
        stage: Current stage name
        message: Human-readable progress message
        error: Error message (for failed status)
        cache_data: AI scan results (for completed status)
        
    **Feature: ai-scan-progress-fix**
    **Validates: Requirements 2.2**
    """
    from app.services.analysis_state import AnalysisStateService
    
    try:
        with _get_db_session() as session:
            state_service = AnalysisStateService(session, publish_events=True)
            
            if status == "running":
                # Use start_ai_scan for pending -> running transition
                state_service.start_ai_scan(UUID(analysis_id))
            elif status == "completed" and cache_data is not None:
                # Use complete_ai_scan for running -> completed transition
                state_service.complete_ai_scan(UUID(analysis_id), cache_data)
            elif status == "failed":
                # Use fail_ai_scan for -> failed transition
                state_service.fail_ai_scan(UUID(analysis_id), error or "Unknown error")
            elif progress is not None and stage is not None:
                # Progress update without status change
                state_service.update_ai_scan_progress(
                    UUID(analysis_id),
                    progress=progress,
                    stage=stage,
                    message=message,
                )
            
    except Exception as e:
        logger.warning(f"Failed to update AI scan state in PostgreSQL: {e}")
        # Don't raise - we still want to continue processing


def run_async(coro):
    """Run async function in sync context."""
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


def get_ai_scan_channel(analysis_id: str) -> str:
    """Get Redis channel name for AI scan progress."""
    return f"{AI_SCAN_PROGRESS_PREFIX}{analysis_id}"


def get_ai_scan_state_key(analysis_id: str) -> str:
    """Get Redis key for storing AI scan progress state."""
    return f"{AI_SCAN_STATE_PREFIX}{analysis_id}"


def publish_ai_scan_progress(
    analysis_id: str,
    stage: str,
    progress: int,
    message: str | None = None,
    status: str = "running",
) -> None:
    """Publish AI scan progress to Redis channel and store state.
    
    Args:
        analysis_id: The analysis ID
        stage: Current stage of the scan
        progress: Progress percentage (0-100)
        message: Human-readable progress message
        status: Scan status (running, completed, failed)
    """
    import json

    from app.core.redis import get_sync_redis_context

    with get_sync_redis_context() as redis_client:
        channel = get_ai_scan_channel(analysis_id)
        state_key = get_ai_scan_state_key(analysis_id)

        payload_dict = {
            "analysis_id": analysis_id,
            "stage": stage,
            "progress": progress,
            "message": message,
            "status": status,
        }

        payload = json.dumps(payload_dict)

        # Store state for late subscribers
        redis_client.setex(state_key, AI_SCAN_STATE_TTL, payload)

        # Publish for real-time updates
        redis_client.publish(channel, payload)
        logger.debug(f"Published AI scan progress to {channel}: {stage} {progress}%")


def _get_analysis_with_repo(analysis_id: str) -> tuple[Analysis, Repository, str | None, str, str]:
    """Get analysis record with repository and access token.
    
    Args:
        analysis_id: UUID of the analysis
        
    Returns:
        Tuple of (Analysis, Repository, access_token, commit_sha, repo_url)
        
    Raises:
        ValueError: If analysis or repository not found
    """
    from app.core.encryption import decrypt_token

    with get_sync_session() as db:
        # Fetch analysis
        result = db.execute(
            select(Analysis).where(Analysis.id == analysis_id)
        )
        analysis = result.scalar_one_or_none()

        if not analysis:
            raise ValueError(f"Analysis {analysis_id} not found")

        if analysis.status != "completed":
            raise ValueError(
                f"Analysis {analysis_id} is not completed (status: {analysis.status}). "
                "AI scan requires a completed analysis."
            )

        # Fetch repository
        repo_result = db.execute(
            select(Repository).where(Repository.id == analysis.repository_id)
        )
        repository = repo_result.scalar_one_or_none()

        if not repository:
            raise ValueError(f"Repository for analysis {analysis_id} not found")

        # Get owner's access token for private repos
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
        commit_sha = analysis.commit_sha
        repo_url = f"https://github.com/{repository.full_name}"

        return analysis, repository, access_token, commit_sha, repo_url


def _update_ai_scan_cache(analysis_id: str, cache_data: dict[str, Any]) -> None:
    """Update Analysis.ai_scan_cache in database.
    
    Args:
        analysis_id: UUID of the analysis
        cache_data: AI scan cache data to store
    """
    with get_sync_session() as db:
        result = db.execute(
            select(Analysis).where(Analysis.id == analysis_id)
        )
        analysis = result.scalar_one_or_none()

        if analysis:
            analysis.ai_scan_cache = cache_data
            db.commit()
            logger.info(f"Updated ai_scan_cache for analysis {analysis_id}")
        else:
            logger.warning(f"Analysis {analysis_id} not found for cache update")


def _mark_ai_scan_failed(analysis_id: str, error_message: str) -> None:
    """Mark AI scan as failed in the cache.
    
    Args:
        analysis_id: UUID of the analysis
        error_message: Error message to store
    """
    cache_data = {
        "status": "failed",
        "error_message": error_message[:500],
        "computed_at": datetime.now(timezone.utc).isoformat(),
    }
    _update_ai_scan_cache(analysis_id, cache_data)

    # Publish failure to Redis
    publish_ai_scan_progress(
        analysis_id=analysis_id,
        stage="failed",
        progress=0,
        message=error_message[:200],
        status="failed",
    )


async def _investigate_issues(
    merged_issues: list,
    investigate_severity: list[str],
    max_issues: int,
    repo_path: Any,
    llm_gateway: Any,
    publish_progress: Any,
) -> list:
    """Investigate high-severity issues using the IssueInvestigator.
    
    Args:
        merged_issues: List of MergedIssue objects
        investigate_severity: List of severity levels to investigate
        max_issues: Maximum number of issues to investigate
        repo_path: Path to the cloned repository
        llm_gateway: LLMGateway instance
        publish_progress: Function to publish progress updates
        
    Returns:
        Updated list of MergedIssue objects with investigation results
    """
    from app.services.issue_investigator import get_issue_investigator
    
    # Filter issues by severity
    issues_to_investigate = [
        issue for issue in merged_issues
        if issue.severity in investigate_severity
    ][:max_issues]
    
    if not issues_to_investigate:
        logger.info("No issues match investigation criteria")
        return merged_issues
    
    logger.info(
        f"Investigating {len(issues_to_investigate)} issues "
        f"(severity: {investigate_severity})"
    )
    
    # Create investigator
    investigator = get_issue_investigator(
        llm_gateway=llm_gateway,
        repo_path=repo_path,
        sandbox=None,  # CLI commands disabled for now
    )
    
    # Investigate each issue
    for i, issue in enumerate(issues_to_investigate):
        progress_pct = 80 + int((i / len(issues_to_investigate)) * 10)
        publish_progress(
            "investigating",
            progress_pct,
            f"Investigating issue {i + 1}/{len(issues_to_investigate)}: {issue.id}"
        )
        
        try:
            result = await investigator.investigate(issue)
            
            # Update issue with investigation results
            issue.investigation_status = result.status
            if result.suggested_fix:
                issue.suggested_fix = result.suggested_fix
            
            logger.info(
                f"Issue {issue.id} investigation: {result.status} "
                f"({result.iterations_used} iterations)"
            )
            
        except Exception as e:
            logger.error(f"Failed to investigate issue {issue.id}: {e}")
            issue.investigation_status = "uncertain"
    
    return merged_issues



# =============================================================================
# Main Celery Task
# =============================================================================


@celery_app.task(bind=True, name="app.workers.ai_scan.run_ai_scan")
def run_ai_scan(
    self,
    analysis_id: str,
    models: list[str] | None = None,
    investigate_severity: list[str] | None = None,
    max_issues: int = 10,
) -> dict:
    """Run AI-powered scan on repository.
    
    Uses the same commit_sha as the parent Analysis record.
    Results are cached in Analysis.ai_scan_cache.
    
    State is managed through AnalysisStateService with PostgreSQL as the
    single source of truth. Redis pub/sub is used for real-time updates.
    
    Args:
        analysis_id: UUID of the analysis to scan
        models: List of LLM models to use (defaults to Gemini + Claude)
        investigate_severity: Severity levels to investigate (not implemented yet)
        max_issues: Maximum issues to investigate (not implemented yet)
        
    Returns:
        Dict with scan results summary
        
    **Feature: ai-scan-progress-fix**
    **Validates: Requirements 1.3, 1.4, 4.1, 4.3**
    """
    from app.services.broad_scan_agent import (
            DEFAULT_SCAN_MODELS,
            get_broad_scan_agent,
        )
    from app.services.issue_merger import get_issue_merger
    from app.services.repo_view_generator import RepoViewGenerator

    logger.info(f"Starting AI scan for analysis {analysis_id}")

    # Use default models if not specified
    if models is None:
        models = DEFAULT_SCAN_MODELS.copy()

    def publish_progress(stage: str, progress: int, message: str | None = None):
        """Helper to publish progress updates.
        
        Updates state in PostgreSQL (primary) and Redis (for real-time updates).
        
        **Feature: ai-scan-progress-fix**
        **Validates: Requirements 4.1, 4.3**
        """
        # Update PostgreSQL state via AnalysisStateService (primary source of truth)
        if stage == "initializing" and progress <= 5:
            # Transition from pending -> running (Requirements 1.3)
            _update_ai_scan_state(
                analysis_id=analysis_id,
                status="running",
            )
        else:
            # Progress update without status change (Requirements 4.3)
            _update_ai_scan_state(
                analysis_id=analysis_id,
                progress=progress,
                stage=stage,
                message=message,
            )
        
        # Also publish to Redis for real-time SSE updates (Requirements 4.1)
        publish_ai_scan_progress(
            analysis_id=analysis_id,
            stage=stage,
            progress=progress,
            message=message,
            status="running",
        )
        self.update_state(state="PROGRESS", meta={"stage": stage, "progress": progress})

    try:
        # Step 1: Mark scan as running via state service
        publish_progress("initializing", 5, "Initializing AI scan...")

        # Step 2: Get analysis and repository info
        publish_progress("loading", 10, "Loading analysis data...")
        try:
            analysis, repository, access_token, commit_sha, repo_url = _get_analysis_with_repo(analysis_id)
        except ValueError as e:
            logger.error(f"Failed to load analysis: {e}")
            _mark_ai_scan_failed(analysis_id, str(e))
            raise

        logger.info(f"AI scan for {repo_url} at commit {commit_sha[:7]}")

        # Step 3: Clone repository at specific commit
        publish_progress("cloning", 20, f"Cloning repository at commit {commit_sha[:7]}...")

        from app.services.repo_analyzer import RepoAnalyzer

        with RepoAnalyzer(repo_url, access_token, commit_sha=commit_sha) as analyzer:
            repo_path = analyzer.clone()
            logger.info(f"Cloned repository to {repo_path}")

            # Step 4: Generate repo view
            publish_progress("generating_view", 35, "Generating repository view...")

            generator = RepoViewGenerator(repo_path)
            repo_view_result = generator.generate()

            logger.info(
                f"Generated repo view: {repo_view_result.token_estimate} tokens, "
                f"{repo_view_result.files_included} files"
            )

            # Step 5: Run broad scan with multiple models
            publish_progress("scanning", 50, f"Running AI scan with {len(models)} models...")

            # Lazy import to avoid fork-safety issues with LiteLLM
            from app.services.llm_gateway import get_llm_gateway

            llm_gateway = get_llm_gateway()
            broad_scan_agent = get_broad_scan_agent(llm_gateway, models)

            # Run async scan in sync context
            broad_scan_result = run_async(broad_scan_agent.scan(repo_view_result.content))

            logger.info(
                f"Broad scan completed: {len(broad_scan_result.candidates)} candidates, "
                f"{len(broad_scan_result.models_succeeded)}/{len(models)} models succeeded"
            )

            # Step 6: Merge and deduplicate issues
            publish_progress("merging", 75, "Merging and deduplicating issues...")

            merger = get_issue_merger()
            merged_issues = merger.merge(broad_scan_result.candidates)

            logger.info(f"Merged into {len(merged_issues)} unique issues")

            # Step 6.5: Investigate high-severity issues (optional)
            if investigate_severity:
                publish_progress("investigating", 80, "Investigating high-severity issues...")
                
                merged_issues = run_async(_investigate_issues(
                    merged_issues=merged_issues,
                    investigate_severity=investigate_severity,
                    max_issues=max_issues,
                    repo_path=repo_path,
                    llm_gateway=llm_gateway,
                    publish_progress=publish_progress,
                ))

        # Step 7: Build cache structure
        publish_progress("caching", 90, "Saving results...")

        # Convert merged issues to serializable format
        issues_data = []
        for issue in merged_issues:
            issues_data.append({
                "id": issue.id,
                "dimension": issue.dimension,
                "severity": issue.severity,
                "title": issue.title,
                "summary": issue.summary,
                "files": issue.files,
                "evidence_snippets": issue.evidence_snippets,
                "confidence": issue.confidence,
                "found_by_models": issue.found_by_models,
                "investigation_status": issue.investigation_status,
                "suggested_fix": issue.suggested_fix,
            })

        cache_data = {
            "status": "completed",
            "models_used": models,
            "models_succeeded": broad_scan_result.models_succeeded,
            "repo_overview": broad_scan_result.repo_overview,
            "issues": issues_data,
            "computed_at": datetime.now(timezone.utc).isoformat(),
            "total_tokens_used": broad_scan_result.total_tokens,
            "total_cost_usd": broad_scan_result.total_cost,
            "commit_sha": commit_sha,
        }

        # Step 8: Save to database via state service (Requirements 1.4)
        # Use AnalysisStateService for state transition: running -> completed
        _update_ai_scan_state(
            analysis_id=analysis_id,
            status="completed",
            cache_data=cache_data,
        )

        # Publish completion to Redis for real-time SSE updates
        publish_ai_scan_progress(
            analysis_id=analysis_id,
            stage="completed",
            progress=100,
            message=f"AI scan complete! Found {len(merged_issues)} issues.",
            status="completed",
        )

        logger.info(
            f"AI scan completed for analysis {analysis_id}: "
            f"{len(merged_issues)} issues, "
            f"{broad_scan_result.total_tokens} tokens, "
            f"${broad_scan_result.total_cost:.4f}"
        )

        return {
            "analysis_id": analysis_id,
            "commit_sha": commit_sha,
            "status": "completed",
            "issues_count": len(merged_issues),
            "models_used": models,
            "models_succeeded": broad_scan_result.models_succeeded,
            "total_tokens": broad_scan_result.total_tokens,
            "total_cost_usd": broad_scan_result.total_cost,
        }

    except Exception as e:
        error_msg = str(e)
        logger.error(f"AI scan failed for analysis {analysis_id}: {error_msg}")
        
        # Update PostgreSQL state via AnalysisStateService (primary source of truth)
        _update_ai_scan_state(
            analysis_id=analysis_id,
            status="failed",
            error=error_msg,
        )
        
        # Also publish to Redis for real-time SSE updates
        publish_ai_scan_progress(
            analysis_id=analysis_id,
            stage="failed",
            progress=0,
            message=error_msg[:200],
            status="failed",
        )
        
        self.update_state(state="FAILURE", meta={"error": error_msg})
        raise
