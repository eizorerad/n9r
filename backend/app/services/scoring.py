"""Scoring Service for Transparent Architecture Finding Prioritization.

Provides transparent, explainable scoring formulas for:
- Dead Code Impact Score (DCI): Prioritizes dead code removal
- Hot Spot Risk Score (HSR): Prioritizes high-risk files
- Architecture Health Score (AHS): Overall repository health

All formulas are documented and exposed to users via the UI.
"""

import logging

logger = logging.getLogger(__name__)


class ScoringService:
    """Transparent scoring formulas for architecture findings.

    All scores are in the range [0, 100].
    """

    # Location score lookup table - higher scores for more critical code
    LOCATION_SCORES: dict[str, int] = {
        "services": 100,
        "service": 100,
        "api": 90,
        "routes": 90,
        "endpoints": 90,
        "models": 80,
        "model": 80,
        "workers": 70,
        "worker": 70,
        "tasks": 70,
        "components": 60,
        "component": 60,
        "lib": 40,
        "utils": 40,
        "util": 40,
        "helpers": 40,
        "helper": 40,
        "common": 40,
        "tests": 20,
        "test": 20,
        "__tests__": 20,
    }
    DEFAULT_LOCATION_SCORE = 50

    # DCI formula weights
    DCI_SIZE_WEIGHT = 0.40
    DCI_LOCATION_WEIGHT = 0.30
    DCI_RECENCY_WEIGHT = 0.20
    DCI_COMPLEXITY_WEIGHT = 0.10

    # HSR formula weights
    HSR_CHURN_WEIGHT = 0.30
    HSR_COVERAGE_WEIGHT = 0.30
    HSR_LOCATION_WEIGHT = 0.20
    HSR_VOLATILITY_WEIGHT = 0.20

    # AHS penalty caps
    AHS_DEAD_CODE_PENALTY_CAP = 40
    AHS_HOT_SPOT_PENALTY_CAP = 30
    AHS_OUTLIER_PENALTY_CAP = 20

    def _normalize_size(self, line_count: int) -> float:
        """Normalize line count to 0-100.

        Formula: min(100, line_count × 2)

        Args:
            line_count: Number of lines in the dead code

        Returns:
            Normalized size score 0-100
        """
        if line_count < 0:
            line_count = 0
        return min(100.0, line_count * 2)

    def _normalize_recency(self, days_since_modified: int | None) -> float:
        """Normalize recency to 0-100.

        Formula: max(0, 100 - days_since_modified) capped at 100
        More recent = higher score (more impactful to remove)

        Args:
            days_since_modified: Days since the file was last modified, or None

        Returns:
            Normalized recency score 0-100
        """
        if days_since_modified is None:
            return 50.0  # Neutral value when unknown
        if days_since_modified < 0:
            days_since_modified = 0
        return max(0.0, min(100.0, 100 - days_since_modified))

    def _normalize_churn(self, changes_90d: int) -> float:
        """Normalize churn count to 0-100.

        Formula: min(100, changes_90d × 3)

        Args:
            changes_90d: Number of changes in the last 90 days

        Returns:
            Normalized churn score 0-100
        """
        if changes_90d < 0:
            changes_90d = 0
        return min(100.0, changes_90d * 3)

    def _normalize_coverage(self, coverage_rate: float | None) -> float:
        """Normalize coverage to 0-100 (inverted - lower coverage = higher risk).

        Formula: 100 - (coverage_rate × 100)

        Args:
            coverage_rate: Coverage rate as decimal (0.0-1.0), or None

        Returns:
            Normalized coverage score 0-100 (higher = more risk)
        """
        if coverage_rate is None:
            return 50.0  # Neutral value when unknown
        # Clamp coverage_rate to valid range
        coverage_rate = max(0.0, min(1.0, coverage_rate))
        return 100.0 - (coverage_rate * 100.0)

    def _normalize_volatility(self, unique_authors: int) -> float:
        """Normalize author volatility to 0-100.

        Formula: min(100, unique_authors × 15)
        More authors = higher volatility = higher risk

        Args:
            unique_authors: Number of unique authors who modified the file

        Returns:
            Normalized volatility score 0-100
        """
        if unique_authors < 0:
            unique_authors = 0
        return min(100.0, unique_authors * 15)

    def _get_location_score(self, file_path: str) -> float:
        """Get location score based on file path patterns.

        Uses a lookup table where:
        - services = 100 (core business logic)
        - api/routes = 90
        - models = 80
        - workers/tasks = 70
        - components = 60
        - lib/utils/helpers = 40
        - tests = 20
        - other = 50 (default)

        Args:
            file_path: Path to the file

        Returns:
            Location score 0-100
        """
        if not file_path:
            return float(self.DEFAULT_LOCATION_SCORE)

        # Normalize path separators
        normalized_path = file_path.replace("\\", "/").lower()
        path_parts = normalized_path.split("/")

        # Check each path part for location keywords
        for part in path_parts:
            if part in self.LOCATION_SCORES:
                return float(self.LOCATION_SCORES[part])

        return float(self.DEFAULT_LOCATION_SCORE)

    def calculate_dead_code_impact_score(
        self,
        line_count: int,
        file_path: str,
        days_since_modified: int | None = None,
        complexity: float | None = None,
    ) -> float:
        """Calculate Dead Code Impact Score (DCI).

        Formula: (Size × 0.40) + (Location × 0.30) + (Recency × 0.20) + (Complexity × 0.10)

        All components are normalized to 0-100, resulting in a final score of 0-100.

        Args:
            line_count: Number of lines in the dead code
            file_path: Path to the file containing dead code
            days_since_modified: Days since the file was last modified, or None
            complexity: Complexity score 0-100, or None (defaults to 50)

        Returns:
            Dead Code Impact Score 0-100
        """
        size = self._normalize_size(line_count)
        location = self._get_location_score(file_path)
        recency = self._normalize_recency(days_since_modified)
        complexity_score = complexity if complexity is not None else 50.0
        # Clamp complexity to valid range
        complexity_score = max(0.0, min(100.0, complexity_score))

        score = (
            (size * self.DCI_SIZE_WEIGHT)
            + (location * self.DCI_LOCATION_WEIGHT)
            + (recency * self.DCI_RECENCY_WEIGHT)
            + (complexity_score * self.DCI_COMPLEXITY_WEIGHT)
        )

        # Clamp to valid range (should already be 0-100 but ensure)
        return max(0.0, min(100.0, score))

    def calculate_hot_spot_risk_score(
        self,
        changes_90d: int,
        coverage_rate: float | None,
        file_path: str,
        unique_authors: int,
    ) -> float:
        """Calculate Hot Spot Risk Score (HSR).

        Formula: (Churn × 0.30) + (Coverage × 0.30) + (Location × 0.20) + (Volatility × 0.20)

        All components are normalized to 0-100, resulting in a final score of 0-100.

        Args:
            changes_90d: Number of changes in the last 90 days
            coverage_rate: Coverage rate as decimal (0.0-1.0), or None
            file_path: Path to the file
            unique_authors: Number of unique authors who modified the file

        Returns:
            Hot Spot Risk Score 0-100
        """
        churn = self._normalize_churn(changes_90d)
        coverage = self._normalize_coverage(coverage_rate)
        location = self._get_location_score(file_path)
        volatility = self._normalize_volatility(unique_authors)

        score = (
            (churn * self.HSR_CHURN_WEIGHT)
            + (coverage * self.HSR_COVERAGE_WEIGHT)
            + (location * self.HSR_LOCATION_WEIGHT)
            + (volatility * self.HSR_VOLATILITY_WEIGHT)
        )

        # Clamp to valid range (should already be 0-100 but ensure)
        return max(0.0, min(100.0, score))

    def _calculate_dead_code_penalty(
        self,
        dead_code_count: int,
        total_functions: int,
    ) -> float:
        """Calculate dead code penalty for Architecture Health Score.

        Formula: min(40, (dead_code_count / total_functions) × 80)

        Args:
            dead_code_count: Number of dead code findings
            total_functions: Total number of functions in the repository

        Returns:
            Dead code penalty 0-40
        """
        if total_functions <= 0:
            return 0.0
        if dead_code_count < 0:
            dead_code_count = 0

        ratio = dead_code_count / total_functions
        penalty = ratio * 80.0
        return min(self.AHS_DEAD_CODE_PENALTY_CAP, penalty)

    def _calculate_hot_spot_penalty(
        self,
        hot_spot_count: int,
        total_files: int,
    ) -> float:
        """Calculate hot spot penalty for Architecture Health Score.

        Formula: min(30, (hot_spot_count / total_files) × 60)

        Args:
            hot_spot_count: Number of hot spot findings
            total_files: Total number of files in the repository

        Returns:
            Hot spot penalty 0-30
        """
        if total_files <= 0:
            return 0.0
        if hot_spot_count < 0:
            hot_spot_count = 0

        ratio = hot_spot_count / total_files
        penalty = ratio * 60.0
        return min(self.AHS_HOT_SPOT_PENALTY_CAP, penalty)

    def _calculate_outlier_penalty(
        self,
        outlier_count: int,
        total_chunks: int,
    ) -> float:
        """Calculate outlier penalty for Architecture Health Score.

        Formula: min(20, (outlier_count / total_chunks) × 40)

        Args:
            outlier_count: Number of outlier findings
            total_chunks: Total number of code chunks in the repository

        Returns:
            Outlier penalty 0-20
        """
        if total_chunks <= 0:
            return 0.0
        if outlier_count < 0:
            outlier_count = 0

        ratio = outlier_count / total_chunks
        penalty = ratio * 40.0
        return min(self.AHS_OUTLIER_PENALTY_CAP, penalty)

    def calculate_architecture_health_score(
        self,
        dead_code_count: int,
        total_functions: int,
        hot_spot_count: int,
        total_files: int,
        outlier_count: int,
        total_chunks: int,
    ) -> int:
        """Calculate Architecture Health Score (AHS).

        Formula: 100 - (Dead Code Penalty + Hot Spot Penalty + Outlier Penalty)

        The score is clamped to [0, 100] range.

        Args:
            dead_code_count: Number of dead code findings
            total_functions: Total number of functions in the repository
            hot_spot_count: Number of hot spot findings
            total_files: Total number of files in the repository
            outlier_count: Number of outlier findings
            total_chunks: Total number of code chunks in the repository

        Returns:
            Architecture Health Score 0-100 (integer)
        """
        dead_code_penalty = self._calculate_dead_code_penalty(dead_code_count, total_functions)
        hot_spot_penalty = self._calculate_hot_spot_penalty(hot_spot_count, total_files)
        outlier_penalty = self._calculate_outlier_penalty(outlier_count, total_chunks)

        total_penalty = dead_code_penalty + hot_spot_penalty + outlier_penalty
        score = 100.0 - total_penalty

        # Clamp to valid range and return as integer
        return max(0, min(100, int(score)))

    def _get_directory(self, file_path: str) -> str:
        """Extract directory from file path for diversity sampling.

        Args:
            file_path: Path to the file

        Returns:
            Directory portion of the path, or empty string if no directory
        """
        if not file_path:
            return ""
        # Normalize path separators
        normalized = file_path.replace("\\", "/")
        parts = normalized.rsplit("/", 1)
        return parts[0] if len(parts) > 1 else ""

    def select_llm_samples(
        self,
        findings: list[dict],
        limit: int = 15,
        score_key: str = "score",
        file_path_key: str = "file_path",
    ) -> list[dict]:
        """Select most impactful findings for LLM analysis.

        Strategy:
        1. Sort all findings by score descending
        2. Take top 50% of the limit from highest-scoring findings
        3. Fill remaining 50% with diversity sampling from different directories
        4. Fall back to next highest scores if diversity exhausted

        This ensures the LLM sees both the most critical findings AND a diverse
        sample across the codebase.

        Args:
            findings: List of finding dictionaries with score and file_path
            limit: Maximum number of findings to return (default 15)
            score_key: Key name for the score field in findings (default "score")
            file_path_key: Key name for the file path field (default "file_path")

        Returns:
            Selected findings list, at most `limit` items
        """
        if not findings:
            return []

        if limit <= 0:
            return []

        # If we have fewer findings than limit, return all sorted by score
        if len(findings) <= limit:
            sorted_findings = sorted(
                findings,
                key=lambda f: f.get(score_key, 0.0),
                reverse=True
            )
            logger.info(
                f"LLM sample selection: returning all {len(sorted_findings)} findings "
                f"(limit={limit})"
            )
            return sorted_findings

        # Sort all findings by score descending
        sorted_findings = sorted(
            findings,
            key=lambda f: f.get(score_key, 0.0),
            reverse=True
        )

        # Calculate how many to take from top scores vs diversity
        top_count = limit // 2  # 50% from top scores
        diversity_count = limit - top_count  # Remaining 50% for diversity

        # Take top 50% from highest scores
        selected: list[dict] = sorted_findings[:top_count]
        selected_set: set[int] = {id(f) for f in selected}

        # Track directories already represented in selected findings
        represented_dirs: set[str] = {
            self._get_directory(f.get(file_path_key, ""))
            for f in selected
        }

        # Remaining findings not yet selected
        remaining = [f for f in sorted_findings[top_count:] if id(f) not in selected_set]

        # Diversity sampling: pick from different directories
        diversity_selected: list[dict] = []
        for finding in remaining:
            if len(diversity_selected) >= diversity_count:
                break

            directory = self._get_directory(finding.get(file_path_key, ""))
            if directory not in represented_dirs:
                diversity_selected.append(finding)
                represented_dirs.add(directory)

        # If diversity sampling didn't fill all slots, fall back to next highest scores
        if len(diversity_selected) < diversity_count:
            # Get remaining findings not yet selected
            diversity_set = {id(f) for f in diversity_selected}
            fallback_candidates = [
                f for f in remaining
                if id(f) not in diversity_set
            ]

            # Take as many as needed to fill the limit
            slots_to_fill = diversity_count - len(diversity_selected)
            diversity_selected.extend(fallback_candidates[:slots_to_fill])

        # Combine top scores and diversity selections
        result = selected + diversity_selected

        # Log selection details
        logger.info(
            f"LLM sample selection: {len(result)} findings selected "
            f"(top_scores={len(selected)}, diversity={len(diversity_selected)}, "
            f"unique_dirs={len(represented_dirs)}, total_available={len(findings)})"
        )

        return result


    def get_score_color(self, score: float) -> str:
        """Get color coding for finding scores (DCI, HSR).

        Color coding for finding priority:
        - green: 0-39 (low priority)
        - amber: 40-69 (medium priority)
        - red: 70-100 (high priority)

        Args:
            score: Score value 0-100

        Returns:
            Color string: "green", "amber", or "red"
        """
        # Clamp score to valid range
        score = max(0.0, min(100.0, score))

        if score < 40:
            return "green"
        elif score < 70:
            return "amber"
        else:
            return "red"

    def get_health_color(self, score: int) -> str:
        """Get color coding for Architecture Health Score.

        Color coding for health status (inverse of finding scores):
        - green: 80-100 (healthy)
        - amber: 60-79 (moderate)
        - orange: 40-59 (concerning)
        - red: 0-39 (critical)

        Args:
            score: Health score value 0-100

        Returns:
            Color string: "green", "amber", "orange", or "red"
        """
        # Clamp score to valid range
        score = max(0, min(100, score))

        if score >= 80:
            return "green"
        elif score >= 60:
            return "amber"
        elif score >= 40:
            return "orange"
        else:
            return "red"


# Singleton instance for easy import
_scoring_service: ScoringService | None = None


def get_scoring_service() -> ScoringService:
    """Get the singleton ScoringService instance."""
    global _scoring_service
    if _scoring_service is None:
        _scoring_service = ScoringService()
    return _scoring_service
