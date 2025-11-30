"""Playground API - public repo scanning without auth."""

import logging
import re
from datetime import datetime
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request, BackgroundTasks
from pydantic import BaseModel, Field, field_validator

from app.core.config import settings
from app.core.redis import (
    store_playground_scan,
    get_playground_scan,
    update_playground_scan,
    check_playground_rate_limit,
)
from app.services.repo_analyzer import RepoAnalyzer

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/playground", tags=["playground"])


class PlaygroundScanRequest(BaseModel):
    """Request to scan a public repository."""
    repo_url: str = Field(..., description="GitHub repository URL")
    
    @field_validator("repo_url")
    @classmethod
    def validate_github_url(cls, v: str) -> str:
        """Validate GitHub URL format."""
        pattern = r"^https?://(www\.)?github\.com/[\w.-]+/[\w.-]+/?$"
        if not re.match(pattern, v):
            raise ValueError("Invalid GitHub repository URL")
        return v.rstrip("/")


class PlaygroundScanResponse(BaseModel):
    """Response after starting a scan."""
    scan_id: str
    repo_url: str
    status: str = "pending"
    message: str = "Scan started"


class PlaygroundScanResult(BaseModel):
    """Result of a completed scan."""
    scan_id: str
    repo_url: str
    status: str
    vci_score: Optional[float] = None
    tech_debt_level: Optional[str] = None
    metrics: Optional[dict] = None
    top_issues: Optional[list] = None
    ai_report: Optional[str] = None
    error: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


def _get_client_ip(request: Request) -> str:
    """Get client IP from request."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _run_scan(scan_id: str, repo_url: str):
    """Run the actual scan (background task)."""
    logger.info(f"Starting playground scan {scan_id} for {repo_url}")
    
    update_playground_scan(scan_id, {
        "status": "running",
        "started_at": datetime.utcnow().isoformat(),
    })
    
    try:
        with RepoAnalyzer(repo_url) as analyzer:
            result = analyzer.analyze()
        
        update_playground_scan(scan_id, {
            "status": "completed",
            "vci_score": result.vci_score,
            "tech_debt_level": result.tech_debt_level,
            "metrics": result.metrics,
            "top_issues": result.issues[:5],  # Top 5 issues
            "ai_report": result.ai_report,
            "completed_at": datetime.utcnow().isoformat(),
        })
        
        logger.info(f"Playground scan {scan_id} completed, VCI: {result.vci_score}")
        
    except Exception as e:
        logger.error(f"Playground scan {scan_id} failed: {e}")
        update_playground_scan(scan_id, {
            "status": "failed",
            "error": str(e)[:500],
            "completed_at": datetime.utcnow().isoformat(),
        })


@router.post("/scan", response_model=PlaygroundScanResponse)
async def start_scan(
    request: Request,
    body: PlaygroundScanRequest,
    background_tasks: BackgroundTasks,
):
    """
    Start a public repository scan.
    
    - **repo_url**: GitHub repository URL (must be public)
    - Rate limited: 5 scans per hour per IP
    - No authentication required
    """
    client_ip = _get_client_ip(request)
    
    # Check rate limit
    if not check_playground_rate_limit(client_ip):
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded. Maximum 5 scans per hour."
        )
    
    # Generate scan ID
    scan_id = str(uuid4())
    
    # Initialize scan result in Redis
    store_playground_scan(scan_id, {
        "scan_id": scan_id,
        "repo_url": body.repo_url,
        "status": "pending",
        "client_ip": client_ip,
    })
    
    # Start background scan
    background_tasks.add_task(_run_scan, scan_id, body.repo_url)
    
    return PlaygroundScanResponse(
        scan_id=scan_id,
        repo_url=body.repo_url,
        status="pending",
        message="Scan started. Poll GET /playground/scan/{scan_id} for results.",
    )


@router.get("/scan/{scan_id}", response_model=PlaygroundScanResult)
async def get_scan_result(scan_id: str):
    """
    Get scan result by ID.
    
    - Returns current status and results when completed
    - Results are cached for 1 hour
    """
    result = get_playground_scan(scan_id)
    
    if not result:
        raise HTTPException(status_code=404, detail="Scan not found")
    
    return PlaygroundScanResult(
        scan_id=result["scan_id"],
        repo_url=result["repo_url"],
        status=result["status"],
        vci_score=result.get("vci_score"),
        tech_debt_level=result.get("tech_debt_level"),
        metrics=result.get("metrics"),
        top_issues=result.get("top_issues"),
        ai_report=result.get("ai_report"),
        error=result.get("error"),
        started_at=result.get("started_at"),
        completed_at=result.get("completed_at"),
    )
