"""Analysis schemas."""

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel

from app.schemas.common import BaseSchema


class AnalysisStatus(str, Enum):
    """Analysis status enum for schemas."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class TriggerType(str, Enum):
    """Trigger type enum for schemas."""
    SCHEDULED = "scheduled"
    WEBHOOK = "webhook"
    MANUAL = "manual"


class AnalysisCreate(BaseModel):
    """Analysis creation request."""

    commit_sha: str | None = None


class RepositoryInfo(BaseSchema):
    """Repository info in analysis response."""

    id: UUID
    full_name: str


class IssuesSummary(BaseModel):
    """Issues summary by severity."""

    critical: int = 0
    high: int = 0
    medium: int = 0
    low: int = 0


class AnalysisSummary(BaseSchema):
    """Analysis list response."""

    id: UUID
    commit_sha: str
    status: AnalysisStatus
    trigger_type: TriggerType
    vci_score: float | None = None
    issues_found: int = 0
    started_at: datetime | None = None
    completed_at: datetime | None = None


class MetricsComplexity(BaseModel):
    """Complexity metrics."""

    avg: float
    max: int
    files_above_threshold: int


class MetricsDuplication(BaseModel):
    """Duplication metrics."""

    ratio: float
    total_lines: int = 0
    duplicate_blocks: int


class MetricsHeuristics(BaseModel):
    """Hard heuristics metrics."""

    long_functions: int = 0
    long_files: int = 0
    low_comment_density: int = 0


class MetricsArchitecture(BaseModel):
    """Architecture metrics."""

    consistency_score: float
    violations: list[str] = []


class AnalysisMetrics(BaseModel):
    """Full analysis metrics."""

    cyclomatic_complexity: MetricsComplexity | None = None
    duplication: MetricsDuplication | None = None
    hard_heuristics: MetricsHeuristics | None = None
    architecture: MetricsArchitecture | None = None


class AnalysisResponse(BaseSchema):
    """Analysis creation response."""

    id: UUID
    status: AnalysisStatus
    created_at: datetime


class AnalysisDetail(BaseSchema):
    """Analysis detail response."""

    id: UUID
    repository: RepositoryInfo
    commit_sha: str
    status: AnalysisStatus
    trigger_type: TriggerType
    vci_score: float | None = None
    metrics: AnalysisMetrics | None = None
    issues_summary: IssuesSummary
    report_url: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None


# =============================================================================
# Semantic Cache Schemas
# =============================================================================


class ClusterInfoCache(BaseModel):
    """Cluster information for cache."""

    id: int
    name: str
    file_count: int
    chunk_count: int
    cohesion: float
    top_files: list[str]
    dominant_language: str | None
    status: str


class OutlierInfoCache(BaseModel):
    """Outlier information for cache."""

    file_path: str
    chunk_name: str | None
    chunk_type: str | None
    nearest_similarity: float
    nearest_file: str | None
    suggestion: str
    confidence: float = 0.5
    confidence_factors: list[str] = []
    tier: str = "recommended"


class CouplingHotspotCache(BaseModel):
    """Coupling hotspot information for cache."""

    file_path: str
    clusters_connected: int
    cluster_names: list[str]
    suggestion: str


class ArchitectureHealthCache(BaseModel):
    """Architecture health data for cache."""

    overall_score: int
    clusters: list[ClusterInfoCache]
    outliers: list[OutlierInfoCache]
    coupling_hotspots: list[CouplingHotspotCache]
    total_chunks: int
    total_files: int
    metrics: dict[str, Any]


class SemanticCacheResponse(BaseModel):
    """Response for semantic cache endpoint."""

    analysis_id: UUID
    commit_sha: str
    architecture_health: ArchitectureHealthCache | None = None
    computed_at: datetime | None = None
    is_cached: bool


# =============================================================================
# Full Status Response Schema (Requirements 4.1, 4.2, 4.3)
# =============================================================================


class EmbeddingsStatus(str, Enum):
    """Embeddings status enum for schemas."""
    NONE = "none"
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class SemanticCacheStatus(str, Enum):
    """Semantic cache status enum for schemas."""
    NONE = "none"
    PENDING = "pending"
    COMPUTING = "computing"
    COMPLETED = "completed"
    FAILED = "failed"


class AnalysisFullStatusResponse(BaseModel):
    """
    Full analysis status response combining all state information.
    
    This schema provides a single source of truth for frontend polling,
    including analysis status, embeddings status, semantic cache status,
    and computed overall progress.
    
    **Feature: progress-tracking-refactor**
    **Validates: Requirements 4.1, 4.2, 4.3**
    """

    # Identity fields
    analysis_id: str
    repository_id: str
    commit_sha: str

    # Analysis status
    analysis_status: AnalysisStatus
    vci_score: float | None = None
    grade: str | None = None

    # Embeddings status (Requirements 4.1)
    embeddings_status: EmbeddingsStatus
    embeddings_progress: int
    embeddings_stage: str | None = None
    embeddings_message: str | None = None
    embeddings_error: str | None = None
    vectors_count: int

    # Semantic cache status (Requirements 4.1)
    semantic_cache_status: SemanticCacheStatus
    has_semantic_cache: bool

    # Timestamps for polling optimization
    state_updated_at: datetime
    embeddings_started_at: datetime | None = None
    embeddings_completed_at: datetime | None = None

    # Computed fields (Requirements 4.2, 4.3)
    overall_progress: int
    overall_stage: str
    is_complete: bool


def compute_overall_progress(
    analysis_status: str,
    embeddings_status: str,
    embeddings_progress: int,
    semantic_cache_status: str,
) -> int:
    """
    Compute overall progress from individual phase statuses.
    
    Progress breakdown (Requirements 3.4, 4.2):
    - Analysis phase: 0-40%
    - Embeddings phase: 40-90%
    - Semantic cache phase: 90-100%
    
    Args:
        analysis_status: Current analysis status
        embeddings_status: Current embeddings status
        embeddings_progress: Embeddings progress percentage (0-100)
        semantic_cache_status: Current semantic cache status
        
    Returns:
        Overall progress percentage (0-100)
        
    **Feature: progress-tracking-refactor, Property 7: Overall Progress Computation**
    **Validates: Requirements 3.4, 4.2, 4.3**
    """
    # Phase 1: Analysis (0-40%)
    if analysis_status == "pending":
        return 0
    elif analysis_status == "running":
        return 20  # Mid-point of analysis phase
    elif analysis_status == "failed":
        return 0  # Failed analysis = 0 progress
    # analysis_status == "completed" -> continue to embeddings phase

    # Phase 2: Embeddings (40-90%)
    if embeddings_status == "none":
        return 40  # Analysis complete, embeddings not started
    elif embeddings_status == "pending":
        return 40  # Waiting for embeddings to start
    elif embeddings_status == "running":
        # Scale embeddings_progress (0-100) to (40-90)
        # embeddings_progress=0 -> 40, embeddings_progress=100 -> 90
        return 40 + int(embeddings_progress * 0.5)
    elif embeddings_status == "failed":
        return 40  # Embeddings failed, stuck at analysis complete
    # embeddings_status == "completed" -> continue to semantic cache phase

    # Phase 3: Semantic Cache (90-100%)
    if semantic_cache_status == "none":
        return 90  # Embeddings complete, semantic cache not started
    elif semantic_cache_status == "pending":
        return 90  # Waiting for semantic cache to start
    elif semantic_cache_status == "computing":
        return 95  # Mid-point of semantic cache phase
    elif semantic_cache_status == "failed":
        return 90  # Semantic cache failed, stuck at embeddings complete
    elif semantic_cache_status == "completed":
        return 100  # All phases complete

    return 0  # Fallback


def compute_overall_stage(
    analysis_status: str,
    embeddings_status: str,
    embeddings_stage: str | None,
    semantic_cache_status: str,
) -> str:
    """
    Compute human-readable overall stage description.
    
    Args:
        analysis_status: Current analysis status
        embeddings_status: Current embeddings status
        embeddings_stage: Current embeddings stage (if running)
        semantic_cache_status: Current semantic cache status
        
    Returns:
        Human-readable stage description
        
    **Feature: progress-tracking-refactor**
    **Validates: Requirements 4.3**
    """
    # Analysis phase
    if analysis_status == "pending":
        return "Waiting for analysis to start"
    elif analysis_status == "running":
        return "Analyzing repository"
    elif analysis_status == "failed":
        return "Analysis failed"

    # Embeddings phase (analysis completed)
    if embeddings_status == "none":
        return "Analysis complete"
    elif embeddings_status == "pending":
        return "Waiting for embedding generation"
    elif embeddings_status == "running":
        if embeddings_stage:
            stage_descriptions = {
                "initializing": "Initializing embedding generation",
                "chunking": "Chunking code files",
                "embedding": "Generating embeddings",
                "indexing": "Indexing vectors",
                "completed": "Embedding generation complete",
            }
            return stage_descriptions.get(embeddings_stage, f"Generating embeddings ({embeddings_stage})")
        return "Generating embeddings"
    elif embeddings_status == "failed":
        return "Embedding generation failed"

    # Semantic cache phase (embeddings completed)
    if semantic_cache_status == "none":
        return "Embeddings complete"
    elif semantic_cache_status == "pending":
        return "Waiting for semantic analysis"
    elif semantic_cache_status == "computing":
        return "Computing semantic analysis"
    elif semantic_cache_status == "failed":
        return "Semantic analysis failed"
    elif semantic_cache_status == "completed":
        return "All processing complete"

    return "Unknown state"


def compute_is_complete(
    analysis_status: str,
    embeddings_status: str,
    semantic_cache_status: str,
) -> bool:
    """
    Determine if all processing phases are complete.
    
    Args:
        analysis_status: Current analysis status
        embeddings_status: Current embeddings status
        semantic_cache_status: Current semantic cache status
        
    Returns:
        True if all phases are completed, False otherwise
        
    **Feature: progress-tracking-refactor**
    **Validates: Requirements 4.2**
    """
    return (
        analysis_status == "completed"
        and embeddings_status == "completed"
        and semantic_cache_status == "completed"
    )
