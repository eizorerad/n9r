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
    GENERATING_INSIGHTS = "generating_insights"
    COMPLETED = "completed"
    FAILED = "failed"


class AIScanStatus(str, Enum):
    """AI scan status enum for schemas.

    **Feature: ai-scan-progress-fix**
    **Validates: Requirements 2.3**
    """
    NONE = "none"
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class AnalysisFullStatusResponse(BaseModel):
    """
    Full analysis status response combining all state information.

    This schema provides a single source of truth for frontend polling,
    including analysis status, embeddings status, semantic cache status,
    AI scan status, and computed overall progress.

    **Feature: progress-tracking-refactor, ai-scan-progress-fix, parallel-analysis-pipeline**
    **Validates: Requirements 4.1, 4.2, 4.3, 2.3, 2.1**
    """

    # Identity fields
    analysis_id: str
    repository_id: str
    commit_sha: str

    # Analysis status
    analysis_status: AnalysisStatus
    analysis_progress: int = 0  # Static analysis progress (0-100) for parallel tracking
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

    # AI Scan status (Requirements 2.3)
    # **Feature: ai-scan-progress-fix**
    ai_scan_status: AIScanStatus
    ai_scan_progress: int
    ai_scan_stage: str | None = None
    ai_scan_message: str | None = None
    ai_scan_error: str | None = None
    has_ai_scan_cache: bool
    ai_scan_started_at: datetime | None = None
    ai_scan_completed_at: datetime | None = None

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
    ai_scan_status: str = "none",
    ai_scan_progress: int = 0,
) -> int:
    """
    Compute overall progress from individual phase statuses.

    Progress breakdown (Requirements 6.1):
    - Analysis phase: 0-30%
    - Embeddings phase: 30-60%
    - Semantic cache phase: 60-80%
    - AI scan phase: 80-100%

    Args:
        analysis_status: Current analysis status
        embeddings_status: Current embeddings status
        embeddings_progress: Embeddings progress percentage (0-100)
        semantic_cache_status: Current semantic cache status
        ai_scan_status: Current AI scan status (default: "none")
        ai_scan_progress: AI scan progress percentage (0-100, default: 0)

    Returns:
        Overall progress percentage (0-100)

    **Feature: progress-tracking-refactor, ai-scan-progress-fix**
    **Property 5: Progress Calculation Bounds**
    **Validates: Requirements 3.4, 4.2, 4.3, 6.1**
    """
    # Phase 1: Analysis (0-30%)
    if analysis_status == "pending":
        return 0
    elif analysis_status == "running":
        return 15  # Mid-point of analysis phase
    elif analysis_status == "failed":
        return 0  # Failed analysis = 0 progress
    # analysis_status == "completed" -> continue to embeddings phase

    # Phase 2: Embeddings (30-60%)
    if embeddings_status == "none":
        return 30  # Analysis complete, embeddings not started
    elif embeddings_status == "pending":
        return 30  # Waiting for embeddings to start
    elif embeddings_status == "running":
        # Scale embeddings_progress (0-100) to (30-60)
        # embeddings_progress=0 -> 30, embeddings_progress=100 -> 60
        return 30 + int(embeddings_progress * 0.3)
    elif embeddings_status == "failed":
        return 30  # Embeddings failed, stuck at analysis complete
    # embeddings_status == "completed" -> continue to semantic cache phase

    # Phase 3: Semantic Cache (60-80%)
    if semantic_cache_status == "none":
        return 60  # Embeddings complete, semantic cache not started
    elif semantic_cache_status == "pending":
        return 60  # Waiting for semantic cache to start
    elif semantic_cache_status == "computing":
        return 70  # Mid-point of semantic cache phase
    elif semantic_cache_status == "failed":
        return 60  # Semantic cache failed, stuck at embeddings complete
    # semantic_cache_status == "completed" -> continue to AI scan phase

    # Phase 4: AI Scan (80-100%)
    if ai_scan_status == "none":
        return 80  # Semantic cache complete, AI scan not started
    elif ai_scan_status == "pending":
        return 80  # Waiting for AI scan to start
    elif ai_scan_status == "running":
        # Scale ai_scan_progress (0-100) to (80-100)
        # ai_scan_progress=0 -> 80, ai_scan_progress=100 -> 100
        return 80 + int(ai_scan_progress * 0.2)
    elif ai_scan_status == "failed":
        return 80  # AI scan failed, stuck at semantic cache complete
    elif ai_scan_status in ("completed", "skipped"):
        return 100  # All phases complete

    return 0  # Fallback


def compute_overall_stage(
    analysis_status: str,
    embeddings_status: str,
    embeddings_stage: str | None,
    semantic_cache_status: str,
    ai_scan_status: str = "none",
    ai_scan_stage: str | None = None,
) -> str:
    """
    Compute human-readable overall stage description.

    Args:
        analysis_status: Current analysis status
        embeddings_status: Current embeddings status
        embeddings_stage: Current embeddings stage (if running)
        semantic_cache_status: Current semantic cache status
        ai_scan_status: Current AI scan status (default: "none")
        ai_scan_stage: Current AI scan stage (if running)

    Returns:
        Human-readable stage description

    **Feature: progress-tracking-refactor, ai-scan-progress-fix**
    **Validates: Requirements 4.3, 6.2**
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
    # semantic_cache_status == "completed" -> continue to AI scan phase

    # AI scan phase (semantic cache completed)
    if ai_scan_status == "none":
        return "Semantic analysis complete"
    elif ai_scan_status == "pending":
        return "Waiting for AI scan to start"
    elif ai_scan_status == "running":
        if ai_scan_stage:
            stage_descriptions = {
                "initializing": "Initializing AI scan",
                "cloning": "Cloning repository for AI scan",
                "generating_view": "Generating repository view",
                "scanning": "Running AI code analysis",
                "merging": "Merging AI scan results",
                "investigating": "Investigating detected issues",
                "completed": "AI scan complete",
            }
            return stage_descriptions.get(ai_scan_stage, f"Running AI scan ({ai_scan_stage})")
        return "Running AI scan"
    elif ai_scan_status == "failed":
        return "AI scan failed"
    elif ai_scan_status == "skipped":
        return "All processing complete (AI scan skipped)"
    elif ai_scan_status == "completed":
        return "All processing complete"

    return "Unknown state"


def compute_is_complete(
    analysis_status: str,
    embeddings_status: str,
    semantic_cache_status: str,
    ai_scan_status: str = "none",
) -> bool:
    """
    Determine if all processing phases are complete.

    Args:
        analysis_status: Current analysis status
        embeddings_status: Current embeddings status
        semantic_cache_status: Current semantic cache status
        ai_scan_status: Current AI scan status (default: "none")

    Returns:
        True if all phases are completed (including AI scan completed or skipped), False otherwise

    **Feature: progress-tracking-refactor, ai-scan-progress-fix**
    **Validates: Requirements 4.2, 6.1**
    """
    return (
        analysis_status == "completed"
        and embeddings_status == "completed"
        and semantic_cache_status == "completed"
        and ai_scan_status in ("completed", "skipped")
    )


# =============================================================================
# Parallel Progress Calculation Functions
# =============================================================================


def compute_is_complete_parallel(
    analysis_status: str,
    embeddings_status: str,
    semantic_cache_status: str,
    ai_scan_status: str,
) -> bool:
    """
    Determine if all parallel processing tracks are complete.

    All three tracks must be in a terminal state (completed, failed, or skipped).
    This allows partial results when one track fails but others succeed.

    Args:
        analysis_status: Current static analysis status
        embeddings_status: Current embeddings status
        semantic_cache_status: Current semantic cache status
        ai_scan_status: Current AI scan status

    Returns:
        True if all tracks are in terminal states, False otherwise

    **Feature: parallel-analysis-pipeline**
    **Property 8: Terminal State Completion**
    **Validates: Requirements 4.1, 4.2, 4.3, 4.4**
    """
    terminal_states = ("completed", "failed", "skipped")

    return (
        analysis_status in terminal_states and
        embeddings_status in terminal_states and
        semantic_cache_status in terminal_states and
        ai_scan_status in terminal_states
    )


def compute_overall_stage_parallel(
    analysis_status: str,
    embeddings_status: str,
    embeddings_stage: str | None,
    semantic_cache_status: str,
    ai_scan_status: str,
    ai_scan_stage: str | None,
) -> str:
    """
    Compute human-readable overall stage description for parallel tracks.

    Shows all running tracks with bullet separator (•).
    Shows completed tracks with checkmark (✓).
    Shows failed tracks with cross (✗).

    Args:
        analysis_status: Current static analysis status
        embeddings_status: Current embeddings status
        embeddings_stage: Current embeddings stage (if running)
        semantic_cache_status: Current semantic cache status
        ai_scan_status: Current AI scan status
        ai_scan_stage: Current AI scan stage (if running)

    Returns:
        Human-readable stage description

    **Feature: parallel-analysis-pipeline**
    **Property 7: Combined Stage Description**
    **Validates: Requirements 3.1, 3.2, 3.3**
    """
    terminal_states = ("completed", "failed", "skipped")
    running_parts = []
    completed_parts = []
    failed_parts = []

    # Track A: Static Analysis
    if analysis_status == "pending":
        running_parts.append("Static Analysis pending")
    elif analysis_status == "running":
        running_parts.append("Analyzing repository")
    elif analysis_status == "completed":
        completed_parts.append("Static Analysis ✓")
    elif analysis_status == "failed":
        failed_parts.append("Static Analysis ✗")

    # Track B: Embeddings + Semantic Cache
    if embeddings_status == "pending":
        running_parts.append("Embeddings pending")
    elif embeddings_status == "running":
        if embeddings_stage:
            stage_descriptions = {
                "initializing": "Initializing embeddings",
                "chunking": "Chunking code files",
                "embedding": "Generating embeddings",
                "indexing": "Indexing vectors",
            }
            running_parts.append(stage_descriptions.get(embeddings_stage, f"Embeddings ({embeddings_stage})"))
        else:
            running_parts.append("Generating embeddings")
    elif embeddings_status == "completed":
        # Check semantic cache status
        if semantic_cache_status == "pending":
            running_parts.append("Semantic analysis pending")
        elif semantic_cache_status == "computing":
            running_parts.append("Computing semantic analysis")
        elif semantic_cache_status == "completed":
            completed_parts.append("Embeddings ✓")
        elif semantic_cache_status == "failed":
            failed_parts.append("Semantic analysis ✗")
        else:
            completed_parts.append("Embeddings ✓")
    elif embeddings_status == "failed":
        failed_parts.append("Embeddings ✗")

    # Track C: AI Scan
    if ai_scan_status == "pending":
        running_parts.append("AI Scan pending")
    elif ai_scan_status == "running":
        if ai_scan_stage:
            stage_descriptions = {
                "initializing": "Initializing AI scan",
                "cloning": "Cloning for AI scan",
                "generating_view": "Generating repo view",
                "scanning": "Running AI analysis",
                "merging": "Merging AI results",
                "investigating": "Investigating issues",
            }
            running_parts.append(stage_descriptions.get(ai_scan_stage, f"AI Scan ({ai_scan_stage})"))
        else:
            running_parts.append("Running AI scan")
    elif ai_scan_status == "completed":
        completed_parts.append("AI Scan ✓")
    elif ai_scan_status == "failed":
        failed_parts.append("AI Scan ✗")
    elif ai_scan_status == "skipped":
        completed_parts.append("AI Scan skipped")

    # Build the final description
    all_terminal = (
        analysis_status in terminal_states and
        embeddings_status in terminal_states and
        semantic_cache_status in terminal_states and
        ai_scan_status in terminal_states
    )

    if all_terminal:
        # All tracks complete - show summary
        if failed_parts:
            return f"Completed with failures: {' • '.join(failed_parts)}"
        return "All processing complete"

    # Show running tracks first, then completed
    parts = []
    if running_parts:
        parts.extend(running_parts)
    if completed_parts:
        parts.extend(completed_parts)
    if failed_parts:
        parts.extend(failed_parts)

    if parts:
        return " • ".join(parts)

    return "Initializing parallel analysis"


def compute_overall_progress_parallel(
    analysis_status: str,
    analysis_progress: int,
    embeddings_status: str,
    embeddings_progress: int,
    semantic_cache_status: str,
    ai_scan_status: str,
    ai_scan_progress: int,
) -> int:
    """
    Compute overall progress with three parallel tracks.

    Progress breakdown:
    - Static Analysis track: 33% weight
    - Embeddings + Semantic Cache track: 33% weight
    - AI Scan track: 33% weight

    Each track contributes 0-33% based on its progress.
    Progress is capped at 95% until all tracks reach terminal states.
    Returns 100% when all tracks complete.

    Args:
        analysis_status: Current static analysis status
        analysis_progress: Static analysis progress percentage (0-100)
        embeddings_status: Current embeddings status
        embeddings_progress: Embeddings progress percentage (0-100)
        semantic_cache_status: Current semantic cache status
        ai_scan_status: Current AI scan status
        ai_scan_progress: AI scan progress percentage (0-100)

    Returns:
        Overall progress percentage (0-100)

    **Feature: parallel-analysis-pipeline**
    **Property 4: Parallel Progress Calculation**
    **Property 5: Progress Completion Detection**
    **Property 6: Progress Cap at 95%**
    **Validates: Requirements 2.1, 2.2, 2.3, 2.4**
    """
    # Terminal states for each track
    terminal_states = ("completed", "failed", "skipped")

    # Track A: Static Analysis (0-33%)
    static_track = 0
    if analysis_status == "pending":
        static_track = 0
    elif analysis_status == "running":
        # Scale analysis_progress (0-100) to (0-33)
        static_track = int(analysis_progress * 0.33)
    elif analysis_status in terminal_states:
        static_track = 33

    # Track B: Embeddings + Semantic Cache (0-33%)
    # Embeddings is 0-25% of track, Semantic Cache is 25-33%
    embeddings_track = 0
    if embeddings_status == "pending":
        embeddings_track = 0
    elif embeddings_status == "running":
        # Scale embeddings_progress (0-100) to (0-25)
        embeddings_track = int(embeddings_progress * 0.25)
    elif embeddings_status in terminal_states:
        embeddings_track = 25
        # Add semantic cache contribution
        if semantic_cache_status == "computing":
            embeddings_track = 29  # Mid-point of semantic cache portion
        elif semantic_cache_status in terminal_states:
            embeddings_track = 33

    # Track C: AI Scan (0-33%)
    ai_scan_track = 0
    if ai_scan_status == "pending":
        ai_scan_track = 0
    elif ai_scan_status == "running":
        # Scale ai_scan_progress (0-100) to (0-33)
        ai_scan_track = int(ai_scan_progress * 0.33)
    elif ai_scan_status in terminal_states:
        ai_scan_track = 33

    # Combine all tracks
    total = static_track + embeddings_track + ai_scan_track

    # Check if all tracks are in terminal state
    all_terminal = (
        analysis_status in terminal_states and
        embeddings_status in terminal_states and
        semantic_cache_status in terminal_states and
        ai_scan_status in terminal_states
    )

    # Return 100% when all complete, otherwise cap at 95%
    if all_terminal:
        return 100
    else:
        return min(total, 95)
