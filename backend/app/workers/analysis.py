"""Repository analysis tasks."""

import logging
import time
from datetime import datetime
from typing import Callable

from sqlalchemy import select

from app.core.celery import celery_app
from app.core.config import settings
from app.core.database import get_sync_session
from app.core.redis import publish_analysis_progress
from app.services.repo_analyzer import RepoAnalyzer
from app.workers.helpers import collect_files_for_embedding, get_repo_url

logger = logging.getLogger(__name__)

# Module-level state for heartbeat throttling (per-analysis tracking)
_last_heartbeat_times: dict[str, float] = {}


# Keep _get_repo_url as an alias for backward compatibility
def _get_repo_url(repository_id: str) -> tuple[str, str | None]:
    """Get repository URL and access token from database.

    DEPRECATED: Use get_repo_url from app.workers.helpers instead.
    This function is kept for backward compatibility.
    """
    return get_repo_url(repository_id)


def update_heartbeat(analysis_id: str, force: bool = False) -> bool:
    """Update the heartbeat timestamp for an analysis.
    
    Updates Analysis.state_updated_at to indicate the worker is still alive.
    Implements throttling to avoid database spam - updates at most once per
    settings.analysis_heartbeat_interval_seconds (default 30s).
    
    Args:
        analysis_id: UUID of the analysis to update
        force: If True, bypass throttling and always update
        
    Returns:
        True if heartbeat was updated, False if throttled
        
    Note:
        This function is idempotent and safe for retries.
        Uses module-level _last_heartbeat_times dict for throttling state.
    """
    from app.models.analysis import Analysis
    
    current_time = time.time()
    interval = settings.analysis_heartbeat_interval_seconds
    
    # Check throttling (unless forced)
    if not force:
        last_update = _last_heartbeat_times.get(analysis_id, 0)
        if current_time - last_update < interval:
            # Throttled - skip this update
            return False
    
    try:
        with get_sync_session() as db:
            result = db.execute(
                select(Analysis).where(Analysis.id == analysis_id)
            )
            analysis = result.scalar_one_or_none()
            
            if analysis:
                analysis.state_updated_at = datetime.utcnow()
                db.commit()
                
                # Update throttle tracking
                _last_heartbeat_times[analysis_id] = current_time
                logger.debug(f"Heartbeat updated for analysis {analysis_id}")
                return True
            else:
                logger.warning(f"Cannot update heartbeat: analysis {analysis_id} not found")
                return False
                
    except Exception as e:
        # Heartbeat failures should not crash the worker
        logger.warning(f"Failed to update heartbeat for analysis {analysis_id}: {e}")
        return False


def cleanup_heartbeat_tracking(analysis_id: str) -> None:
    """Remove heartbeat tracking state for a completed analysis.
    
    Should be called when an analysis completes or fails to prevent
    memory leaks in long-running workers.
    """
    _last_heartbeat_times.pop(analysis_id, None)


def create_heartbeat_callback(analysis_id: str) -> Callable[[], None]:
    """Create a heartbeat callback function for use in long operations.
    
    Returns a callable that can be passed to RepoAnalyzer or other
    long-running operations to periodically update the heartbeat.
    
    Args:
        analysis_id: UUID of the analysis
        
    Returns:
        A callable that updates the heartbeat when invoked
        
    Example:
        heartbeat = create_heartbeat_callback(analysis_id)
        with RepoAnalyzer(url, token, heartbeat_callback=heartbeat) as analyzer:
            result = analyzer.analyze()
    """
    def heartbeat():
        update_heartbeat(analysis_id)
    return heartbeat


def _mark_analysis_running(analysis_id: str):
    """Mark analysis as running and set started_at timestamp (A2).
    
    This should be called at the very beginning of analyze_repository,
    after input validation but before heavy operations.
    
    - Sets status="running"
    - Sets started_at only if it's still null (idempotency)
    - Sets state_updated_at for heartbeat (initial heartbeat)
    - Clears error_message on successful start (if this was a retry after fail)
    """
    from sqlalchemy import select

    from app.models.analysis import Analysis

    with get_sync_session() as db:
        result = db.execute(
            select(Analysis).where(Analysis.id == analysis_id)
        )
        analysis = result.scalar_one_or_none()

        if analysis:
            analysis.status = "running"
            # Only set started_at if it's still null (idempotency + correct duration calculation)
            if analysis.started_at is None:
                analysis.started_at = datetime.utcnow()
            # Update heartbeat timestamp (initial heartbeat on worker start)
            analysis.state_updated_at = datetime.utcnow()
            # Clear error_message on successful start (if this was a retry after fail)
            analysis.error_message = None
            db.commit()
            
            # Initialize heartbeat tracking for this analysis
            _last_heartbeat_times[analysis_id] = time.time()
            logger.info(f"Marked analysis {analysis.id} as running (initial heartbeat set)")
        else:
            logger.warning(f"No analysis found with id {analysis_id}")


def _save_analysis_results(repository_id: str, analysis_id: str, result):
    """Save analysis results to database."""
    from sqlalchemy import update

    from app.models.analysis import Analysis
    from app.models.issue import Issue
    from app.models.repository import Repository

    with get_sync_session() as db:
        # Find the specific analysis by ID
        analysis_result = db.execute(
            select(Analysis).where(Analysis.id == analysis_id)
        )
        analysis = analysis_result.scalar_one_or_none()

        if analysis:
            analysis.status = "completed"
            analysis.vci_score = result.vci_score
            analysis.tech_debt_level = result.tech_debt_level
            analysis.metrics = result.metrics
            analysis.ai_report = result.ai_report
            # A3: Do NOT overwrite started_at - it should be set by _mark_analysis_running
            # Defensive fallback: if started_at is still null (legacy records/rare race), set it now
            if analysis.started_at is None:
                analysis.started_at = datetime.utcnow()
            analysis.completed_at = datetime.utcnow()
            # Final heartbeat update on completion
            analysis.state_updated_at = datetime.utcnow()

            # Close old open issues for this repository (to avoid duplicates)
            # Important: Don't close issues from the current analysis (race condition protection)
            # This prevents issues from being lost if two analyses somehow run in parallel
            db.execute(
                update(Issue)
                .where(
                    Issue.repository_id == repository_id,
                    Issue.status == "open",
                    Issue.analysis_id != analysis.id,  # Don't close issues from current analysis
                )
                .values(status="closed")
            )

            # Create new issues from this analysis
            for issue_data in result.issues:
                issue = Issue(
                    repository_id=repository_id,
                    analysis_id=analysis.id,
                    type=issue_data["type"],
                    severity=issue_data["severity"],
                    title=issue_data["title"],
                    description=issue_data["description"],
                    confidence=issue_data.get("confidence", 0.8),
                    status="open",
                )
                db.add(issue)

            # Update repository
            repo_result = db.execute(
                select(Repository).where(Repository.id == repository_id)
            )
            repo = repo_result.scalar_one_or_none()
            if repo:
                repo.vci_score = result.vci_score
                repo.tech_debt_level = result.tech_debt_level
                repo.last_analysis_at = datetime.utcnow()

            db.commit()
            logger.info(f"Saved analysis {analysis.id} with VCI score {result.vci_score}")
            
            # Cleanup heartbeat tracking to prevent memory leaks
            cleanup_heartbeat_tracking(analysis_id)
        else:
            logger.warning(f"No pending analysis found for repository {repository_id}")


def _mark_analysis_failed(analysis_id: str, error_message: str):
    """Mark analysis as failed."""
    from app.models.analysis import Analysis

    with get_sync_session() as db:
        result = db.execute(
            select(Analysis).where(Analysis.id == analysis_id)
        )
        analysis = result.scalar_one_or_none()

        if analysis:
            analysis.status = "failed"
            analysis.error_message = error_message[:500]  # Limit error message length
            # A4: Do NOT touch started_at, except for fallback (if null — set started_at=now)
            if analysis.started_at is None:
                analysis.started_at = datetime.utcnow()
            analysis.completed_at = datetime.utcnow()
            # Final heartbeat update on failure
            analysis.state_updated_at = datetime.utcnow()
            db.commit()
            logger.info(f"Marked analysis {analysis.id} as failed")

            # Publish failure to Redis for SSE
            publish_analysis_progress(
                analysis_id=analysis_id,
                stage="failed",
                progress=0,
                message=error_message[:200],
                status="failed",
            )
            
            # Cleanup heartbeat tracking to prevent memory leaks
            cleanup_heartbeat_tracking(analysis_id)


def _collect_files_for_embedding(repo_path) -> list[dict]:
    """Collect code files from repository for embedding generation.

    DEPRECATED: Use collect_files_for_embedding from app.workers.helpers instead.
    This function is kept for backward compatibility.

    Args:
        repo_path: Path to the cloned repository

    Returns:
        List of {path: str, content: str} dicts
    """
    return collect_files_for_embedding(repo_path)


@celery_app.task(bind=True, name="app.workers.analysis.analyze_repository")
def analyze_repository(
    self,
    repository_id: str,
    analysis_id: str,
    commit_sha: str | None = None,
    triggered_by: str = "manual",
) -> dict:
    """
    Analyze a repository and calculate VCI score.

    This task clones the repository, runs static analysis,
    calculates metrics, and generates a VCI score.

    Progress is published to Redis Pub/Sub for real-time SSE updates.
    Heartbeat updates are sent to the database to indicate the worker is alive.
    """
    logger.info(
        f"Starting analysis {analysis_id} for repository {repository_id}, "
        f"commit={commit_sha}, triggered_by={triggered_by}"
    )

    # A2: Mark analysis as running immediately (pending→running transition)
    # This sets status="running", started_at (if null), state_updated_at, and clears error_message
    _mark_analysis_running(analysis_id)

    # Create heartbeat callback for long operations in RepoAnalyzer
    heartbeat_callback = create_heartbeat_callback(analysis_id)

    def publish_progress(stage: str, progress: int, message: str | None = None):
        """Helper to publish progress updates and update heartbeat."""
        # Publish to Redis for SSE
        publish_analysis_progress(
            analysis_id=analysis_id,
            stage=stage,
            progress=progress,
            message=message,
            status="running",
        )
        self.update_state(state="PROGRESS", meta={"stage": stage, "progress": progress})
        
        # Update heartbeat in database (throttled to avoid DB spam)
        update_heartbeat(analysis_id)

    try:
        # Step 1: Get repository URL
        publish_progress("initializing", 5, "Initializing analysis...")
        repo_url, access_token = _get_repo_url(repository_id)
        logger.info(f"Repository URL: {repo_url}")

        # Step 2: Clone repository
        publish_progress("cloning", 15, "Cloning repository...")

        with RepoAnalyzer(
            repo_url, 
            access_token, 
            commit_sha=commit_sha,
            heartbeat_callback=heartbeat_callback,
        ) as analyzer:
            # Clone complete
            publish_progress("cloning", 25, "Repository cloned successfully")

            # Count lines
            publish_progress("counting_lines", 40, "Counting lines of code...")

            # Complexity analysis
            publish_progress("analyzing_complexity", 55, "Analyzing code complexity...")

            # Run static analysis
            publish_progress("static_analysis", 70, "Running static analysis tools...")

            # Calculate VCI
            publish_progress("calculating_vci", 85, "Calculating VCI score...")

            # Full analysis (heartbeat_callback will be called during long operations)
            result = analyzer.analyze()

        # Step 3: Save results (after context manager exits, temp dir is cleaned)
        # Note: Embeddings are now generated in parallel via generate_embeddings_parallel task
        publish_progress("saving_results", 95, "Saving results...")
        _save_analysis_results(repository_id, analysis_id, result)

        # Note: Embeddings are now dispatched in parallel from the API endpoint
        # (generate_embeddings_parallel task), not from this worker.
        # This enables true parallel execution of Static Analysis, Embeddings, and AI Scan.

        # Publish completion with VCI score and commit_sha
        publish_analysis_progress(
            analysis_id=analysis_id,
            stage="completed",
            progress=100,
            message=f"Analysis complete! VCI Score: {result.vci_score}",
            status="completed",
            vci_score=result.vci_score,
            commit_sha=commit_sha,
        )

        logger.info(f"Analysis {analysis_id} completed for repository {repository_id}, VCI: {result.vci_score}")

        return {
            "repository_id": repository_id,
            "analysis_id": analysis_id,
            "commit_sha": commit_sha,
            "vci_score": result.vci_score,
            "tech_debt_level": result.tech_debt_level,
            "metrics": result.metrics,
            "issues_count": len(result.issues),
            "status": "completed",
        }

    except Exception as e:
        error_msg = str(e)
        logger.error(f"Analysis {analysis_id} failed for repository {repository_id}: {error_msg}")
        _mark_analysis_failed(analysis_id, error_msg)
        self.update_state(state="FAILURE", meta={"error": error_msg})
        raise


@celery_app.task(name="app.workers.analysis.run_quick_scan")
def run_quick_scan(repo_url: str) -> dict:
    """
    Run a quick VCI scan for playground (public repos).

    Args:
        repo_url: GitHub repository URL

    Returns:
        dict with quick scan results
    """
    logger.info(f"Running quick scan for {repo_url}")

    try:
        with RepoAnalyzer(repo_url) as analyzer:
            result = analyzer.analyze()

        return {
            "repo_url": repo_url,
            "vci_score": result.vci_score,
            "tech_debt_level": result.tech_debt_level,
            "metrics": result.metrics,
            "top_issues": result.issues[:5],  # Top 5 issues
            "status": "completed",
        }

    except Exception as e:
        logger.error(f"Quick scan failed for {repo_url}: {e}")
        return {
            "repo_url": repo_url,
            "status": "failed",
            "error": str(e),
        }


@celery_app.task(name="app.workers.analysis.run_cluster_analysis")
def run_cluster_analysis(repository_id: str) -> dict:
    """
    Run cluster analysis on repository embeddings.

    This task analyzes the vector embeddings for a repository,
    performs HDBSCAN clustering, and updates cluster_id in Qdrant.

    Should be run after embeddings are generated.

    Args:
        repository_id: UUID of the repository

    Returns:
        dict with cluster analysis results
    """
    import asyncio

    logger.info(f"Running cluster analysis for repository {repository_id}")

    try:
        from app.services.cluster_analyzer import get_cluster_analyzer
        from app.workers.embeddings import get_qdrant_client

        # Run async analyzer in sync context
        def run_async(coro):
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            return loop.run_until_complete(coro)

        analyzer = get_cluster_analyzer()
        health = run_async(analyzer.analyze(repository_id))

        # Update cluster_id in Qdrant for each chunk
        if health.clusters:
            get_qdrant_client()

            # Build cluster mapping from file paths
            file_to_cluster = {}
            for cluster in health.clusters:
                for file_path in cluster.top_files:
                    file_to_cluster[file_path] = cluster.id

            # Update points with cluster_id
            # Note: This is a simplified approach - in production,
            # you'd want to update based on the actual clustering results
            logger.info(f"Cluster analysis complete: {len(health.clusters)} clusters found")

        return {
            "repository_id": repository_id,
            "overall_score": health.overall_score,
            "cluster_count": len(health.clusters),
            "outlier_count": len(health.outliers),
            "total_chunks": health.total_chunks,
            "total_files": health.total_files,
            "metrics": health.metrics,
            "status": "completed",
        }

    except Exception as e:
        logger.error(f"Cluster analysis failed for {repository_id}: {e}")
        return {
            "repository_id": repository_id,
            "status": "failed",
            "error": str(e),
        }
