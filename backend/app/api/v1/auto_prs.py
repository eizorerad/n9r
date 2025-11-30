"""Auto-PR API endpoints."""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import CurrentUser, DbSession
from app.models.auto_pr import AutoPR
from app.models.repository import Repository

router = APIRouter()


class AutoPRAction(BaseModel):
    """Auto-PR action request."""
    feedback: Optional[str] = None


@router.get("/repositories/{repository_id}/auto-prs")
async def list_auto_prs(
    repository_id: UUID,
    db: DbSession,
    user: CurrentUser,
    status: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
) -> dict:
    """List auto-PRs for a repository."""
    # Verify access
    result = await db.execute(
        select(Repository).where(
            Repository.id == repository_id,
            Repository.owner_id == user.id,
        )
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Repository not found")
    
    query = select(AutoPR).where(AutoPR.repository_id == repository_id)
    if status:
        query = query.where(AutoPR.status == status)
    query = query.order_by(AutoPR.created_at.desc()).limit(limit)
    
    result = await db.execute(query)
    prs = result.scalars().all()
    
    return {
        "data": [
            {
                "id": str(pr.id),
                "title": pr.title,
                "description": pr.description,
                "status": pr.status,
                "pr_number": pr.github_pr_number,
                "pr_url": pr.github_pr_url,
                "branch_name": pr.branch_name,
                "files_changed": pr.files_changed,
                "created_at": pr.created_at.isoformat(),
            }
            for pr in prs
        ]
    }


@router.get("/auto-prs/{pr_id}")
async def get_auto_pr(
    pr_id: UUID,
    db: DbSession,
    user: CurrentUser,
) -> dict:
    """Get auto-PR details with diff."""
    result = await db.execute(
        select(AutoPR)
        .options(selectinload(AutoPR.repository), selectinload(AutoPR.issue))
        .where(AutoPR.id == pr_id)
    )
    pr = result.scalar_one_or_none()
    
    if not pr or pr.repository.owner_id != user.id:
        raise HTTPException(status_code=404, detail="Auto-PR not found")
    
    return {
        "id": str(pr.id),
        "repository_id": str(pr.repository_id),
        "issue_id": str(pr.issue_id) if pr.issue_id else None,
        "title": pr.title,
        "description": pr.description,
        "status": pr.status,
        "pr_number": pr.github_pr_number,
        "pr_url": pr.github_pr_url,
        "branch_name": pr.branch_name,
        "base_branch": pr.base_branch,
        "files_changed": pr.files_changed,
        "additions": pr.additions,
        "deletions": pr.deletions,
        "diff": pr.diff_content,
        "test_status": pr.test_status,
        "test_output": pr.test_output,
        "review_feedback": pr.review_feedback,
        "created_at": pr.created_at.isoformat(),
        "merged_at": pr.merged_at.isoformat() if pr.merged_at else None,
    }


@router.post("/auto-prs/{pr_id}/approve")
async def approve_auto_pr(
    pr_id: UUID,
    db: DbSession,
    user: CurrentUser,
) -> dict:
    """Approve and merge auto-PR."""
    result = await db.execute(
        select(AutoPR)
        .options(selectinload(AutoPR.repository))
        .where(AutoPR.id == pr_id)
    )
    pr = result.scalar_one_or_none()
    
    if not pr or pr.repository.owner_id != user.id:
        raise HTTPException(status_code=404, detail="Auto-PR not found")
    
    if pr.status != "pending_review":
        raise HTTPException(status_code=400, detail=f"Cannot approve PR in {pr.status} status")
    
    # TODO: Call GitHub API to merge PR
    pr.status = "approved"
    await db.commit()
    
    return {"id": str(pr.id), "status": pr.status, "message": "PR approved"}


@router.post("/auto-prs/{pr_id}/reject")
async def reject_auto_pr(
    pr_id: UUID,
    payload: AutoPRAction,
    db: DbSession,
    user: CurrentUser,
) -> dict:
    """Reject and close auto-PR."""
    result = await db.execute(
        select(AutoPR)
        .options(selectinload(AutoPR.repository))
        .where(AutoPR.id == pr_id)
    )
    pr = result.scalar_one_or_none()
    
    if not pr or pr.repository.owner_id != user.id:
        raise HTTPException(status_code=404, detail="Auto-PR not found")
    
    # TODO: Call GitHub API to close PR
    pr.status = "rejected"
    pr.review_feedback = payload.feedback
    await db.commit()
    
    return {"id": str(pr.id), "status": pr.status}


@router.post("/auto-prs/{pr_id}/revise")
async def request_revision(
    pr_id: UUID,
    payload: AutoPRAction,
    db: DbSession,
    user: CurrentUser,
) -> dict:
    """Request revision of auto-PR with feedback."""
    from app.workers.healing import retry_healing
    
    result = await db.execute(
        select(AutoPR)
        .options(selectinload(AutoPR.repository))
        .where(AutoPR.id == pr_id)
    )
    pr = result.scalar_one_or_none()
    
    if not pr or pr.repository.owner_id != user.id:
        raise HTTPException(status_code=404, detail="Auto-PR not found")
    
    if not payload.feedback:
        raise HTTPException(status_code=400, detail="Feedback is required for revision")
    
    pr.status = "revision_requested"
    pr.review_feedback = payload.feedback
    await db.commit()
    
    # Queue retry task with feedback
    task = retry_healing.delay(
        auto_pr_id=str(pr.id),
        feedback=payload.feedback,
    )
    
    return {
        "id": str(pr.id),
        "status": pr.status,
        "task_id": task.id,
        "message": "Revision requested and queued",
    }
