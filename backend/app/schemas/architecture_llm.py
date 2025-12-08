"""LLM-ready architecture data schemas.

Defines dataclasses for architecture analysis data optimized for LLM consumption.
These schemas are used internally by the ClusterAnalyzer and SemanticAIInsightsService.

Requirements: 4.1, 4.2, 4.3, 4.4
"""

from dataclasses import dataclass, field


@dataclass
class ArchitectureSummary:
    """High-level summary for LLM context.

    Provides an overview of the repository's architecture health,
    including key metrics and main concerns.

    Requirements: 4.1
    """

    health_score: int  # 0-100
    main_concerns: list[str]  # Natural language concerns
    total_files: int
    total_functions: int
    dead_code_count: int
    hot_spot_count: int


@dataclass
class DeadCodeFinding:
    """Dead code finding with evidence for LLM.

    Represents a function that is unreachable from any entry point,
    with natural language evidence and suggested action.

    Requirements: 4.2
    """

    file_path: str
    function_name: str
    line_start: int
    line_end: int
    line_count: int
    confidence: float  # 1.0 = call-graph proven
    evidence: str  # "Never called from any entry point"
    suggested_action: str  # "Safe to remove - no callers found"
    last_modified: str | None = None  # "January 2024" or None
    impact_score: float = 0.0  # Dead Code Impact Score (0-100)


@dataclass
class HotSpotFinding:
    """High-risk file finding with risk factors.

    Represents a file with high code churn and/or low test coverage,
    with natural language risk factors and suggested action.

    Requirements: 4.4
    """

    file_path: str
    churn_count: int  # Changes in 90 days
    coverage_rate: float | None  # 0.0-1.0 or None if unavailable
    unique_authors: int
    risk_factors: list[str]  # ["47 changes in 90 days", "0% test coverage"]
    suggested_action: str  # "Add tests before next modification"
    risk_score: float = 0.0  # Hot Spot Risk Score (0-100)


@dataclass
class ArchitectureIssue:
    """General architecture issue.

    Represents a detected architecture problem with impact assessment
    and suggested fix.

    Requirements: 4.3
    """

    issue_type: str  # "coupling", "complexity", "duplication"
    description: str  # Natural language description
    affected_files: list[str]
    impact: str  # "High - affects 12 modules"
    suggested_fix: str  # "Extract shared logic to utils module"


@dataclass
class LLMReadyArchitectureData:
    """Complete architecture data optimized for LLM consumption.

    Container class that holds all architecture analysis findings
    in a format suitable for AI/LLM processing.

    Requirements: 4.1, 4.2, 4.3, 4.4
    """

    summary: ArchitectureSummary
    dead_code: list[DeadCodeFinding] = field(default_factory=list)
    hot_spots: list[HotSpotFinding] = field(default_factory=list)
    issues: list[ArchitectureIssue] = field(default_factory=list)
