"""Semantic Code Analysis API endpoints.

Provides vector-based code understanding features:
- Semantic search (natural language code search)
- Related code detection (impact analysis)
- Cluster analysis (architecture insights)
- Outlier detection (dead code)
- Similar code detection (duplicates)
- Refactoring suggestions
- Technical debt heatmap
- Code style consistency

All endpoints support commit-aware filtering via optional `ref` parameter.
When `ref` is not provided, defaults to the latest completed analysis commit.
"""

import logging
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.models.repository import Repository
from app.services.vector_store import VectorStoreService, get_qdrant_client

logger = logging.getLogger(__name__)
router = APIRouter()

COLLECTION_NAME = "code_embeddings"


def _get_vector_store_service() -> VectorStoreService:
    """Get VectorStoreService instance."""
    return VectorStoreService()


async def _resolve_commit_sha(
    db,
    repository_id: UUID,
    user_id: UUID,
    ref: str | None,
) -> tuple[str | None, str]:
    """Resolve ref to commit SHA, return (sha, source).
    
    Returns:
        Tuple of (commit_sha or None, source description)
    """
    vs = _get_vector_store_service()
    resolution = await vs.resolve_ref_to_commit_sha_async(
        db=db,
        repository_id=repository_id,
        user_id=user_id,
        ref=ref,
    )
    return resolution.resolved_commit_sha, resolution.source


# ============================================================================
# Semantic Search
# ============================================================================

class SemanticSearchResult(BaseModel):
    """A single search result."""
    file_path: str
    name: str | None
    chunk_type: str | None
    line_start: int | None
    line_end: int | None
    content: str | None
    similarity: float
    qualified_name: str | None = None
    language: str | None = None


class SemanticSearchResponse(BaseModel):
    """Response for semantic search."""
    query: str
    results: list[SemanticSearchResult]
    total: int
    resolved_commit_sha: str | None = None  # Actual commit SHA used for query
    requested_ref: str | None = None  # Original ref requested by user


@router.get("/repositories/{repository_id}/semantic-search")
async def semantic_search(
    repository_id: UUID,
    db: DbSession,
    user: CurrentUser,
    q: str = Query(..., min_length=2, description="Search query"),
    limit: int = Query(10, ge=1, le=50, description="Max results"),
    ref: str | None = Query(None, description="Git ref (branch name or SHA). Defaults to latest analyzed commit."),
) -> SemanticSearchResponse:
    """
    Search code using natural language.

    Supports commit-aware filtering via optional `ref` parameter.
    When `ref` is not provided, defaults to the latest completed analysis commit.

    Examples:
    - "user authentication"
    - "database connection handling"
    - "error handling patterns"
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
        raise HTTPException(status_code=404, detail="Repository not found")

    # Lazy import to avoid fork-safety issues
    from app.services.llm_gateway import get_llm_gateway

    try:
        # Resolve commit SHA (commit-centric by default)
        commit_sha, source = await _resolve_commit_sha(db, repository_id, user.id, ref)
        logger.debug(f"semantic-search: resolved ref={ref} -> sha={commit_sha} (source={source})")

        llm = get_llm_gateway()
        vs = _get_vector_store_service()

        # Generate embedding for query
        query_embedding = await llm.embed([q])

        # Search using VectorStoreService (commit-aware)
        points = vs.query_similar_chunks(
            repository_id=repository_id,
            commit_sha=commit_sha,
            query_vector=query_embedding[0],
            limit=limit,
        )

        search_results = [
            SemanticSearchResult(
                file_path=hit.payload.get("file_path", ""),
                name=hit.payload.get("name"),
                chunk_type=hit.payload.get("chunk_type"),
                line_start=hit.payload.get("line_start"),
                line_end=hit.payload.get("line_end"),
                content=hit.payload.get("content", "")[:500],  # Truncate for response
                similarity=round(hit.score, 4),
                qualified_name=hit.payload.get("qualified_name"),
                language=hit.payload.get("language"),
            )
            for hit in points
        ]

        return SemanticSearchResponse(
            query=q,
            results=search_results,
            total=len(search_results),
            resolved_commit_sha=commit_sha,
            requested_ref=ref,
        )

    except Exception as e:
        logger.error(f"Semantic search failed: {e}")
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")


# ============================================================================
# Related Code (Impact Analysis)
# ============================================================================

class RelatedCodeResult(BaseModel):
    """A related code chunk."""
    file_path: str
    name: str | None
    chunk_type: str | None
    line_start: int | None
    line_end: int | None
    similarity: float
    cluster: str | None = None
    qualified_name: str | None = None


class RelatedCodeResponse(BaseModel):
    """Response for related code query."""
    query_file: str
    cluster: str | None = None
    related: list[RelatedCodeResult]
    resolved_commit_sha: str | None = None  # Actual commit SHA used for query
    requested_ref: str | None = None  # Original ref requested by user


@router.get("/repositories/{repository_id}/related-code")
async def get_related_code(
    repository_id: UUID,
    db: DbSession,
    user: CurrentUser,
    file: str = Query(..., description="File path to find related code for"),
    limit: int = Query(10, ge=1, le=50, description="Max results"),
    ref: str | None = Query(None, description="Git ref (branch name or SHA). Defaults to latest analyzed commit."),
) -> RelatedCodeResponse:
    """
    Find code semantically related to a given file.

    Supports commit-aware filtering via optional `ref` parameter.

    Useful for:
    - Impact analysis: "What might break if I change this?"
    - Understanding dependencies beyond imports
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
        raise HTTPException(status_code=404, detail="Repository not found")

    try:
        # Resolve commit SHA (commit-centric by default)
        commit_sha, source = await _resolve_commit_sha(db, repository_id, user.id, ref)
        logger.debug(f"related-code: resolved ref={ref} -> sha={commit_sha} (source={source})")

        vs = _get_vector_store_service()

        # First, get embeddings for the query file (commit-aware scroll)
        file_chunks, _ = vs.scroll_vectors(
            repository_id=repository_id,
            commit_sha=commit_sha,
            limit=10,
            with_vectors=True,
        )

        # Filter to only the target file
        file_chunks = [c for c in file_chunks if c.payload and c.payload.get("file_path") == file]

        if not file_chunks:
            raise HTTPException(status_code=404, detail=f"No embeddings found for file: {file}")

        # Average the vectors for the file
        import numpy as np
        vectors = [chunk.vector for chunk in file_chunks if chunk.vector]
        if not vectors:
            raise HTTPException(status_code=404, detail="No vectors found for file")

        avg_vector = np.mean(vectors, axis=0).tolist()

        # Search for similar code, excluding the query file (commit-aware)
        points = vs.query_similar_chunks(
            repository_id=repository_id,
            commit_sha=commit_sha,
            query_vector=avg_vector,
            limit=limit,
            exclude_file_path=file,
        )

        related = [
            RelatedCodeResult(
                file_path=hit.payload.get("file_path", ""),
                name=hit.payload.get("name"),
                chunk_type=hit.payload.get("chunk_type"),
                line_start=hit.payload.get("line_start"),
                line_end=hit.payload.get("line_end"),
                similarity=round(hit.score, 4),
                cluster=None,  # Will be populated by cluster analysis
                qualified_name=hit.payload.get("qualified_name"),
            )
            for hit in points
        ]

        return RelatedCodeResponse(
            query_file=file,
            cluster=None,  # Will be populated by cluster analysis
            related=related,
            resolved_commit_sha=commit_sha,
            requested_ref=ref,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Related code search failed: {e}")
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")



# ============================================================================
# Cluster Analysis & Architecture Health
# ============================================================================

class ClusterInfoResponse(BaseModel):
    """Cluster information."""
    id: int
    name: str
    file_count: int
    chunk_count: int
    cohesion: float
    top_files: list[str]
    dominant_language: str | None
    status: str


class OutlierInfoResponse(BaseModel):
    """Outlier information."""
    file_path: str
    chunk_name: str | None
    chunk_type: str | None
    nearest_similarity: float
    nearest_file: str | None
    suggestion: str
    confidence: float = 0.5
    confidence_factors: list[str] = []
    tier: str = "recommended"


class CouplingHotspotResponse(BaseModel):
    """Coupling hotspot information."""
    file_path: str
    clusters_connected: int
    cluster_names: list[str]
    suggestion: str


class ArchitectureHealthResponse(BaseModel):
    """Full architecture health response."""
    overall_score: int
    clusters: list[ClusterInfoResponse]
    outliers: list[OutlierInfoResponse]
    coupling_hotspots: list[CouplingHotspotResponse]
    total_chunks: int
    total_files: int
    metrics: dict


@router.get("/repositories/{repository_id}/architecture-health")
async def get_architecture_health(
    repository_id: UUID,
    db: DbSession,
    user: CurrentUser,
    ref: str | None = Query(None, description="Git ref (branch name or SHA). Defaults to latest analyzed commit."),
) -> ArchitectureHealthResponse:
    """
    Get architecture health analysis for a repository.

    Supports commit-aware filtering via optional `ref` parameter.

    Includes:
    - Detected clusters with cohesion scores
    - Outliers (potential dead/misplaced code)
    - Coupling hotspots (god files)
    - Overall health score
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
        raise HTTPException(status_code=404, detail="Repository not found")

    try:
        # Resolve commit SHA (commit-centric by default)
        commit_sha, source = await _resolve_commit_sha(db, repository_id, user.id, ref)
        logger.debug(f"architecture-health: resolved ref={ref} -> sha={commit_sha} (source={source})")

        from app.services.cluster_analyzer import get_cluster_analyzer

        analyzer = get_cluster_analyzer()
        health = await analyzer.analyze(str(repository_id), commit_sha=commit_sha)

        return ArchitectureHealthResponse(
            overall_score=health.overall_score,
            clusters=[
                ClusterInfoResponse(
                    id=c.id,
                    name=c.name,
                    file_count=c.file_count,
                    chunk_count=c.chunk_count,
                    cohesion=c.cohesion,
                    top_files=c.top_files,
                    dominant_language=c.dominant_language,
                    status=c.status,
                )
                for c in health.clusters
            ],
            outliers=[
                OutlierInfoResponse(
                    file_path=o.file_path,
                    chunk_name=o.chunk_name,
                    chunk_type=o.chunk_type,
                    nearest_similarity=o.nearest_similarity,
                    nearest_file=o.nearest_file,
                    suggestion=o.suggestion,
                    confidence=o.confidence,
                    confidence_factors=o.confidence_factors,
                    tier=o.tier,
                )
                for o in health.outliers
            ],
            coupling_hotspots=[
                CouplingHotspotResponse(
                    file_path=h.file_path,
                    clusters_connected=h.clusters_connected,
                    cluster_names=h.cluster_names,
                    suggestion=h.suggestion,
                )
                for h in health.coupling_hotspots
            ],
            total_chunks=health.total_chunks,
            total_files=health.total_files,
            metrics=health.metrics,
        )

    except Exception as e:
        logger.error(f"Architecture health analysis failed: {e}")
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")


class OutliersResponse(BaseModel):
    """Response for outliers endpoint."""
    outliers: list[OutlierInfoResponse]
    total_outliers: int
    percentage: float


@router.get("/repositories/{repository_id}/outliers")
async def get_outliers(
    repository_id: UUID,
    db: DbSession,
    user: CurrentUser,
    ref: str | None = Query(None, description="Git ref (branch name or SHA). Defaults to latest analyzed commit."),
) -> OutliersResponse:
    """
    Get outliers (potential dead/misplaced code) for a repository.

    Supports commit-aware filtering via optional `ref` parameter.

    Outliers are code chunks that don't belong to any cluster,
    indicating they may be:
    - Dead code
    - Misplaced utilities
    - Orphaned features
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
        raise HTTPException(status_code=404, detail="Repository not found")

    try:
        # Resolve commit SHA (commit-centric by default)
        commit_sha, source = await _resolve_commit_sha(db, repository_id, user.id, ref)
        logger.debug(f"outliers: resolved ref={ref} -> sha={commit_sha} (source={source})")

        from app.services.cluster_analyzer import get_cluster_analyzer

        analyzer = get_cluster_analyzer()
        health = await analyzer.analyze(str(repository_id), commit_sha=commit_sha)

        return OutliersResponse(
            outliers=[
                OutlierInfoResponse(
                    file_path=o.file_path,
                    chunk_name=o.chunk_name,
                    chunk_type=o.chunk_type,
                    nearest_similarity=o.nearest_similarity,
                    nearest_file=o.nearest_file,
                    suggestion=o.suggestion,
                    confidence=o.confidence,
                    confidence_factors=o.confidence_factors,
                    tier=o.tier,
                )
                for o in health.outliers
            ],
            total_outliers=len(health.outliers),
            percentage=health.metrics.get("outlier_percentage", 0),
        )

    except Exception as e:
        logger.error(f"Outlier detection failed: {e}")
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")



# ============================================================================
# Placement Suggestion
# ============================================================================

class PlacementSuggestionResponse(BaseModel):
    """Response for placement suggestion."""
    current_location: str
    current_cluster: str | None
    suggested_cluster: str | None
    similar_files: list[RelatedCodeResult]
    suggestion: str | None


@router.get("/repositories/{repository_id}/suggest-placement")
async def suggest_placement(
    repository_id: UUID,
    db: DbSession,
    user: CurrentUser,
    file: str = Query(..., description="File path to analyze"),
    ref: str | None = Query(None, description="Git ref (branch name or SHA). Defaults to latest analyzed commit."),
) -> PlacementSuggestionResponse:
    """
    Suggest better placement for a file based on semantic similarity.

    Supports commit-aware filtering via optional `ref` parameter.

    Useful for:
    - Finding misplaced files
    - Reorganizing code structure
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
        raise HTTPException(status_code=404, detail="Repository not found")

    try:
        # Get related code first (pass ref for commit-awareness)
        related_response = await get_related_code(
            repository_id=repository_id,
            db=db,
            user=user,
            file=file,
            limit=10,
            ref=ref,
        )

        if not related_response.related:
            return PlacementSuggestionResponse(
                current_location=file,
                current_cluster=None,
                suggested_cluster=None,
                similar_files=[],
                suggestion="No similar code found to suggest placement",
            )

        # Analyze where similar files are located
        similar_dirs = {}
        for r in related_response.related:
            dir_path = "/".join(r.file_path.split("/")[:-1]) or "root"
            if dir_path not in similar_dirs:
                similar_dirs[dir_path] = []
            similar_dirs[dir_path].append(r.similarity)

        # Find best matching directory
        current_dir = "/".join(file.split("/")[:-1]) or "root"
        best_dir = max(similar_dirs.keys(), key=lambda d: sum(similar_dirs[d]) / len(similar_dirs[d]))

        # Generate suggestion
        if best_dir == current_dir:
            suggestion = "File is well-placed — similar code is in the same directory"
        else:
            avg_similarity = sum(similar_dirs[best_dir]) / len(similar_dirs[best_dir])
            if avg_similarity > 0.7:
                suggestion = f"Consider moving to {best_dir}/ — {avg_similarity:.0%} similar to code there"
            else:
                suggestion = f"File might fit better in {best_dir}/ based on semantic similarity"

        return PlacementSuggestionResponse(
            current_location=file,
            current_cluster=None,  # Would need cluster analysis
            suggested_cluster=best_dir,
            similar_files=related_response.related[:5],
            suggestion=suggestion,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Placement suggestion failed: {e}")
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")


# ============================================================================
# Similar Code Detection (Duplicates)
# ============================================================================

class SimilarCodeGroup(BaseModel):
    """A group of similar code chunks."""
    similarity: float
    suggestion: str
    chunks: list[dict]


class SimilarCodeResponse(BaseModel):
    """Response for similar code detection."""
    groups: list[SimilarCodeGroup]
    total_groups: int
    potential_loc_reduction: int


@router.get("/repositories/{repository_id}/similar-code")
async def find_similar_code(
    repository_id: UUID,
    db: DbSession,
    user: CurrentUser,
    threshold: float = Query(0.85, ge=0.5, le=0.99, description="Similarity threshold"),
    limit: int = Query(20, ge=1, le=100, description="Max groups to return"),
    ref: str | None = Query(None, description="Git ref (branch name or SHA). Defaults to latest analyzed commit."),
) -> SimilarCodeResponse:
    """
    Find groups of similar code (potential duplicates).

    Supports commit-aware filtering via optional `ref` parameter.

    Uses vector similarity to find code that is semantically similar,
    even if the syntax differs.
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
        raise HTTPException(status_code=404, detail="Repository not found")

    try:
        import numpy as np
        from sklearn.metrics.pairwise import cosine_similarity

        # Resolve commit SHA (commit-centric by default)
        commit_sha, source = await _resolve_commit_sha(db, repository_id, user.id, ref)
        logger.debug(f"similar-code: resolved ref={ref} -> sha={commit_sha} (source={source})")

        vs = _get_vector_store_service()

        # Fetch all vectors (commit-aware scroll)
        vectors = []
        payloads = []
        offset = None

        while True:
            results, new_offset = vs.scroll_vectors(
                repository_id=repository_id,
                commit_sha=commit_sha,
                limit=100,
                offset=offset,
                with_vectors=True,
            )

            for point in results:
                if point.vector:
                    vectors.append(point.vector)
                    payloads.append(point.payload or {})

            if new_offset is None:
                break
            offset = new_offset

        if len(vectors) < 2:
            return SimilarCodeResponse(groups=[], total_groups=0, potential_loc_reduction=0)

        # Compute pairwise similarities
        vectors_array = np.array(vectors)
        similarities = cosine_similarity(vectors_array)

        # Find groups above threshold
        groups = []
        used = set()

        for i in range(len(vectors)):
            if i in used:
                continue

            # Find all similar chunks
            similar_indices = np.where(similarities[i] >= threshold)[0]
            similar_indices = [j for j in similar_indices if j != i and j not in used]

            if similar_indices:
                group_indices = [i] + similar_indices
                avg_similarity = np.mean([similarities[i][j] for j in similar_indices])

                # Mark as used
                used.update(group_indices)

                # Build group
                chunks = []
                total_lines = 0
                for idx in group_indices:
                    p = payloads[idx]
                    chunks.append({
                        "file": p.get("file_path", ""),
                        "name": p.get("name", ""),
                        "lines": [p.get("line_start", 0), p.get("line_end", 0)],
                        "chunk_type": p.get("chunk_type", ""),
                    })
                    total_lines += p.get("line_count", 0) or (p.get("line_end", 0) - p.get("line_start", 0))

                groups.append(SimilarCodeGroup(
                    similarity=round(avg_similarity, 3),
                    suggestion="Extract to shared utility" if len(chunks) > 2 else "Consider consolidating",
                    chunks=chunks,
                ))

        # Sort by similarity and limit
        groups.sort(key=lambda g: g.similarity, reverse=True)
        groups = groups[:limit]

        # Estimate LOC reduction
        potential_loc = sum(
            sum(c.get("lines", [0, 0])[1] - c.get("lines", [0, 0])[0] for c in g.chunks[1:])
            for g in groups
        )

        return SimilarCodeResponse(
            groups=groups,
            total_groups=len(groups),
            potential_loc_reduction=potential_loc,
        )

    except Exception as e:
        logger.error(f"Similar code detection failed: {e}")
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")



# ============================================================================
# Refactoring Suggestions
# ============================================================================

class RefactoringSuggestion(BaseModel):
    """A refactoring suggestion."""
    type: str  # move_file, split_file, create_module, extract_utility
    file: str | None
    target: str | None
    reason: str
    impact: str  # low, medium, high
    details: dict | None = None


class RefactoringSuggestionsResponse(BaseModel):
    """Response for refactoring suggestions."""
    suggestions: list[RefactoringSuggestion]
    total: int


@router.get("/repositories/{repository_id}/refactoring-suggestions")
async def get_refactoring_suggestions(
    repository_id: UUID,
    db: DbSession,
    user: CurrentUser,
    ref: str | None = Query(None, description="Git ref (branch name or SHA). Defaults to latest analyzed commit."),
) -> RefactoringSuggestionsResponse:
    """
    Get refactoring suggestions based on semantic analysis.

    Supports commit-aware filtering via optional `ref` parameter.

    Combines cluster analysis, similarity detection, and complexity metrics
    to suggest actionable refactoring opportunities.
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
        raise HTTPException(status_code=404, detail="Repository not found")

    try:
        # Resolve commit SHA (commit-centric by default)
        commit_sha, source = await _resolve_commit_sha(db, repository_id, user.id, ref)
        logger.debug(f"refactoring-suggestions: resolved ref={ref} -> sha={commit_sha} (source={source})")

        from app.services.cluster_analyzer import get_cluster_analyzer

        suggestions = []

        # Get architecture health (commit-aware)
        analyzer = get_cluster_analyzer()
        health = await analyzer.analyze(str(repository_id), commit_sha=commit_sha)

        # Suggestion 1: Split god files (coupling hotspots)
        for hotspot in health.coupling_hotspots:
            suggestions.append(RefactoringSuggestion(
                type="split_file",
                file=hotspot.file_path,
                target=None,
                reason=f"Bridges {hotspot.clusters_connected} clusters — too many responsibilities",
                impact="high",
                details={"clusters": hotspot.cluster_names},
            ))

        # Suggestion 2: Move misplaced files (outliers with high similarity to a cluster)
        for outlier in health.outliers:
            if outlier.nearest_similarity > 0.5 and outlier.nearest_file:
                target_dir = "/".join(outlier.nearest_file.split("/")[:-1])
                suggestions.append(RefactoringSuggestion(
                    type="move_file",
                    file=outlier.file_path,
                    target=target_dir,
                    reason=f"{outlier.nearest_similarity:.0%} similar to {outlier.nearest_file}",
                    impact="medium",
                ))

        # Suggestion 3: Reorganize scattered clusters
        for cluster in health.clusters:
            if cluster.status == "scattered" and cluster.file_count > 3:
                suggestions.append(RefactoringSuggestion(
                    type="create_module",
                    file=None,
                    target=cluster.name,
                    reason=f"Low cohesion ({cluster.cohesion:.0%}) — files are unrelated",
                    impact="medium",
                    details={"files": cluster.top_files},
                ))

        # Get similar code for extract_utility suggestions (commit-aware)
        similar_response = await find_similar_code(
            repository_id=repository_id,
            db=db,
            user=user,
            threshold=0.85,
            limit=5,
            ref=ref,
        )

        for group in similar_response.groups:
            if len(group.chunks) >= 3:
                files = [c.get("file", "") for c in group.chunks]
                suggestions.append(RefactoringSuggestion(
                    type="extract_utility",
                    file=None,
                    target="shared/utils",
                    reason=f"{len(group.chunks)} similar functions ({group.similarity:.0%} similar)",
                    impact="low",
                    details={"files": files},
                ))

        # Sort by impact
        impact_order = {"high": 0, "medium": 1, "low": 2}
        suggestions.sort(key=lambda s: impact_order.get(s.impact, 3))

        return RefactoringSuggestionsResponse(
            suggestions=suggestions[:20],
            total=len(suggestions),
        )

    except Exception as e:
        logger.error(f"Refactoring suggestions failed: {e}")
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")


# ============================================================================
# Technical Debt Heatmap
# ============================================================================

class TechDebtHotspot(BaseModel):
    """A technical debt hotspot."""
    file_path: str
    complexity: int | None
    cohesion: float | None
    bridges_clusters: int
    risk: str  # critical, high, medium, low
    suggestion: str


class TechDebtByCluster(BaseModel):
    """Tech debt summary by cluster."""
    cluster: str
    avg_complexity: float
    cohesion: float
    health: str


class TechDebtHeatmapResponse(BaseModel):
    """Response for tech debt heatmap."""
    debt_score: int
    hotspots: list[TechDebtHotspot]
    by_cluster: list[TechDebtByCluster]


@router.get("/repositories/{repository_id}/tech-debt-heatmap")
async def get_tech_debt_heatmap(
    repository_id: UUID,
    db: DbSession,
    user: CurrentUser,
    ref: str | None = Query(None, description="Git ref (branch name or SHA). Defaults to latest analyzed commit."),
) -> TechDebtHeatmapResponse:
    """
    Get technical debt heatmap combining complexity and architecture metrics.

    Supports commit-aware filtering via optional `ref` parameter.

    Identifies files that are both complex and poorly integrated,
    making them high-priority refactoring targets.
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
        raise HTTPException(status_code=404, detail="Repository not found")

    try:
        # Resolve commit SHA (commit-centric by default)
        commit_sha, source = await _resolve_commit_sha(db, repository_id, user.id, ref)
        logger.debug(f"tech-debt-heatmap: resolved ref={ref} -> sha={commit_sha} (source={source})")

        from app.services.cluster_analyzer import get_cluster_analyzer

        analyzer = get_cluster_analyzer()
        health = await analyzer.analyze(str(repository_id), commit_sha=commit_sha)

        hotspots = []

        # Add coupling hotspots as critical
        for hotspot in health.coupling_hotspots:
            hotspots.append(TechDebtHotspot(
                file_path=hotspot.file_path,
                complexity=None,  # Would need to fetch from analysis
                cohesion=None,
                bridges_clusters=hotspot.clusters_connected,
                risk="critical" if hotspot.clusters_connected >= 4 else "high",
                suggestion=hotspot.suggestion,
            ))

        # Add outliers as medium risk
        for outlier in health.outliers[:10]:
            if outlier.nearest_similarity < 0.4:
                hotspots.append(TechDebtHotspot(
                    file_path=outlier.file_path,
                    complexity=None,
                    cohesion=outlier.nearest_similarity,
                    bridges_clusters=0,
                    risk="medium",
                    suggestion=outlier.suggestion,
                ))

        # Build by-cluster summary
        by_cluster = []
        for cluster in health.clusters:
            health_status = "good" if cluster.cohesion >= 0.7 else "moderate" if cluster.cohesion >= 0.5 else "poor"
            by_cluster.append(TechDebtByCluster(
                cluster=cluster.name,
                avg_complexity=0,  # Would need complexity data
                cohesion=cluster.cohesion,
                health=health_status,
            ))

        # Calculate debt score (inverse of health score)
        debt_score = 100 - health.overall_score

        return TechDebtHeatmapResponse(
            debt_score=debt_score,
            hotspots=hotspots,
            by_cluster=by_cluster,
        )

    except Exception as e:
        logger.error(f"Tech debt heatmap failed: {e}")
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")



# ============================================================================
# Code Style Consistency
# ============================================================================

class StyleIssue(BaseModel):
    """A style consistency issue."""
    type: str  # error_handling, naming, logging, patterns
    message: str
    reference_file: str | None = None
    reference_lines: list[int] | None = None


class StyleConsistencyResponse(BaseModel):
    """Response for style consistency check."""
    file: str
    overall_consistency: float
    analysis: dict
    issues: list[StyleIssue]
    suggestions: list[str]


@router.get("/repositories/{repository_id}/style-consistency")
async def check_style_consistency(
    repository_id: UUID,
    db: DbSession,
    user: CurrentUser,
    file: str = Query(..., description="File path to check"),
    ref: str | None = Query(None, description="Git ref (branch name or SHA). Defaults to latest analyzed commit."),
) -> StyleConsistencyResponse:
    """
    Check code style consistency for a file.

    Supports commit-aware filtering via optional `ref` parameter.

    Compares the file's patterns against the rest of the codebase
    to detect style drift and inconsistencies.
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
        raise HTTPException(status_code=404, detail="Repository not found")

    try:
        import numpy as np
        from sklearn.metrics.pairwise import cosine_similarity

        # Resolve commit SHA (commit-centric by default)
        commit_sha, source = await _resolve_commit_sha(db, repository_id, user.id, ref)
        logger.debug(f"style-consistency: resolved ref={ref} -> sha={commit_sha} (source={source})")

        vs = _get_vector_store_service()

        # Get file's embeddings (commit-aware scroll)
        # First scroll to get file vectors
        file_results = []
        offset = None
        while True:
            results, new_offset = vs.scroll_vectors(
                repository_id=repository_id,
                commit_sha=commit_sha,
                limit=100,
                offset=offset,
                with_vectors=True,
            )
            for p in results:
                if p.payload and p.payload.get("file_path") == file:
                    file_results.append(p)
            if new_offset is None or len(file_results) >= 20:
                break
            offset = new_offset

        if not file_results:
            raise HTTPException(status_code=404, detail=f"No embeddings found for file: {file}")

        file_vectors = np.array([p.vector for p in file_results if p.vector])
        if len(file_vectors) == 0:
            raise HTTPException(status_code=404, detail="No vectors found for file")

        file_avg = np.mean(file_vectors, axis=0)

        # Get all other embeddings grouped by directory (commit-aware scroll)
        all_results = []
        offset = None
        while True:
            results, new_offset = vs.scroll_vectors(
                repository_id=repository_id,
                commit_sha=commit_sha,
                limit=100,
                offset=offset,
                with_vectors=True,
            )
            for p in results:
                if p.payload and p.payload.get("file_path") != file:
                    all_results.append(p)
            if new_offset is None or len(all_results) >= 500:
                break
            offset = new_offset

        # Group by directory
        dir_vectors = {}
        for point in all_results:
            if not point.vector:
                continue
            dir_path = "/".join(point.payload.get("file_path", "").split("/")[:-1]) or "root"
            if dir_path not in dir_vectors:
                dir_vectors[dir_path] = []
            dir_vectors[dir_path].append(point.vector)

        # Calculate similarity to each directory
        analysis = {}
        for dir_path, vectors in dir_vectors.items():
            if vectors:
                dir_avg = np.mean(vectors, axis=0)
                similarity = cosine_similarity([file_avg], [dir_avg])[0][0]
                analysis[f"similarity_to_{dir_path}"] = round(float(similarity), 3)

        # Overall consistency is similarity to the file's own directory
        file_dir = "/".join(file.split("/")[:-1]) or "root"
        overall = analysis.get(f"similarity_to_{file_dir}", 0.5)

        # Generate issues based on low similarity
        issues = []
        suggestions = []

        if overall < 0.6:
            issues.append(StyleIssue(
                type="patterns",
                message=f"Code patterns differ from other files in {file_dir}/",
            ))
            suggestions.append(f"Review other files in {file_dir}/ for consistent patterns")

        # Find most similar directory if different from current
        if analysis:
            best_dir = max(analysis.keys(), key=lambda k: analysis[k])
            best_similarity = analysis[best_dir]
            best_dir_name = best_dir.replace("similarity_to_", "")

            if best_dir_name != file_dir and best_similarity > overall + 0.1:
                issues.append(StyleIssue(
                    type="placement",
                    message=f"Code style is more similar to {best_dir_name}/ ({best_similarity:.0%}) than {file_dir}/ ({overall:.0%})",
                ))
                suggestions.append(f"Consider if this file belongs in {best_dir_name}/")

        return StyleConsistencyResponse(
            file=file,
            overall_consistency=round(float(overall), 3),
            analysis=analysis,
            issues=issues,
            suggestions=suggestions,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Style consistency check failed: {e}")
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")


# ============================================================================
# Embedding Status (Legacy Endpoint - DEPRECATED)
# ============================================================================

class EmbeddingStatusResponse(BaseModel):
    """Response for embedding status."""
    repository_id: str
    status: str  # pending, running, completed, error, none
    stage: str | None
    progress: int
    message: str | None
    chunks_processed: int
    vectors_stored: int
    analysis_id: str | None = None  # Analysis that triggered these embeddings


@router.get("/repositories/{repository_id}/embedding-status")
async def get_embedding_status(
    repository_id: UUID,
    db: DbSession,
    user: CurrentUser,
) -> EmbeddingStatusResponse:
    """
    Get current embedding generation status for a repository.

    DEPRECATED: Use GET /analyses/{id}/full-status instead.
    This endpoint is maintained for backward compatibility.

    Returns the progress of any ongoing embedding generation,
    or the last known status if completed.
    """
    # Log deprecation warning (Requirements 8.3)
    logger.warning(
        f"DEPRECATED: GET /repositories/{repository_id}/embedding-status called. "
        "Use GET /analyses/{{id}}/full-status instead."
    )

    # Verify repository access
    result = await db.execute(
        select(Repository).where(
            Repository.id == repository_id,
            Repository.owner_id == user.id,
        )
    )
    repository = result.scalar_one_or_none()
    if not repository:
        raise HTTPException(status_code=404, detail="Repository not found")

    # Find the most recent analysis for this repository (Requirements 8.3)
    from app.models.analysis import Analysis

    most_recent_analysis_result = await db.execute(
        select(Analysis)
        .where(Analysis.repository_id == repository_id)
        .order_by(Analysis.created_at.desc())
        .limit(1)
    )
    analysis = most_recent_analysis_result.scalar_one_or_none()

    if not analysis:
        # No analysis exists for this repository
        return EmbeddingStatusResponse(
            repository_id=str(repository_id),
            status="none",
            stage=None,
            progress=0,
            message="No embeddings generated yet",
            chunks_processed=0,
            vectors_stored=0,
            analysis_id=None,
        )

    # Read embeddings status from PostgreSQL (single source of truth)
    embeddings_status = analysis.embeddings_status

    # Map 'none' status to check if we should report 'none' or look for existing vectors
    if embeddings_status == "none":
        # Check if vectors exist in Qdrant for backward compatibility
        # This handles legacy data before the migration
        try:
            qdrant = get_qdrant_client()
            count = qdrant.count(
                collection_name=COLLECTION_NAME,
                count_filter={
                    "must": [
                        {"key": "repository_id", "match": {"value": str(repository_id)}}
                    ]
                }
            )
            if count.count > 0:
                # Vectors exist but status is 'none' - legacy data
                return EmbeddingStatusResponse(
                    repository_id=str(repository_id),
                    status="completed",
                    stage="completed",
                    progress=100,
                    message=f"{count.count} vectors available",
                    chunks_processed=count.count,
                    vectors_stored=count.count,
                    analysis_id=str(analysis.id),
                )
        except Exception as e:
            logger.warning(f"Failed to check Qdrant for legacy vectors: {e}")

        return EmbeddingStatusResponse(
            repository_id=str(repository_id),
            status="none",
            stage=None,
            progress=0,
            message="No embeddings generated yet",
            chunks_processed=0,
            vectors_stored=0,
            analysis_id=str(analysis.id),
        )

    # Return status from PostgreSQL in the existing format
    # Map embeddings_status to the legacy status values
    status_mapping = {
        "pending": "pending",
        "running": "running",
        "completed": "completed",
        "failed": "error",  # Legacy format used 'error' instead of 'failed'
    }

    legacy_status = status_mapping.get(embeddings_status, embeddings_status)

    # Build message based on status
    if embeddings_status == "completed":
        message = f"{analysis.vectors_count} vectors available"
    elif embeddings_status == "failed":
        message = analysis.embeddings_error or "Embedding generation failed"
    else:
        message = analysis.embeddings_message

    return EmbeddingStatusResponse(
        repository_id=str(repository_id),
        status=legacy_status,
        stage=analysis.embeddings_stage,
        progress=analysis.embeddings_progress,
        message=message,
        chunks_processed=analysis.vectors_count,  # Use vectors_count as proxy
        vectors_stored=analysis.vectors_count,
        analysis_id=str(analysis.id),
    )
