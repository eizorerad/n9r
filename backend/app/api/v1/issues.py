"""Issues API endpoints."""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import CurrentUser, DbSession
from app.models.auto_pr import AutoPR
from app.models.issue import Issue
from app.models.repository import Repository
from app.workers.healing import heal_issue

router = APIRouter()


class IssueUpdate(BaseModel):
    """Issue update payload."""
    status: Optional[str] = None
    assigned_to: Optional[str] = None


@router.get("/repositories/{repository_id}/issues")
async def list_issues(
    repository_id: UUID,
    db: DbSession,
    user: CurrentUser,
    status: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
    type: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> dict:
    """List issues for a repository."""
    # Verify access
    result = await db.execute(
        select(Repository).where(
            Repository.id == repository_id,
            Repository.owner_id == user.id,
        )
    )
    repository = result.scalar_one_or_none()
    
    if not repository:
        raise HTTPException(status_code=404, detail="Repository not found")
    
    # Build query
    query = select(Issue).where(Issue.repository_id == repository_id)
    
    if status:
        query = query.where(Issue.status == status)
    if severity:
        query = query.where(Issue.severity == severity)
    if type:
        query = query.where(Issue.type == type)
    
    query = query.order_by(Issue.severity.desc(), Issue.created_at.desc())
    query = query.limit(limit).offset(offset)
    
    result = await db.execute(query)
    issues = result.scalars().all()
    
    return {
        "data": [
            {
                "id": str(i.id),
                "type": i.type,
                "severity": i.severity,
                "title": i.title,
                "description": i.description,
                "file_path": i.file_path,
                "line_start": i.line_start,
                "line_end": i.line_end,
                "confidence": float(i.confidence) if i.confidence else 0.0,
                "status": i.status,
                "auto_fixable": i.auto_fixable,
                "created_at": i.created_at.isoformat(),
            }
            for i in issues
        ],
        "total": len(issues),
    }


@router.get("/issues/{issue_id}")
async def get_issue(
    issue_id: UUID,
    db: DbSession,
    user: CurrentUser,
) -> dict:
    """Get issue details."""
    result = await db.execute(
        select(Issue)
        .options(selectinload(Issue.repository))
        .where(Issue.id == issue_id)
    )
    issue = result.scalar_one_or_none()
    
    if not issue or issue.repository.owner_id != user.id:
        raise HTTPException(status_code=404, detail="Issue not found")
    
    return {
        "id": str(issue.id),
        "type": issue.type,
        "severity": issue.severity,
        "title": issue.title,
        "description": issue.description,
        "file_path": issue.file_path,
        "line_start": issue.line_start,
        "line_end": issue.line_end,
        "metadata": issue.issue_metadata,
        "confidence": float(issue.confidence) if issue.confidence else 0.0,
        "status": issue.status,
        "auto_fixable": issue.auto_fixable,
        "created_at": issue.created_at.isoformat(),
    }


@router.patch("/issues/{issue_id}")
async def update_issue(
    issue_id: UUID,
    payload: IssueUpdate,
    db: DbSession,
    user: CurrentUser,
) -> dict:
    """Update issue status."""
    result = await db.execute(
        select(Issue)
        .options(selectinload(Issue.repository))
        .where(Issue.id == issue_id)
    )
    issue = result.scalar_one_or_none()
    
    if not issue or issue.repository.owner_id != user.id:
        raise HTTPException(status_code=404, detail="Issue not found")
    
    if payload.status:
        issue.status = payload.status
    
    await db.commit()
    
    return {"id": str(issue.id), "status": issue.status}


@router.post("/issues/{issue_id}/fix", status_code=status.HTTP_202_ACCEPTED)
async def fix_issue(
    issue_id: UUID,
    db: DbSession,
    user: CurrentUser,
) -> dict:
    """
    Request automatic fix for an issue.
    
    Triggers the healing pipeline which will:
    1. Diagnose the issue
    2. Generate a fix
    3. Generate regression tests
    4. Validate in sandbox
    5. Create a PR if successful
    
    Returns immediately with task info. Use SSE endpoint to track progress.
    """
    # Load issue and verify access
    result = await db.execute(
        select(Issue)
        .options(selectinload(Issue.repository))
        .where(Issue.id == issue_id)
    )
    issue = result.scalar_one_or_none()
    
    if not issue:
        raise HTTPException(status_code=404, detail="Issue not found")
    
    if issue.repository.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Not authorized to fix this issue")
    
    # Check if issue can be auto-fixed
    if not issue.auto_fixable:
        raise HTTPException(
            status_code=400,
            detail="This issue cannot be auto-fixed. No suggestion available."
        )
    
    # Check if issue has required file_path
    if not issue.file_path:
        raise HTTPException(
            status_code=400,
            detail="Issue has no file path - cannot determine file to fix"
        )
    
    # Check if already being fixed
    if issue.status in ("fixing", "fix_pending"):
        raise HTTPException(
            status_code=409,
            detail=f"Issue is already being processed (status: {issue.status})"
        )
    
    # Create AutoPR record
    auto_pr = AutoPR(
        repository_id=issue.repository_id,
        issue_id=issue.id,
        title=f"fix: {issue.title[:100]}",
        description=f"Automated fix for: {issue.description or issue.title}",
        status="pending",
    )
    db.add(auto_pr)
    
    # Update issue status
    issue.status = "queued"
    await db.commit()
    await db.refresh(auto_pr)
    
    # Queue healing task
    task = heal_issue.delay(
        issue_id=str(issue.id),
        auto_pr_id=str(auto_pr.id),
        max_iterations=3,
    )
    
    return {
        "auto_pr_id": str(auto_pr.id),
        "issue_id": str(issue.id),
        "task_id": task.id,
        "status": "queued",
        "message": "Fix process started. Track progress via SSE endpoint.",
    }


@router.get("/issues/{issue_id}/fix/stream")
async def stream_fix_progress(
    issue_id: UUID,
    db: DbSession,
    user: CurrentUser,
):
    """
    Stream fix progress via Server-Sent Events.
    
    Connect to this endpoint to receive real-time updates during the healing process.
    """
    import asyncio
    import json
    from app.core.redis import subscribe_to_channel
    
    # Verify access
    result = await db.execute(
        select(Issue)
        .options(selectinload(Issue.repository))
        .where(Issue.id == issue_id)
    )
    issue = result.scalar_one_or_none()
    
    if not issue or issue.repository.owner_id != user.id:
        raise HTTPException(status_code=404, detail="Issue not found")
    
    channel = f"healing:progress:{issue_id}"
    
    async def event_generator():
        """Generate SSE events from Redis pub/sub."""
        try:
            async for message in subscribe_to_channel(channel):
                yield f"data: {message}\n\n"
                
                # Check if this is a terminal event
                try:
                    data = json.loads(message)
                    if data.get("status") in ("completed", "failed", "manual_required"):
                        break
                except json.JSONDecodeError:
                    pass
        except asyncio.CancelledError:
            pass
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
