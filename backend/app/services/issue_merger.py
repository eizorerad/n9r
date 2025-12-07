"""Issue Merger for AI Scan.

Deduplicates and consolidates issues found by multiple LLM models.
Implements similarity-based deduplication and confidence boosting.
"""

import logging
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any

from app.services.broad_scan_agent import CandidateIssue

logger = logging.getLogger(__name__)


# =============================================================================
# Constants
# =============================================================================

# Similarity threshold for considering two issues as duplicates
SIMILARITY_THRESHOLD = 0.8

# Dimension prefixes for unique ID generation
DIMENSION_PREFIXES = {
    "security": "sec",
    "db_consistency": "db",
    "api_correctness": "api",
    "code_health": "health",
    "other": "other",
}


# =============================================================================
# Data Classes
# =============================================================================


@dataclass
class MergedIssue:
    """Consolidated issue from multiple models.

    Represents a deduplicated issue that may have been found by multiple
    LLM models during broad scan.

    Attributes:
        id: Unique issue ID (e.g., "sec-001")
        dimension: Category of issue (security, db_consistency, api_correctness, code_health, other)
        severity: Issue severity (critical, high, medium, low)
        title: Brief title for the issue
        summary: Detailed summary of the issue
        files: List of affected files with line ranges
        evidence_snippets: Combined code snippets from all sources
        confidence: Confidence level (boosted if found by multiple models)
        found_by_models: List of models that identified this issue
        investigation_status: Status from investigation agent (if investigated)
        suggested_fix: Suggested fix from investigation (if investigated)
    """
    id: str
    dimension: str
    severity: str
    title: str
    summary: str
    files: list[dict[str, Any]]
    evidence_snippets: list[str]
    confidence: str
    found_by_models: list[str]
    investigation_status: str | None = None
    suggested_fix: str | None = None


# =============================================================================
# IssueMerger Class
# =============================================================================


class IssueMerger:
    """Merges and deduplicates issues from multiple models.

    Uses similarity-based deduplication to consolidate issues found by
    different LLM models. Boosts confidence for issues found by multiple models.
    """

    def __init__(self, similarity_threshold: float = SIMILARITY_THRESHOLD):
        """Initialize the IssueMerger.

        Args:
            similarity_threshold: Threshold for considering issues as duplicates (0.0-1.0)
        """
        self.similarity_threshold = similarity_threshold
        self._id_counters: dict[str, int] = {}

    def _calculate_similarity(self, text1: str, text2: str) -> float:
        """Calculate similarity between two text strings.

        Uses SequenceMatcher for similarity calculation.

        Args:
            text1: First text string
            text2: Second text string

        Returns:
            Similarity ratio between 0.0 and 1.0
        """
        if not text1 or not text2:
            return 0.0
        return SequenceMatcher(None, text1.lower(), text2.lower()).ratio()

    def _get_file_paths(self, issue: CandidateIssue) -> set[str]:
        """Extract file paths from an issue.

        Args:
            issue: CandidateIssue to extract paths from

        Returns:
            Set of file paths
        """
        paths = set()
        for file_info in issue.files:
            if isinstance(file_info, dict) and "path" in file_info:
                paths.add(file_info["path"])
        return paths

    def _has_file_overlap(self, issue_a: CandidateIssue, issue_b: CandidateIssue) -> bool:
        """Check if two issues have overlapping file paths.

        Args:
            issue_a: First issue
            issue_b: Second issue

        Returns:
            True if there's at least one common file path
        """
        paths_a = self._get_file_paths(issue_a)
        paths_b = self._get_file_paths(issue_b)
        return bool(paths_a & paths_b)

    def _are_duplicates(self, issue_a: CandidateIssue, issue_b: CandidateIssue) -> bool:
        """Check if two issues are duplicates.

        Deduplication criteria:
        - Same file path AND
        - Similar summary (>threshold similarity)

        Args:
            issue_a: First issue
            issue_b: Second issue

        Returns:
            True if issues are considered duplicates
        """
        # Must have file path overlap
        if not self._has_file_overlap(issue_a, issue_b):
            return False

        # Check summary similarity
        similarity = self._calculate_similarity(issue_a.summary, issue_b.summary)
        return similarity > self.similarity_threshold

    def _boost_confidence(self, found_by_count: int, original_confidence: str) -> str:
        """Determine confidence level based on model consensus.

        Confidence boosting rules:
        - Found by 2+ models: confidence = "high"
        - Found by 1 model: keep original confidence

        Args:
            found_by_count: Number of models that found the issue
            original_confidence: Original confidence from the first model

        Returns:
            Boosted confidence level
        """
        if found_by_count >= 2:
            return "high"
        return original_confidence

    def _generate_id(self, dimension: str) -> str:
        """Generate unique ID for an issue.

        Format: {dimension_prefix}-{sequence} (e.g., "sec-001")

        Args:
            dimension: Issue dimension

        Returns:
            Unique issue ID
        """
        prefix = DIMENSION_PREFIXES.get(dimension, "other")

        # Increment counter for this prefix
        if prefix not in self._id_counters:
            self._id_counters[prefix] = 0
        self._id_counters[prefix] += 1

        return f"{prefix}-{self._id_counters[prefix]:03d}"

    def _merge_group(self, issues: list[CandidateIssue]) -> MergedIssue:
        """Merge a group of duplicate issues into one.

        Combines evidence from all sources and tracks which models found the issue.

        Args:
            issues: List of duplicate CandidateIssue instances

        Returns:
            Single MergedIssue combining all information
        """
        if not issues:
            raise ValueError("Cannot merge empty issue list")

        # Use first issue as base
        base = issues[0]

        # Collect all unique models
        found_by_models: list[str] = []
        seen_models: set[str] = set()
        for issue in issues:
            if issue.source_model not in seen_models:
                found_by_models.append(issue.source_model)
                seen_models.add(issue.source_model)

        # Combine all evidence snippets (deduplicated)
        all_evidence: list[str] = []
        seen_evidence: set[str] = set()
        for issue in issues:
            for snippet in issue.evidence_snippets:
                if snippet and snippet not in seen_evidence:
                    all_evidence.append(snippet)
                    seen_evidence.add(snippet)

        # Combine all files (deduplicated by path)
        all_files: list[dict[str, Any]] = []
        seen_paths: set[str] = set()
        for issue in issues:
            for file_info in issue.files:
                if isinstance(file_info, dict):
                    path = file_info.get("path", "")
                    if path and path not in seen_paths:
                        all_files.append(file_info)
                        seen_paths.add(path)

        # Boost confidence based on model count
        confidence = self._boost_confidence(len(found_by_models), base.confidence)

        # Generate unique ID
        issue_id = self._generate_id(base.dimension)

        # Use summary as title (truncated if needed)
        title = base.summary[:200] if len(base.summary) > 200 else base.summary

        return MergedIssue(
            id=issue_id,
            dimension=base.dimension,
            severity=base.severity,
            title=title,
            summary=base.detailed_description or base.summary,
            files=all_files,
            evidence_snippets=all_evidence,
            confidence=confidence,
            found_by_models=found_by_models,
            investigation_status=None,
            suggested_fix=None,
        )

    def merge(self, candidates: list[CandidateIssue]) -> list[MergedIssue]:
        """Merge candidate issues into deduplicated list.

        Groups duplicate issues together and merges each group into a single
        MergedIssue. Issues found by multiple models get boosted confidence.

        Args:
            candidates: List of CandidateIssue from all models

        Returns:
            List of deduplicated MergedIssue instances
        """
        if not candidates:
            return []

        # Reset ID counters for each merge operation
        self._id_counters = {}

        # Track which candidates have been assigned to groups
        assigned: set[int] = set()
        groups: list[list[CandidateIssue]] = []

        # Group duplicates together
        for i, candidate_a in enumerate(candidates):
            if i in assigned:
                continue

            # Start a new group with this candidate
            group = [candidate_a]
            assigned.add(i)

            # Find all duplicates
            for j, candidate_b in enumerate(candidates):
                if j in assigned:
                    continue

                if self._are_duplicates(candidate_a, candidate_b):
                    group.append(candidate_b)
                    assigned.add(j)

            groups.append(group)

        # Merge each group
        merged_issues: list[MergedIssue] = []
        for group in groups:
            merged = self._merge_group(group)
            merged_issues.append(merged)

        logger.info(
            f"Merged {len(candidates)} candidates into {len(merged_issues)} issues "
            f"({len(candidates) - len(merged_issues)} duplicates removed)"
        )

        return merged_issues


# =============================================================================
# Convenience Functions
# =============================================================================


def get_issue_merger(similarity_threshold: float = SIMILARITY_THRESHOLD) -> IssueMerger:
    """Create an IssueMerger instance.

    Args:
        similarity_threshold: Threshold for duplicate detection (0.0-1.0)

    Returns:
        Configured IssueMerger instance
    """
    return IssueMerger(similarity_threshold)
