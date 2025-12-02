"""Analysis API endpoints."""

import asyncio
from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import CurrentUser, DbSession
from app.core.redis import subscribe_analysis_progress, publish_analysis_progress
from app.models.analysis import Analysis
from app.models.issue import Issue
from app.models.repository import Repository
from app.workers.analysis import analyze_repository

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
                "vci_score": a.vci_score,
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


@router.post("/repositories/{repository_id}/analyses", status_code=status.HTTP_202_ACCEPTED)
async def trigger_analysis(
    repository_id: UUID,
    db: DbSession,
    user: CurrentUser,
    branch: Optional[str] = None,
    commit_sha: Optional[str] = None,
) -> dict:
    """
    Trigger a new analysis for a repository.
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
    
    if not repository.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Repository is not active",
        )
    
    # Atomic duplicate check with row locking to prevent race conditions.
    # Uses FOR UPDATE NOWAIT to lock the repository row while checking for existing analyses.
    # This prevents two concurrent requests from both passing the check.
    from datetime import timedelta
    from sqlalchemy import and_
    from sqlalchemy.exc import OperationalError
    
    now = datetime.now()
    stuck_threshold = now - timedelta(minutes=5)
    
    try:
        # Lock the repository row to serialize concurrent analysis requests
        # NOWAIT ensures we fail fast if another request holds the lock
        await db.execute(
            select(Repository)
            .where(Repository.id == repository_id)
            .with_for_update(nowait=True)
        )
    
        # Now safely check for existing analyses (other requests are blocked)
        result = await db.execute(
            select(Analysis)
            .where(
                Analysis.repository_id == repository_id,
                Analysis.status.in_(["pending", "running"]),
            )
            .with_for_update(nowait=True)  # Also lock any existing analyses we find
        )
    except OperationalError:
        # Another request is already processing - likely a race condition
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Another analysis request is being processed. Please try again.",
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
    
    # Create analysis record (still within the lock)
    analysis = Analysis(
        repository_id=repository_id,
        commit_sha=commit_sha or "HEAD",
        branch=branch or repository.default_branch,
        status="pending",
    )
    db.add(analysis)
    
    # Single commit: updates stuck analyses + creates new one atomically
    await db.commit()
    await db.refresh(analysis)
    
    # Queue analysis task via Celery (now passing analysis_id)
    task = analyze_repository.delay(
        repository_id=str(repository_id),
        analysis_id=str(analysis.id),
        commit_sha=commit_sha or "HEAD",
        triggered_by="manual",
    )
    
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
                "vci_score": analysis.vci_score,
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
        from app.core.redis import get_analysis_last_state
        import json as json_module
        
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
            import json
            error_data = json.dumps({
                "analysis_id": str(analysis_id),
                "stage": "error",
                "progress": 0,
                "message": f"Stream error: {str(e)}",
                "status": "failed",
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
        "vci_score": analysis.vci_score,
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
        "vci_score": analysis.vci_score,
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
                "vci_score": a.vci_score,
                "grade": a.grade,
                "commit_sha": a.commit_sha[:7] if a.commit_sha else None,
            }
            for a in analyses
        ],
        "trend": _calculate_trend(analyses) if len(analyses) >= 2 else "stable",
        "current_score": analyses[-1].vci_score if analyses else None,
        "previous_score": analyses[-2].vci_score if len(analyses) >= 2 else None,
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
    
    diff = last_score - first_score
    
    if diff > 5:
        return "improving"
    elif diff < -5:
        return "declining"
    return "stable"
