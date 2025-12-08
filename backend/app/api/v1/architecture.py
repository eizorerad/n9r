"""Architecture Findings API endpoints.

Provides endpoints for architecture analysis findings:
- Dead code findings from call graph analysis
- Hot spot findings from git churn analysis
- Semantic AI insights from LLM analysis

Requirements: 6.1, 6.2, 7.3, 7.4
"""

import logging
from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.models.analysis import Analysis
from app.models.dead_code import DeadCode
from app.models.file_churn import FileChurn
from app.models.repository import Repository
from app.models.semantic_ai_insight import SemanticAIInsight
from app.schemas.architecture_findings import (
    ArchitectureFindingsResponse,
    ArchitectureSummarySchema,
    DeadCodeFindingSchema,
    HotSpotFindingSchema,
    SemanticAIInsightSchema,
)
from app.services.scoring import get_scoring_service

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get(
    "/repositories/{repository_id}/architecture-findings",
    response_model=ArchitectureFindingsResponse,
)
async def get_architecture_findings(
    repository_id: UUID,
    db: DbSession,
    user: CurrentUser,
    analysis_id: UUID | None = Query(
        default=None,
        description="Specific analysis ID. If not provided, uses latest completed analysis.",
    ),
    include_dismissed: bool = Query(
        default=False,
        description="Include dismissed findings in response",
    ),
) -> ArchitectureFindingsResponse:
    """
    Get architecture findings for a repository.

    Returns dead code findings, hot spots, and AI-generated insights
    from the specified analysis (or latest completed analysis).

    Requirements: 6.1, 6.2, 7.4
    """
    # Verify repository ownership
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

    # Get analysis (specific or latest completed)
    if analysis_id:
        analysis_result = await db.execute(
            select(Analysis).where(
                Analysis.id == analysis_id,
                Analysis.repository_id == repository_id,
            )
        )
        analysis = analysis_result.scalar_one_or_none()
        if not analysis:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Analysis not found",
            )
    else:
        # Get latest completed analysis
        analysis_result = await db.execute(
            select(Analysis)
            .where(
                Analysis.repository_id == repository_id,
                Analysis.status == "completed",
            )
            .order_by(Analysis.created_at.desc())
            .limit(1)
        )
        analysis = analysis_result.scalar_one_or_none()
        if not analysis:
            # Return empty response if no completed analysis
            return ArchitectureFindingsResponse(
                summary=ArchitectureSummarySchema(
                    health_score=0,
                    main_concerns=[],
                    dead_code_count=0,
                    hot_spot_count=0,
                    insights_count=0,
                ),
                dead_code=[],
                hot_spots=[],
                insights=[],
            )

    # Query dead code findings
    dead_code_query = select(DeadCode).where(DeadCode.analysis_id == analysis.id)
    if not include_dismissed:
        dead_code_query = dead_code_query.where(DeadCode.is_dismissed.is_(False))
    dead_code_result = await db.execute(dead_code_query)
    dead_code_findings = dead_code_result.scalars().all()

    # Query hot spot findings (file_churn with changes_90d > 10)
    hot_spot_query = select(FileChurn).where(
        FileChurn.analysis_id == analysis.id,
        FileChurn.changes_90d > 10,
    )
    hot_spot_result = await db.execute(hot_spot_query)
    hot_spot_findings = hot_spot_result.scalars().all()

    # Query semantic AI insights
    insights_query = select(SemanticAIInsight).where(
        SemanticAIInsight.analysis_id == analysis.id
    )
    if not include_dismissed:
        insights_query = insights_query.where(SemanticAIInsight.is_dismissed.is_(False))
    insights_result = await db.execute(insights_query)
    insights = insights_result.scalars().all()

    logger.info(
        f"Architecture findings for analysis {analysis.id}: "
        f"dead_code={len(dead_code_findings)}, hot_spots={len(hot_spot_findings)}, insights={len(insights)}"
    )

    # Extract totals from analysis metrics and semantic_cache for health score calculation
    # Requirements: 3.1, 3.2, 3.3, 3.4
    metrics = analysis.metrics or {}
    semantic_cache = analysis.semantic_cache or {}

    # Get total_files from metrics or semantic_cache
    total_files = metrics.get("total_files", 0) or semantic_cache.get("total_files", 0)
    if total_files == 0:
        # Fallback: use count of unique files from hot spots
        total_files = len({hs.file_path for hs in hot_spot_findings}) or 1

    # Get total_chunks from semantic_cache
    total_chunks = semantic_cache.get("total_chunks", 0)
    if total_chunks == 0:
        # Fallback: use vectors_count from analysis
        total_chunks = analysis.vectors_count or 1

    # Estimate total_functions - use total_chunks as proxy or estimate from files
    # Each file typically has ~5 functions on average
    total_functions = total_chunks if total_chunks > 0 else max(total_files * 5, 1)

    # Get outlier count from semantic_cache
    outliers = semantic_cache.get("outliers", [])
    outlier_count = len(outliers) if isinstance(outliers, list) else 0

    # Calculate health score using penalty-based formula
    health_score = _calculate_health_score(
        dead_code_count=len(dead_code_findings),
        hot_spot_count=len(hot_spot_findings),
        outlier_count=outlier_count,
        total_functions=total_functions,
        total_files=total_files,
        total_chunks=total_chunks,
    )
    main_concerns = _generate_main_concerns(
        dead_code_findings=dead_code_findings,
        hot_spot_findings=hot_spot_findings,
    )

    return ArchitectureFindingsResponse(
        summary=ArchitectureSummarySchema(
            health_score=health_score,
            main_concerns=main_concerns,
            dead_code_count=len(dead_code_findings),
            hot_spot_count=len(hot_spot_findings),
            insights_count=len(insights),
        ),
        dead_code=[
            DeadCodeFindingSchema(
                id=dc.id,
                file_path=dc.file_path,
                function_name=dc.function_name,
                line_start=dc.line_start,
                line_end=dc.line_end,
                line_count=dc.line_count,
                confidence=dc.confidence,
                evidence=dc.evidence,
                suggested_action=dc.suggested_action,
                impact_score=dc.impact_score,
                is_dismissed=dc.is_dismissed,
                dismissed_at=dc.dismissed_at,
                created_at=dc.created_at,
            )
            for dc in dead_code_findings
        ],
        hot_spots=[
            HotSpotFindingSchema(
                id=hs.id,
                file_path=hs.file_path,
                changes_90d=hs.changes_90d,
                coverage_rate=hs.coverage_rate,
                unique_authors=hs.unique_authors,
                risk_factors=hs.risk_factors or [],
                suggested_action=hs.suggested_action,
                risk_score=hs.risk_score,
                created_at=hs.created_at,
            )
            for hs in hot_spot_findings
        ],
        insights=[
            SemanticAIInsightSchema(
                id=insight.id,
                insight_type=insight.insight_type,
                title=insight.title,
                description=insight.description,
                priority=insight.priority,
                affected_files=insight.affected_files or [],
                evidence=insight.evidence,
                suggested_action=insight.suggested_action,
                is_dismissed=insight.is_dismissed,
                dismissed_at=insight.dismissed_at,
                created_at=insight.created_at,
            )
            for insight in insights
        ],
    )


@router.post(
    "/repositories/{repository_id}/dead-code/{dead_code_id}/dismiss",
    status_code=status.HTTP_200_OK,
)
async def dismiss_dead_code(
    repository_id: UUID,
    dead_code_id: UUID,
    db: DbSession,
    user: CurrentUser,
) -> dict:
    """
    Dismiss a dead code finding.

    Updates the is_dismissed flag and sets dismissed_at timestamp.

    Requirements: 7.3
    """
    # Verify repository ownership
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

    # Get dead code finding
    dead_code_result = await db.execute(
        select(DeadCode).where(
            DeadCode.id == dead_code_id,
            DeadCode.repository_id == repository_id,
        )
    )
    dead_code = dead_code_result.scalar_one_or_none()
    if not dead_code:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dead code finding not found",
        )

    # Update dismissal state
    dead_code.is_dismissed = True
    dead_code.dismissed_at = datetime.now(UTC)
    await db.commit()

    logger.info(f"Dead code finding {dead_code_id} dismissed by user {user.id}")

    return {
        "id": str(dead_code.id),
        "is_dismissed": dead_code.is_dismissed,
        "dismissed_at": dead_code.dismissed_at.isoformat() if dead_code.dismissed_at else None,
    }


@router.post(
    "/repositories/{repository_id}/insights/{insight_id}/dismiss",
    status_code=status.HTTP_200_OK,
)
async def dismiss_insight(
    repository_id: UUID,
    insight_id: UUID,
    db: DbSession,
    user: CurrentUser,
) -> dict:
    """
    Dismiss a semantic AI insight.

    Updates the is_dismissed flag and sets dismissed_at timestamp.
    """
    # Verify repository ownership
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

    # Get insight
    insight_result = await db.execute(
        select(SemanticAIInsight).where(
            SemanticAIInsight.id == insight_id,
            SemanticAIInsight.repository_id == repository_id,
        )
    )
    insight = insight_result.scalar_one_or_none()
    if not insight:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Insight not found",
        )

    # Update dismissal state
    insight.is_dismissed = True
    insight.dismissed_at = datetime.now(UTC)
    await db.commit()

    logger.info(f"Insight {insight_id} dismissed by user {user.id}")

    return {
        "id": str(insight.id),
        "is_dismissed": insight.is_dismissed,
        "dismissed_at": insight.dismissed_at.isoformat() if insight.dismissed_at else None,
    }


def _calculate_health_score(
    dead_code_count: int,
    hot_spot_count: int,
    outlier_count: int,
    total_functions: int,
    total_files: int,
    total_chunks: int,
) -> int:
    """Calculate architecture health score (0-100) using penalty-based formula.

    Uses ScoringService.calculate_architecture_health_score() with the formula:
    AHS = 100 - (Dead Code Penalty + Hot Spot Penalty + Outlier Penalty)

    Where:
    - Dead Code Penalty = min(40, (dead_code_count / total_functions) × 80)
    - Hot Spot Penalty = min(30, (hot_spot_count / total_files) × 60)
    - Outlier Penalty = min(20, (outlier_count / total_chunks) × 40)

    Requirements: 3.1, 3.2, 3.3, 3.4
    """
    scoring_service = get_scoring_service()
    return scoring_service.calculate_architecture_health_score(
        dead_code_count=dead_code_count,
        total_functions=total_functions,
        hot_spot_count=hot_spot_count,
        total_files=total_files,
        outlier_count=outlier_count,
        total_chunks=total_chunks,
    )


def _generate_main_concerns(
    dead_code_findings: list[DeadCode],
    hot_spot_findings: list[FileChurn],
) -> list[str]:
    """Generate natural language main concerns list."""
    concerns = []

    if dead_code_findings:
        total_lines = sum(dc.line_count for dc in dead_code_findings)
        concerns.append(
            f"{len(dead_code_findings)} unreachable functions ({total_lines} lines of dead code)"
        )

    if hot_spot_findings:
        worst = max(hot_spot_findings, key=lambda h: h.changes_90d)
        concerns.append(
            f"{worst.file_path} changed {worst.changes_90d} times in 90 days"
        )

        low_coverage = [h for h in hot_spot_findings if h.coverage_rate is not None and h.coverage_rate < 0.5]
        if low_coverage:
            concerns.append(
                f"{len(low_coverage)} hot spots have less than 50% test coverage"
            )

    return concerns
