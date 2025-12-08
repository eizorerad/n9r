"""Property-based tests for ClusterAnalyzer LLM-Ready Output.

Uses Hypothesis for property-based testing to verify correctness properties
defined in the design document for the cluster-map-refactoring feature.

Requirements: 4.1, 4.5
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from app.schemas.architecture_llm import (
    DeadCodeFinding,
    HotSpotFinding,
)
from app.services.cluster_analyzer import ClusterAnalyzer

# =============================================================================
# Custom Strategies for Architecture Data Generation
# =============================================================================


@st.composite
def dead_code_finding(draw) -> DeadCodeFinding:
    """Generate a valid DeadCodeFinding."""
    file_path = draw(st.from_regex(r"[a-zA-Z_][a-zA-Z0-9_/]*\.py", fullmatch=True).filter(
        lambda s: 4 <= len(s) <= 100
    ))
    function_name = draw(st.from_regex(r"[a-zA-Z_][a-zA-Z0-9_]*", fullmatch=True).filter(
        lambda s: 1 <= len(s) <= 50 and s not in {"def", "class", "return", "if", "else"}
    ))
    line_start = draw(st.integers(min_value=1, max_value=1000))
    line_count = draw(st.integers(min_value=1, max_value=100))
    line_end = line_start + line_count - 1

    return DeadCodeFinding(
        file_path=file_path,
        function_name=function_name,
        line_start=line_start,
        line_end=line_end,
        line_count=line_count,
        confidence=1.0,
        evidence=f"Function '{function_name}' is never called from any entry point",
        suggested_action=f"Safe to remove - no callers found. This will reduce codebase by {line_count} lines.",
        last_modified=None,
    )


@st.composite
def hot_spot_finding(draw) -> HotSpotFinding:
    """Generate a valid HotSpotFinding."""
    file_path = draw(st.from_regex(r"[a-zA-Z_][a-zA-Z0-9_/]*\.py", fullmatch=True).filter(
        lambda s: 4 <= len(s) <= 100
    ))
    churn_count = draw(st.integers(min_value=11, max_value=100))  # Above threshold
    coverage_rate = draw(st.one_of(
        st.none(),
        st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False)
    ))
    unique_authors = draw(st.integers(min_value=1, max_value=20))

    risk_factors = [f"High churn: {churn_count} changes in 90 days"]
    if coverage_rate is not None and coverage_rate < 0.5:
        risk_factors.append(f"Low test coverage: {coverage_rate * 100:.0f}%")

    return HotSpotFinding(
        file_path=file_path,
        churn_count=churn_count,
        coverage_rate=coverage_rate,
        unique_authors=unique_authors,
        risk_factors=risk_factors,
        suggested_action="Add tests before next modification.",
    )


@st.composite
def architecture_findings(draw) -> tuple[list[DeadCodeFinding], list[HotSpotFinding], int, int]:
    """Generate architecture findings with counts.

    Returns:
        Tuple of (dead_code_list, hot_spots_list, total_files, total_functions)
    """
    num_dead_code = draw(st.integers(min_value=0, max_value=10))
    num_hot_spots = draw(st.integers(min_value=0, max_value=10))

    dead_code = [draw(dead_code_finding()) for _ in range(num_dead_code)]
    hot_spots = [draw(hot_spot_finding()) for _ in range(num_hot_spots)]

    # Total files and functions should be >= findings
    total_files = draw(st.integers(min_value=max(1, num_hot_spots), max_value=100))
    total_functions = draw(st.integers(min_value=max(1, num_dead_code), max_value=500))

    return dead_code, hot_spots, total_files, total_functions


# =============================================================================
# Property Tests for Architecture Summary Format
# =============================================================================


class TestArchitectureSummaryFormatProperties:
    """Property tests for architecture summary format.

    **Feature: cluster-map-refactoring, Property 10: Architecture Summary Format**
    **Validates: Requirements 4.1**
    """

    @given(architecture_findings())
    @settings(max_examples=100)
    def test_architecture_summary_format(
        self,
        findings: tuple[list[DeadCodeFinding], list[HotSpotFinding], int, int]
    ):
        """
        **Feature: cluster-map-refactoring, Property 10: Architecture Summary Format**
        **Validates: Requirements 4.1**

        Property: For any LLMReadyArchitectureData, the summary SHALL have:
        health_score in [0, 100], main_concerns as non-empty list when issues exist,
        and accurate counts for dead_code_count and hot_spot_count.
        """
        dead_code, hot_spots, total_files, total_functions = findings

        # Create analyzer and generate summary
        analyzer = ClusterAnalyzer()
        summary = analyzer._generate_architecture_summary(
            dead_code=dead_code,
            hot_spots=hot_spots,
            total_files=total_files,
            total_functions=total_functions,
        )

        # Property 1: health_score is in valid range [0, 100]
        assert 0 <= summary.health_score <= 100, (
            f"health_score must be in [0, 100], got {summary.health_score}"
        )

        # Property 2: main_concerns is a list
        assert isinstance(summary.main_concerns, list), (
            f"main_concerns must be a list, got {type(summary.main_concerns)}"
        )

        # Property 3: main_concerns is non-empty when issues exist
        has_issues = len(dead_code) > 0 or len(hot_spots) > 0
        if has_issues:
            assert len(summary.main_concerns) > 0, (
                "main_concerns should be non-empty when issues exist.\n"
                f"dead_code count: {len(dead_code)}, hot_spots count: {len(hot_spots)}"
            )

        # Property 4: dead_code_count matches actual count
        assert summary.dead_code_count == len(dead_code), (
            f"dead_code_count mismatch: expected {len(dead_code)}, got {summary.dead_code_count}"
        )

        # Property 5: hot_spot_count matches actual count
        assert summary.hot_spot_count == len(hot_spots), (
            f"hot_spot_count mismatch: expected {len(hot_spots)}, got {summary.hot_spot_count}"
        )

        # Property 6: total_files is preserved
        assert summary.total_files == total_files, (
            f"total_files mismatch: expected {total_files}, got {summary.total_files}"
        )

        # Property 7: total_functions is preserved
        assert summary.total_functions == total_functions, (
            f"total_functions mismatch: expected {total_functions}, got {summary.total_functions}"
        )

        # Property 8: health_score is an integer
        assert isinstance(summary.health_score, int), (
            f"health_score must be an integer, got {type(summary.health_score)}"
        )

    @given(architecture_findings())
    @settings(max_examples=100)
    def test_health_score_decreases_with_more_issues(
        self,
        findings: tuple[list[DeadCodeFinding], list[HotSpotFinding], int, int]
    ):
        """
        **Feature: cluster-map-refactoring, Property 10: Architecture Summary Format**
        **Validates: Requirements 4.1**

        Property: Health score should decrease as the ratio of issues increases.
        """
        dead_code, hot_spots, total_files, total_functions = findings

        analyzer = ClusterAnalyzer()

        # Calculate score with current findings
        score_with_issues = analyzer._calculate_llm_health_score(
            dead_code_count=len(dead_code),
            hot_spot_count=len(hot_spots),
            total_files=total_files,
            total_functions=total_functions,
        )

        # Calculate score with no issues
        score_no_issues = analyzer._calculate_llm_health_score(
            dead_code_count=0,
            hot_spot_count=0,
            total_files=total_files,
            total_functions=total_functions,
        )

        # Property: Score with issues should be <= score without issues
        assert score_with_issues <= score_no_issues, (
            f"Score with issues ({score_with_issues}) should be <= "
            f"score without issues ({score_no_issues})"
        )


# =============================================================================
# Property Tests for LLM-Ready Natural Language
# =============================================================================


class TestLLMReadyNaturalLanguageProperties:
    """Property tests for LLM-ready natural language.

    **Feature: cluster-map-refactoring, Property 11: LLM-Ready Natural Language**
    **Validates: Requirements 4.5**
    """

    @given(dead_code_finding())
    @settings(max_examples=100)
    def test_dead_code_evidence_is_human_readable(self, finding: DeadCodeFinding):
        """
        **Feature: cluster-map-refactoring, Property 11: LLM-Ready Natural Language**
        **Validates: Requirements 4.5**

        Property: For any DeadCodeFinding, the evidence and suggested_action fields
        SHALL be human-readable sentences (not code or IDs).
        """
        # Property 1: Evidence is non-empty
        assert finding.evidence, "evidence should not be empty"

        # Property 2: Evidence is a sentence (contains spaces)
        assert " " in finding.evidence, (
            f"evidence should be a sentence with spaces, got: '{finding.evidence}'"
        )

        # Property 3: Evidence mentions the function name
        assert finding.function_name in finding.evidence, (
            f"evidence should mention function name '{finding.function_name}', "
            f"got: '{finding.evidence}'"
        )

        # Property 4: Suggested action is non-empty
        assert finding.suggested_action, "suggested_action should not be empty"

        # Property 5: Suggested action is a sentence (contains spaces)
        assert " " in finding.suggested_action, (
            f"suggested_action should be a sentence with spaces, got: '{finding.suggested_action}'"
        )

        # Property 6: Suggested action is meaningful (more than 10 chars)
        assert len(finding.suggested_action) > 10, (
            f"suggested_action should be meaningful, got: '{finding.suggested_action}'"
        )

    @given(hot_spot_finding())
    @settings(max_examples=100)
    def test_hot_spot_risk_factors_are_human_readable(self, finding: HotSpotFinding):
        """
        **Feature: cluster-map-refactoring, Property 11: LLM-Ready Natural Language**
        **Validates: Requirements 4.5**

        Property: For any HotSpotFinding, the risk_factors and suggested_action fields
        SHALL be human-readable sentences (not code or IDs).
        """
        # Property 1: Risk factors is non-empty
        assert finding.risk_factors, "risk_factors should not be empty"

        # Property 2: Each risk factor is a sentence (contains spaces)
        for factor in finding.risk_factors:
            assert " " in factor, (
                f"risk factor should be a sentence with spaces, got: '{factor}'"
            )

        # Property 3: Suggested action is non-empty
        assert finding.suggested_action, "suggested_action should not be empty"

        # Property 4: Suggested action is a sentence (contains spaces)
        assert " " in finding.suggested_action, (
            f"suggested_action should be a sentence with spaces, got: '{finding.suggested_action}'"
        )

    @given(architecture_findings())
    @settings(max_examples=100)
    def test_main_concerns_are_human_readable(
        self,
        findings: tuple[list[DeadCodeFinding], list[HotSpotFinding], int, int]
    ):
        """
        **Feature: cluster-map-refactoring, Property 11: LLM-Ready Natural Language**
        **Validates: Requirements 4.5**

        Property: For any architecture summary, the main_concerns list SHALL contain
        human-readable sentences that can be directly shown to users.
        """
        dead_code, hot_spots, total_files, total_functions = findings

        analyzer = ClusterAnalyzer()
        concerns = analyzer._generate_main_concerns(dead_code, hot_spots)

        # Property 1: Concerns is a list
        assert isinstance(concerns, list), f"concerns must be a list, got {type(concerns)}"

        # Property 2: Each concern is a string
        for concern in concerns:
            assert isinstance(concern, str), f"each concern must be a string, got {type(concern)}"

        # Property 3: Each concern is a sentence (contains spaces)
        for concern in concerns:
            assert " " in concern, (
                f"concern should be a sentence with spaces, got: '{concern}'"
            )

        # Property 4: Each concern is meaningful (more than 10 chars)
        for concern in concerns:
            assert len(concern) > 10, (
                f"concern should be meaningful, got: '{concern}'"
            )

        # Property 5: Concerns mention specific numbers when issues exist
        if dead_code:
            # At least one concern should mention the dead code count
            dead_code_mentioned = any(
                str(len(dead_code)) in concern or "unreachable" in concern.lower()
                for concern in concerns
            )
            assert dead_code_mentioned, (
                f"Concerns should mention dead code when present.\n"
                f"Dead code count: {len(dead_code)}\n"
                f"Concerns: {concerns}"
            )
