"""AI Scan API endpoints.

Provides endpoints for triggering AI-powered code analysis,
retrieving cached results, and streaming progress updates.

Requirements: 1.1, 1.4, 6.4, 7.1, 7.2, 7.3
"""

import asyncio
import json
import logging
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import CurrentUser, DbSession
from app.api.v1.analyses import get_analysis_for_user_or_404
from app.models.analysis import Analysis
from app.schemas.ai_scan import (
    AIScanCacheResponse,
    AIScanConfidence,
    AIScanDimension,
    AIScanIssue,
    AIScanRequest,
    AIScanSeverity,
    AIScanStatus,
    AIScanTriggerResponse,
    FileLocation,
    InvestigationStatus,
    RepoOverview,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/analyses", tags=["ai-scan"])


# =============================================================================
# Constants
# =============================================================================

AI_SCAN_PROGRESS_PREFIX = "ai_scan:progress:"
AI_SCAN_STATE_PREFIX = "ai_scan:state:"


def get_ai_scan_channel(analysis_id: str) -> str:
    """Get Redis channel name for AI scan progress."""
    return f"{AI_SCAN_PROGRESS_PREFIX}{analysis_id}"


def get_ai_scan_state_key(analysis_id: str) -> str:
    """Get Redis key for AI scan progress state."""
    return f"{AI_SCAN_STATE_PREFIX}{analysis_id}"


# =============================================================================
# POST - Trigger AI Scan
# =============================================================================


@router.post("/{analysis_id}/ai-scan", status_code=status.HTTP_202_ACCEPTED)
async def trigger_ai_scan(
    analysis_id: UUID,
    db: DbSession,
    user: CurrentUser,
    request: AIScanRequest | None = None,
) -> AIScanTriggerResponse:
    """Trigger AI scan for an existing analysis.

    Validates the analysis exists and is completed, checks for in-progress
    scans, and queues a Celery task to perform the scan.

    Requirements: 1.1, 1.4
    """
    from app.workers.ai_scan import run_ai_scan

    # Use defaults if no request body
    if request is None:
        request = AIScanRequest()

    # Use helper to verify access - returns 404 for both non-existent and unauthorized
    analysis = await get_analysis_for_user_or_404(db, analysis_id, user.id)

    # Check if analysis is completed
    if analysis.status != "completed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Analysis must be completed before running AI scan (current status: {analysis.status})",
        )

    # Check for in-progress AI scan (Requirement 1.4)
    # Source of truth is Analysis.ai_scan_status (progress-tracking-refactor).
    if analysis.ai_scan_status in ("pending", "running"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="AI scan already in progress",
        )

    # Mark scan as pending using the state service (single source of truth).
    from app.services.analysis_state import AnalysisStateService, InvalidStateTransitionError

    try:
        AnalysisStateService(db, publish_events=True).mark_ai_scan_pending(analysis_id)
    except InvalidStateTransitionError:
        # If state is already pending/running/completed, treat as conflict to avoid double-queue.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="AI scan already in progress",
        )

    # Queue Celery task
    task = run_ai_scan.delay(
        analysis_id=str(analysis_id),
        models=request.models,
        investigate_severity=[s.value for s in request.investigate_severity],
        max_issues=request.max_issues_to_investigate,
    )

    logger.info(f"Queued AI scan task {task.id} for analysis {analysis_id}")

    return AIScanTriggerResponse(
        analysis_id=analysis_id,
        status=AIScanStatus.PENDING,
        message="AI scan queued successfully",
    )


# =============================================================================
# GET - Retrieve AI Scan Results
# =============================================================================


@router.get("/{analysis_id}/ai-scan")
async def get_ai_scan_results(
    analysis_id: UUID,
    db: DbSession,
    user: CurrentUser,
) -> AIScanCacheResponse:
    """Get AI scan results from cache.

    Returns cached results from Analysis.ai_scan_cache.
    If no scan has been performed, returns is_cached=false.

    Requirements: 7.1, 7.2
    """
    # Use helper to verify access - returns 404 for both non-existent and unauthorized
    analysis = await get_analysis_for_user_or_404(db, analysis_id, user.id)

    cache = analysis.ai_scan_cache

    # No cache - return empty response (Requirement 7.2)
    if not cache:
        return AIScanCacheResponse(
            analysis_id=analysis_id,
            commit_sha=analysis.commit_sha,
            status=AIScanStatus(analysis.ai_scan_status),
            repo_overview=None,
            issues=[],
            computed_at=None,
            is_cached=False,
            total_tokens_used=None,
            total_cost_usd=None,
        )

    # Parse status: prefer the tracked column (single source of truth),
    # fall back to cache["status"] for legacy rows.
    status_str = analysis.ai_scan_status or cache.get("status", "pending")
    try:
        scan_status = AIScanStatus(status_str)
    except ValueError:
        scan_status = AIScanStatus.PENDING

    # Parse repo overview
    repo_overview = None
    if cache.get("repo_overview"):
        try:
            repo_overview = RepoOverview(**cache["repo_overview"])
        except Exception:
            pass

    # Parse issues
    issues = []
    for issue_data in cache.get("issues", []):
        try:
            # Parse file locations
            files = []
            for f in issue_data.get("files", []):
                files.append(FileLocation(
                    path=f.get("path", ""),
                    line_start=f.get("line_start", 1),
                    line_end=f.get("line_end", 1),
                ))

            # Parse investigation status
            inv_status = None
            if issue_data.get("investigation_status"):
                try:
                    inv_status = InvestigationStatus(issue_data["investigation_status"])
                except ValueError:
                    pass

            issues.append(AIScanIssue(
                id=issue_data.get("id", "unknown"),
                dimension=AIScanDimension(issue_data.get("dimension", "other")),
                severity=AIScanSeverity(issue_data.get("severity", "low")),
                title=issue_data.get("title", "Unknown Issue"),
                summary=issue_data.get("summary", ""),
                files=files,
                evidence_snippets=issue_data.get("evidence_snippets", []),
                confidence=AIScanConfidence(issue_data.get("confidence", "low")),
                found_by_models=issue_data.get("found_by_models", []),
                investigation_status=inv_status,
                suggested_fix=issue_data.get("suggested_fix"),
            ))
        except Exception as e:
            logger.warning(f"Failed to parse issue: {e}")
            continue

    # Parse computed_at
    computed_at = None
    if cache.get("computed_at"):
        try:
            computed_at = datetime.fromisoformat(cache["computed_at"].replace("Z", "+00:00"))
        except Exception:
            pass

    return AIScanCacheResponse(
        analysis_id=analysis_id,
        commit_sha=cache.get("commit_sha", analysis.commit_sha),
        status=scan_status,
        repo_overview=repo_overview,
        issues=issues,
        computed_at=computed_at,
        is_cached=True,
        total_tokens_used=cache.get("total_tokens_used"),
        total_cost_usd=cache.get("total_cost_usd"),
    )


# =============================================================================
# GET - SSE Streaming Progress
# =============================================================================


@router.get("/{analysis_id}/ai-scan/stream")
async def stream_ai_scan_progress(
    analysis_id: UUID,
    db: DbSession,
    user: CurrentUser,
):
    """Stream AI scan progress via Server-Sent Events (SSE).

    Subscribes to Redis Pub/Sub for the analysis_id and streams
    progress events to the client.

    Events format:
    ```
    data: {"analysis_id": "...", "stage": "scanning", "progress": 50, "message": "...", "status": "running"}
    ```

    Requirements: 6.4, 7.3
    """
    import redis.asyncio as aioredis

    from app.core.redis import async_redis_pool

    # Use helper to verify access - returns 404 for both non-existent and unauthorized
    analysis = await get_analysis_for_user_or_404(db, analysis_id, user.id)

    # Check if AI scan is already completed or failed (prefer tracked column)
    cache = analysis.ai_scan_cache
    terminal_status = analysis.ai_scan_status if analysis.ai_scan_status in ("completed", "failed") else None
    if terminal_status or (cache and cache.get("status") in ("completed", "failed")):
        async def completed_stream():
            status_str = terminal_status or cache.get("status")
            data = json.dumps({
                "analysis_id": str(analysis_id),
                "stage": status_str,
                "progress": 100 if status_str == "completed" else 0,
                "message": (
                    analysis.ai_scan_error
                    if status_str == "failed" and analysis.ai_scan_error
                    else cache.get("error_message", "AI scan complete") if status_str == "failed"
                    else "AI scan complete"
                ),
                "status": status_str,
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
        """Generate SSE events from Redis Pub/Sub."""
        client = aioredis.Redis(connection_pool=async_redis_pool)
        pubsub = client.pubsub()
        channel = get_ai_scan_channel(str(analysis_id))
        state_key = get_ai_scan_state_key(str(analysis_id))

        start_time = asyncio.get_event_loop().time()
        timeout_seconds = 600  # 10 minutes
        keepalive_interval = 30
        last_message_time = start_time

        try:
            # 1. Send last known state immediately (for late subscribers)
            last_state = await client.get(state_key)
            if last_state:
                yield f"data: {last_state}\n\n"

                # Check if already finished
                try:
                    state_data = json.loads(last_state)
                    if state_data.get("status") in ("completed", "failed"):
                        return
                except json.JSONDecodeError:
                    pass
            else:
                # No state yet, send initial message
                initial_data = json.dumps({
                    "analysis_id": str(analysis_id),
                    "stage": "queued",
                    "progress": 0,
                    "message": "Connected, waiting for AI scan to start...",
                    "status": "pending",
                })
                yield f"data: {initial_data}\n\n"

            # 2. Subscribe to real-time updates
            await pubsub.subscribe(channel)
            logger.info(f"Subscribed to AI scan channel: {channel}")

            while True:
                current_time = asyncio.get_event_loop().time()

                # Check overall timeout (transport timeout, not scan failure)
                if current_time - start_time > timeout_seconds:
                    timeout_data = json.dumps({
                        "analysis_id": str(analysis_id),
                        "stage": "timeout",
                        "progress": 0,
                        "message": "Connection timed out. Refresh to check status.",
                        "status": "timeout",
                    })
                    yield f"data: {timeout_data}\n\n"
                    break

                # Calculate wait timeout
                time_since_last = current_time - last_message_time
                wait_timeout = max(0.1, keepalive_interval - time_since_last)

                try:
                    message = await asyncio.wait_for(
                        pubsub.get_message(ignore_subscribe_messages=True, timeout=wait_timeout),
                        timeout=wait_timeout + 1
                    )

                    if message and message["type"] == "message":
                        last_message_time = asyncio.get_event_loop().time()
                        data = message["data"]
                        if isinstance(data, bytes):
                            data = data.decode("utf-8")
                        yield f"data: {data}\n\n"

                        # Check if scan completed or failed
                        try:
                            parsed = json.loads(data)
                            if parsed.get("status") in ("completed", "failed"):
                                logger.info(f"AI scan {analysis_id} finished: {parsed.get('status')}")
                                return
                        except json.JSONDecodeError:
                            pass

                    elif current_time - last_message_time >= keepalive_interval:
                        # Send keepalive
                        last_message_time = current_time
                        yield ": keepalive\n\n"

                except TimeoutError:
                    if current_time - last_message_time >= keepalive_interval:
                        last_message_time = current_time
                        yield ": keepalive\n\n"
                    continue

        except asyncio.CancelledError:
            pass
        except Exception as e:
            # Streaming transport error (Redis/network/etc). Do NOT mark the scan as failed.
            # Emit a non-terminal "error" event so the client can retry.
            error_data = json.dumps({
                "analysis_id": str(analysis_id),
                "stage": "error",
                "progress": 0,
                "message": f"Stream error: {str(e)}",
                "status": "error",
            })
            yield f"data: {error_data}\n\n"
        finally:
            await pubsub.unsubscribe(channel)
            await pubsub.aclose()
            await client.aclose()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
