"""Analysis API endpoints."""

import asyncio
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import CurrentUser, DbSession
from app.core.config import settings
from app.core.redis import publish_analysis_progress, subscribe_analysis_progress
from app.models.analysis import Analysis
from app.models.issue import Issue
from app.models.repository import Repository
from app.schemas.analysis import (
    AIScanStatus,
    AnalysisFullStatusResponse,
    EmbeddingsStatus,
    SemanticCacheStatus,
    compute_is_complete_parallel,
    compute_overall_progress_parallel,
    compute_overall_stage_parallel,
)
from app.workers.ai_scan import run_ai_scan
from app.workers.analysis import analyze_repository
from app.workers.embeddings import generate_embeddings_parallel

router = APIRouter()


@router.get("/repositories/{repository_id}/analyses")
async def list_analyses(
    repository_id: UUID,
    db: DbSession,
    user: CurrentUser,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> dict:
    """
    List all analyses for a repository.
    """
    # Verify repository access
    result = await db.execute(
        select(Repository).where(
            Repository.id == repository_id,
            Repository.owner_id == user.id,
        )
    )
    repository = result.scalar_one_or_none()

    if not repository:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Repository not found",
        )

    # Get analyses
    result = await db.execute(
        select(Analysis)
        .where(Analysis.repository_id == repository_id)
        .order_by(Analysis.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    analyses = result.scalars().all()

    # Get total count
    from sqlalchemy import func
    count_result = await db.execute(
        select(func.count(Analysis.id))
        .where(Analysis.repository_id == repository_id)
    )
    total = count_result.scalar()

    return {
        "data": [
            {
                "id": str(a.id),
                "repository_id": str(a.repository_id),
                "commit_sha": a.commit_sha,
                "branch": a.branch,
                "status": a.status,
                "vci_score": float(a.vci_score) if a.vci_score is not None else None,
                "grade": a.grade,
                "tech_debt_level": a.tech_debt_level,
                "metrics": a.metrics or {},  # Include raw metrics!
                "ai_report": a.ai_report,
                "started_at": a.started_at.isoformat() if a.started_at else None,
                "completed_at": a.completed_at.isoformat() if a.completed_at else None,
                "created_at": a.created_at.isoformat(),
            }
            for a in analyses
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


class TriggerAnalysisRequest(BaseModel):
    """Request body for triggering analysis."""
    branch: str | None = None
    commit_sha: str | None = None


@router.post("/repositories/{repository_id}/analyses", status_code=status.HTTP_202_ACCEPTED)
async def trigger_analysis(
    repository_id: UUID,
    db: DbSession,
    user: CurrentUser,
    body: TriggerAnalysisRequest | None = None,
) -> dict:
    """
    Trigger a new analysis for a repository.
    """
    from app.core.encryption import decrypt_token_or_none
    from app.services.github import GitHubService

    # Extract parameters from body
    branch = body.branch if body else None
    commit_sha = body.commit_sha if body else None

    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"trigger_analysis called: repo={repository_id}, branch={branch}, commit_sha={commit_sha}")

    # Verify repository access
    result = await db.execute(
        select(Repository).where(
            Repository.id == repository_id,
            Repository.owner_id == user.id,
        )
    )
    repository = result.scalar_one_or_none()

    if not repository:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Repository not found",
        )

    if not repository.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Repository is not active",
        )

    # Get real commit SHA if not provided
    target_branch = branch or repository.default_branch
    if not commit_sha:
        github_token = decrypt_token_or_none(user.access_token_encrypted)
        if github_token:
            try:
                github = GitHubService(github_token)
                owner, repo_name = repository.full_name.split("/")
                branch_info = await github.get_branch(owner, repo_name, target_branch)
                commit_sha = branch_info.get("commit", {}).get("sha")
            except Exception:
                pass  # Fall back to HEAD if GitHub API fails

        if not commit_sha:
            commit_sha = "HEAD"

    # Atomic-ish duplicate check with row locking to prevent race conditions.
    #
    # Design intent: serialize "trigger analysis" per repository.
    # Implementation change: lock ONLY the repository row (NOWAIT) and do a normal read
    # of pending/running analyses. Locking the analyses rows with NOWAIT can cause
    # spurious 409s and increases deadlock risk.
    from datetime import timedelta

    from sqlalchemy.exc import OperationalError

    now = datetime.now()
    stuck_threshold = now - timedelta(minutes=5)

    try:
        await db.execute(
            select(Repository)
            .where(Repository.id == repository_id)
            .with_for_update(nowait=True)
        )
    except OperationalError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Another analysis request is being processed. Please try again.",
        )

    # With the repository row locked, this read is serialized for this repository.
    result = await db.execute(
        select(Analysis).where(
            Analysis.repository_id == repository_id,
            Analysis.status.in_(["pending", "running"]),
        )
    )
    existing_analyses = result.scalars().all()

    for existing in existing_analyses:
        # If analysis is older than 5 minutes, mark as failed
        if existing.created_at.replace(tzinfo=None) < stuck_threshold:
            existing.status = "failed"
            existing.error_message = "Analysis timed out (auto-cleaned)"
        else:
            # Recent analysis still in progress - release locks and reject
            await db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Analysis already in progress",
            )

    # Create analysis record with ALL statuses pending (Requirements 1.2)
    # This enables parallel execution of all three tracks
    analysis = Analysis(
        repository_id=repository_id,
        commit_sha=commit_sha,
        branch=target_branch,
        status="pending",
        embeddings_status="pending",  # Set pending immediately for parallel execution
        ai_scan_status="pending" if settings.ai_scan_enabled else "skipped",  # Skip if disabled
    )
    db.add(analysis)

    # Single commit: updates stuck analyses + creates new one atomically
    await db.commit()
    await db.refresh(analysis)

    # Dispatch ALL tasks in parallel (Requirements 1.1, 1.4)
    # Task 1: Static Analysis (VCI calculation)
    task = analyze_repository.delay(
        repository_id=str(repository_id),
        analysis_id=str(analysis.id),
        commit_sha=commit_sha,
        triggered_by="manual",
    )

    # Task 2: Embeddings (independent clone) - Requirements 5.1
    generate_embeddings_parallel.delay(
        repository_id=str(repository_id),
        analysis_id=str(analysis.id),
        commit_sha=commit_sha,
    )

    # Task 3: AI Scan (independent clone) - Requirements 1.4
    if settings.ai_scan_enabled:
        run_ai_scan.delay(analysis_id=str(analysis.id))

    # Publish initial status to Redis for SSE clients that connect immediately
    publish_analysis_progress(
        analysis_id=str(analysis.id),
        stage="queued",
        progress=0,
        message="Analysis queued, waiting for worker...",
        status="pending",
    )

    return {
        "id": str(analysis.id),
        "repository_id": str(repository_id),
        "status": "pending",
        "task_id": task.id,
        "message": "Analysis queued successfully",
    }


@router.get("/analyses/{analysis_id}/stream")
async def stream_analysis_progress(
    analysis_id: UUID,
    db: DbSession,
    user: CurrentUser,
):
    """
    Stream analysis progress via Server-Sent Events (SSE).

    This endpoint provides real-time updates on analysis progress.
    Connect to this endpoint after triggering an analysis to receive
    live progress updates without polling.

    Events format:
    ```
    data: {"analysis_id": "...", "stage": "cloning", "progress": 25, "message": "...", "status": "running"}
    ```

    Final event will have status: "completed" or "failed"
    """
    # Verify analysis exists and user has access
    result = await db.execute(
        select(Analysis)
        .options(selectinload(Analysis.repository))
        .where(Analysis.id == analysis_id)
    )
    analysis = result.scalar_one_or_none()

    if not analysis:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Analysis not found",
        )

    # Verify access
    if analysis.repository.owner_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )

    # If analysis is already completed or failed, return current status immediately
    if analysis.status in ("completed", "failed"):
        async def completed_stream():
            import json
            data = json.dumps({
                "analysis_id": str(analysis_id),
                "stage": analysis.status,
                "progress": 100 if analysis.status == "completed" else 0,
                "message": analysis.error_message if analysis.status == "failed" else "Analysis complete",
                "status": analysis.status,
                "vci_score": float(analysis.vci_score) if analysis.vci_score else None,
            })
            yield f"data: {data}\n\n"

        return StreamingResponse(
            completed_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    async def event_generator():
        """Generate SSE events from Redis Pub/Sub.

        First sends the last known state (if any) to catch up late subscribers,
        then streams real-time updates from Redis Pub/Sub.
        """
        import json as json_module

        from app.core.redis import get_analysis_last_state

        try:
            # 1. Send last known state immediately (for late subscribers)
            last_state = await get_analysis_last_state(str(analysis_id))
            if last_state:
                yield f"data: {last_state}\n\n"

                # Check if already finished
                try:
                    state_data = json_module.loads(last_state)
                    if state_data.get("status") in ("completed", "failed"):
                        return  # Already done, no need to subscribe
                except json_module.JSONDecodeError:
                    pass
            else:
                # No state yet, send initial "connecting" message
                initial_data = json_module.dumps({
                    "analysis_id": str(analysis_id),
                    "stage": "queued",
                    "progress": 0,
                    "message": "Connected, waiting for worker...",
                    "status": "pending",
                })
                yield f"data: {initial_data}\n\n"

            # 2. Subscribe to real-time updates
            async for data in subscribe_analysis_progress(str(analysis_id)):
                yield f"data: {data}\n\n"

        except asyncio.CancelledError:
            # Client disconnected
            pass
        except Exception as e:
            # Streaming transport error (Redis/network/etc). Do NOT mark the analysis as failed.
            # Emit a non-terminal "error" event so the client can retry.
            import json
            error_data = json.dumps({
                "analysis_id": str(analysis_id),
                "stage": "error",
                "progress": 0,
                "message": f"Stream error: {str(e)}",
                "status": "error",
            })
            yield f"data: {error_data}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )


@router.delete("/analyses/{analysis_id}")
async def delete_analysis(
    analysis_id: UUID,
    db: DbSession,
    user: CurrentUser,
) -> dict:
    """
    Delete an analysis (only pending/failed ones).
    """
    # Get analysis with repository
    result = await db.execute(
        select(Analysis)
        .options(selectinload(Analysis.repository))
        .where(Analysis.id == analysis_id)
    )
    analysis = result.scalar_one_or_none()

    if not analysis:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Analysis not found",
        )

    # Verify access
    if analysis.repository.owner_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )

    # Only allow deleting pending/failed analyses
    if analysis.status not in ["pending", "failed", "running"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete completed analysis",
        )

    await db.delete(analysis)
    await db.commit()

    return {"message": "Analysis deleted", "id": str(analysis_id)}


@router.get("/analyses/{analysis_id}")
async def get_analysis(
    analysis_id: UUID,
    db: DbSession,
    user: CurrentUser,
) -> dict:
    """
    Get detailed analysis results.
    """
    # Get analysis with repository
    result = await db.execute(
        select(Analysis)
        .options(selectinload(Analysis.repository))
        .where(Analysis.id == analysis_id)
    )
    analysis = result.scalar_one_or_none()

    if not analysis:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Analysis not found",
        )

    # Verify access
    if analysis.repository.owner_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )

    # Get issues for this analysis
    issues_result = await db.execute(
        select(Issue)
        .where(Issue.analysis_id == analysis_id)
        .order_by(Issue.severity.desc(), Issue.confidence.desc())
    )
    issues = issues_result.scalars().all()

    return {
        "id": str(analysis.id),
        "repository_id": str(analysis.repository_id),
        "repository_name": analysis.repository.full_name,
        "commit_sha": analysis.commit_sha,
        "branch": analysis.branch,
        "status": analysis.status,
        "vci_score": float(analysis.vci_score) if analysis.vci_score is not None else None,
        "grade": analysis.grade,
        "metrics": analysis.metrics or {},
        "ai_report": analysis.ai_report,
        "started_at": analysis.started_at.isoformat() if analysis.started_at else None,
        "completed_at": analysis.completed_at.isoformat() if analysis.completed_at else None,
        "duration_seconds": (
            (analysis.completed_at - analysis.started_at).total_seconds()
            if analysis.completed_at and analysis.started_at
            else None
        ),
        "created_at": analysis.created_at.isoformat(),
        "issues": [
            {
                "id": str(issue.id),
                "type": issue.type,
                "severity": issue.severity,
                "title": issue.title,
                "description": issue.description,
                "file_path": issue.file_path,
                "line_start": issue.line_start,
                "line_end": issue.line_end,
                "confidence": issue.confidence,
                "status": issue.status,
                "auto_fixable": issue.auto_fixable,
            }
            for issue in issues
        ],
        "issues_count": {
            "total": len(issues),
            "high": sum(1 for i in issues if i.severity == "high"),
            "medium": sum(1 for i in issues if i.severity == "medium"),
            "low": sum(1 for i in issues if i.severity == "low"),
        },
    }


@router.get("/analyses/{analysis_id}/full-status", response_model=AnalysisFullStatusResponse)
async def get_analysis_full_status(
    analysis_id: UUID,
    db: DbSession,
    user: CurrentUser,
) -> AnalysisFullStatusResponse:
    """
    Get full analysis status including embeddings, semantic cache, and AI scan state.

    This endpoint provides a single source of truth for all analysis state,
    enabling simplified frontend polling with computed overall progress.
    PostgreSQL is the single source of truth - no Redis fallback.

    Returns:
        AnalysisFullStatusResponse with all status fields and computed progress

    **Feature: progress-tracking-refactor, ai-scan-progress-fix**
    **Property 10: PostgreSQL as Single Source of Truth**
    **Validates: Requirements 1.3, 2.3, 4.1, 4.2, 4.3, 4.4**
    """
    # Single database query to fetch analysis with repository (Requirements 1.3)
    # PostgreSQL is the single source of truth (Property 10)
    result = await db.execute(
        select(Analysis)
        .options(selectinload(Analysis.repository))
        .where(Analysis.id == analysis_id)
    )
    analysis = result.scalar_one_or_none()

    # Return 404 for non-existent analysis (don't leak existence for unauthorized)
    if not analysis:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Analysis not found",
        )

    # Verify access - return 404 to not leak existence
    if analysis.repository.owner_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Analysis not found",
        )

    # Derive analysis_progress from status (static analysis doesn't track granular progress)
    # pending=0, running=50, completed/failed=100
    # **Feature: parallel-analysis-pipeline**
    # **Validates: Requirements 2.1**
    if analysis.status == "pending":
        analysis_progress = 0
    elif analysis.status == "running":
        analysis_progress = 50  # Mid-point since static analysis doesn't track progress
    else:  # completed, failed
        analysis_progress = 100

    # Compute overall progress using parallel calculation (Requirements 2.1, 2.2, 2.3, 2.4)
    # **Feature: parallel-analysis-pipeline**
    overall_progress = compute_overall_progress_parallel(
        analysis_status=analysis.status,
        analysis_progress=analysis_progress,
        embeddings_status=analysis.embeddings_status,
        embeddings_progress=analysis.embeddings_progress,
        semantic_cache_status=analysis.semantic_cache_status,
        ai_scan_status=analysis.ai_scan_status,
        ai_scan_progress=analysis.ai_scan_progress,
    )

    # Compute overall stage using parallel calculation (Requirements 3.1, 3.2, 3.3)
    # **Feature: parallel-analysis-pipeline**
    overall_stage = compute_overall_stage_parallel(
        analysis_status=analysis.status,
        embeddings_status=analysis.embeddings_status,
        embeddings_stage=analysis.embeddings_stage,
        semantic_cache_status=analysis.semantic_cache_status,
        ai_scan_status=analysis.ai_scan_status,
        ai_scan_stage=analysis.ai_scan_stage,
    )

    # Compute is_complete flag using parallel calculation (Requirements 4.1, 4.2, 4.3, 4.4)
    # **Feature: parallel-analysis-pipeline**
    is_complete = compute_is_complete_parallel(
        analysis_status=analysis.status,
        embeddings_status=analysis.embeddings_status,
        semantic_cache_status=analysis.semantic_cache_status,
        ai_scan_status=analysis.ai_scan_status,
    )

    # Determine if semantic cache exists
    has_semantic_cache = (
        analysis.semantic_cache is not None
        and analysis.semantic_cache.get("architecture_health") is not None
    )

    # Determine if AI scan cache exists (Requirements 2.3)
    has_ai_scan_cache = (
        analysis.ai_scan_cache is not None
        and analysis.ai_scan_cache.get("issues") is not None
    )

    return AnalysisFullStatusResponse(
        # Identity
        analysis_id=str(analysis.id),
        repository_id=str(analysis.repository_id),
        commit_sha=analysis.commit_sha,
        # Analysis status (Requirements 2.1)
        # **Feature: parallel-analysis-pipeline**
        analysis_status=analysis.status,
        analysis_progress=analysis_progress,  # NEW: Track static analysis progress separately
        vci_score=float(analysis.vci_score) if analysis.vci_score is not None else None,
        grade=analysis.grade,
        # Embeddings status
        embeddings_status=EmbeddingsStatus(analysis.embeddings_status),
        embeddings_progress=analysis.embeddings_progress,
        embeddings_stage=analysis.embeddings_stage,
        embeddings_message=analysis.embeddings_message,
        embeddings_error=analysis.embeddings_error,
        vectors_count=analysis.vectors_count,
        # Semantic cache status
        semantic_cache_status=SemanticCacheStatus(analysis.semantic_cache_status),
        has_semantic_cache=has_semantic_cache,
        # AI scan status (Requirements 2.3)
        ai_scan_status=AIScanStatus(analysis.ai_scan_status),
        ai_scan_progress=analysis.ai_scan_progress,
        ai_scan_stage=analysis.ai_scan_stage,
        ai_scan_message=analysis.ai_scan_message,
        ai_scan_error=analysis.ai_scan_error,
        has_ai_scan_cache=has_ai_scan_cache,
        ai_scan_started_at=analysis.ai_scan_started_at,
        ai_scan_completed_at=analysis.ai_scan_completed_at,
        # Timestamps
        state_updated_at=analysis.state_updated_at,
        embeddings_started_at=analysis.embeddings_started_at,
        embeddings_completed_at=analysis.embeddings_completed_at,
        # Computed fields
        overall_progress=overall_progress,
        overall_stage=overall_stage,
        is_complete=is_complete,
    )


@router.get("/analyses/{analysis_id}/metrics")
async def get_analysis_metrics(
    analysis_id: UUID,
    db: DbSession,
    user: CurrentUser,
) -> dict:
    """
    Get detailed metrics for an analysis.
    """
    # Get analysis
    result = await db.execute(
        select(Analysis)
        .options(selectinload(Analysis.repository))
        .where(Analysis.id == analysis_id)
    )
    analysis = result.scalar_one_or_none()

    if not analysis:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Analysis not found",
        )

    # Verify access
    if analysis.repository.owner_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )

    metrics = analysis.metrics or {}

    return {
        "analysis_id": str(analysis_id),
        "vci_score": float(analysis.vci_score) if analysis.vci_score is not None else None,
        "grade": analysis.grade,
        "breakdown": {
            "complexity": {
                "score": metrics.get("complexity_score", 0),
                "weight": 0.25,
                "details": metrics.get("complexity_details", {}),
            },
            "duplication": {
                "score": metrics.get("duplication_score", 0),
                "weight": 0.25,
                "details": metrics.get("duplication_details", {}),
            },
            "maintainability": {
                "score": metrics.get("maintainability_score", 0),
                "weight": 0.30,
                "details": metrics.get("maintainability_details", {}),
            },
            "architecture": {
                "score": metrics.get("architecture_score", 0),
                "weight": 0.20,
                "details": metrics.get("architecture_details", {}),
            },
        },
        "code_stats": {
            "total_files": metrics.get("total_files", 0),
            "total_lines": metrics.get("total_lines", 0),
            "python_lines": metrics.get("python_lines", 0),
            "javascript_lines": metrics.get("javascript_lines", 0),
            "test_coverage": metrics.get("test_coverage", 0),
        },
    }


@router.get("/repositories/{repository_id}/vci-history")
async def get_vci_history(
    repository_id: UUID,
    db: DbSession,
    user: CurrentUser,
    limit: int = Query(30, ge=1, le=100),
) -> dict:
    """
    Get VCI score history for a repository.
    """
    # Verify repository access
    result = await db.execute(
        select(Repository).where(
            Repository.id == repository_id,
            Repository.owner_id == user.id,
        )
    )
    repository = result.scalar_one_or_none()

    if not repository:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Repository not found",
        )

    # Get completed analyses
    result = await db.execute(
        select(Analysis)
        .where(
            Analysis.repository_id == repository_id,
            Analysis.status == "completed",
            Analysis.vci_score.isnot(None),
        )
        .order_by(Analysis.completed_at.desc())
        .limit(limit)
    )
    analyses = result.scalars().all()

    # Reverse for chronological order
    analyses = list(reversed(analyses))

    return {
        "repository_id": str(repository_id),
        "data_points": [
            {
                "date": a.completed_at.isoformat() if a.completed_at else a.created_at.isoformat(),
                "vci_score": float(a.vci_score) if a.vci_score is not None else None,
                "grade": a.grade,
                "commit_sha": a.commit_sha[:7] if a.commit_sha else None,
            }
            for a in analyses
        ],
        "trend": _calculate_trend(analyses) if len(analyses) >= 2 else "stable",
        "current_score": float(analyses[-1].vci_score) if analyses and analyses[-1].vci_score is not None else None,
        "previous_score": float(analyses[-2].vci_score) if len(analyses) >= 2 and analyses[-2].vci_score is not None else None,
    }


def _calculate_trend(analyses: list) -> str:
    """Calculate VCI trend from recent analyses."""
    if len(analyses) < 2:
        return "stable"

    recent = analyses[-3:]  # Last 3 analyses
    if len(recent) < 2:
        return "stable"

    first_score = recent[0].vci_score
    last_score = recent[-1].vci_score

    # Handle None scores
    if first_score is None or last_score is None:
        return "stable"

    diff = float(last_score) - float(first_score)

    if diff > 5:
        return "improving"
    elif diff < -5:
        return "declining"
    return "stable"


# =============================================================================
# Semantic Cache Endpoints
# =============================================================================


@router.get("/analyses/{analysis_id}/semantic")
async def get_semantic_cache(
    analysis_id: UUID,
    db: DbSession,
    user: CurrentUser,
) -> dict:
    """
    Get cached semantic analysis data for an analysis.

    Returns cached architecture health, clusters, outliers from PostgreSQL.
    If cache is missing, returns is_cached: false with null fields.
    """

    # Get analysis with repository
    result = await db.execute(
        select(Analysis)
        .options(selectinload(Analysis.repository))
        .where(Analysis.id == analysis_id)
    )
    analysis = result.scalar_one_or_none()

    if not analysis:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Analysis not found",
        )

    # Verify access
    if analysis.repository.owner_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )

    # Check if semantic cache exists
    cache = analysis.semantic_cache

    if cache and cache.get("architecture_health"):
        return {
            "analysis_id": str(analysis.id),
            "commit_sha": analysis.commit_sha,
            "architecture_health": cache.get("architecture_health"),
            "similar_code": cache.get("similar_code"),
            "computed_at": cache.get("computed_at"),
            "is_cached": True,
        }

    # No cache - return empty response
    return {
        "analysis_id": str(analysis.id),
        "commit_sha": analysis.commit_sha,
        "architecture_health": None,
        "similar_code": None,
        "computed_at": None,
        "is_cached": False,
    }


@router.post("/analyses/{analysis_id}/semantic/generate")
async def generate_semantic_cache(
    analysis_id: UUID,
    db: DbSession,
    user: CurrentUser,
) -> dict:
    """
    Generate and cache semantic analysis for an analysis.

    Computes architecture health using ClusterAnalyzer and stores
    results in the semantic_cache column.
    """

    from app.services.cluster_analyzer import ClusterAnalyzer

    # Get analysis with repository
    result = await db.execute(
        select(Analysis)
        .options(selectinload(Analysis.repository))
        .where(Analysis.id == analysis_id)
    )
    analysis = result.scalar_one_or_none()

    if not analysis:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Analysis not found",
        )

    # Verify access
    if analysis.repository.owner_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )

    # Check if analysis is completed
    if analysis.status != "completed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Analysis must be completed before generating semantic cache",
        )

    try:
        # Compute semantic analysis using ClusterAnalyzer (commit-aware)
        analyzer = ClusterAnalyzer()
        health = await analyzer.analyze(
            str(analysis.repository_id),
            commit_sha=analysis.commit_sha,  # Pass commit_sha for commit-aware filtering
        )

        # Convert to JSON-serializable dict using the built-in method
        cache_data = health.to_cacheable_dict()

        # Store in semantic_cache column
        analysis.semantic_cache = cache_data

        await db.commit()
        await db.refresh(analysis)

        return {
            "analysis_id": str(analysis.id),
            "commit_sha": analysis.commit_sha,
            "architecture_health": cache_data.get("architecture_health"),
            "similar_code": cache_data.get("similar_code"),
            "computed_at": cache_data.get("computed_at"),
            "is_cached": True,
        }

    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Failed to generate semantic cache: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate semantic analysis: {str(e)}",
        )
