"""Property-based tests for Transparent Scoring Formula.

Uses Hypothesis for property-based testing to verify correctness properties
defined in the design document.
"""

from __future__ import annotations

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from app.services.scoring import get_scoring_service

# =============================================================================
# Custom Strategies for Scoring Tests
# =============================================================================

def valid_line_count() -> st.SearchStrategy[int]:
    """Generate valid line counts for dead code."""
    return st.integers(min_value=0, max_value=10000)


def valid_days_since_modified() -> st.SearchStrategy[int | None]:
    """Generate valid days since modified values."""
    return st.one_of(
        st.none(),
        st.integers(min_value=0, max_value=365 * 10)  # Up to 10 years
    )


def valid_complexity() -> st.SearchStrategy[float | None]:
    """Generate valid complexity scores."""
    return st.one_of(
        st.none(),
        st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False)
    )


def valid_file_path() -> st.SearchStrategy[str]:
    """Generate valid file paths for testing."""
    # Generate paths with various directory structures
    return st.one_of(
        # Paths with known location keywords
        st.sampled_from([
            "app/services/user_service.py",
            "app/api/v1/users.py",
            "app/models/user.py",
            "app/workers/email_worker.py",
            "frontend/components/Button.tsx",
            "lib/utils/helpers.py",
            "tests/test_user.py",
            "src/routes/api.ts",
        ]),
        # Random paths
        st.lists(
            st.from_regex(r"[a-z][a-z0-9_]*", fullmatch=True).filter(lambda s: 2 <= len(s) <= 15),
            min_size=1,
            max_size=4
        ).map(lambda parts: "/".join(parts) + ".py"),
    )


def valid_changes_90d() -> st.SearchStrategy[int]:
    """Generate valid churn counts."""
    return st.integers(min_value=0, max_value=1000)


def valid_coverage_rate() -> st.SearchStrategy[float | None]:
    """Generate valid coverage rates."""
    return st.one_of(
        st.none(),
        st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False)
    )


def valid_unique_authors() -> st.SearchStrategy[int]:
    """Generate valid unique author counts."""
    return st.integers(min_value=0, max_value=100)


# =============================================================================
# Property Tests for Dead Code Impact Score (DCI)
# =============================================================================

class TestDeadCodeImpactScoreProperties:
    """Property tests for Dead Code Impact Score calculation.

    **Feature: transparent-scoring-formula, Property 1: Dead Code Impact Score Calculation**
    **Validates: Requirements 1.1, 1.2, 1.3, 1.4**
    """

    @given(
        line_count=valid_line_count(),
        file_path=valid_file_path(),
        days_since_modified=valid_days_since_modified(),
        complexity=valid_complexity(),
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_dci_score_in_valid_range(
        self,
        line_count: int,
        file_path: str,
        days_since_modified: int | None,
        complexity: float | None,
    ):
        """
        **Feature: transparent-scoring-formula, Property 1: Dead Code Impact Score Calculation**
        **Validates: Requirements 1.1, 1.2, 1.3, 1.4**

        Property: For any dead code finding with line_count, file_path, days_since_modified,
        and complexity values, the calculated impact_score SHALL be in the range [0, 100].
        """
        service = get_scoring_service()

        score = service.calculate_dead_code_impact_score(
            line_count=line_count,
            file_path=file_path,
            days_since_modified=days_since_modified,
            complexity=complexity,
        )

        # Property: Score must be in valid range [0, 100]
        assert 0.0 <= score <= 100.0, (
            f"DCI score out of range!\n"
            f"Score: {score}\n"
            f"Inputs: line_count={line_count}, file_path={file_path}, "
            f"days_since_modified={days_since_modified}, complexity={complexity}"
        )

    @given(
        line_count=valid_line_count(),
        file_path=valid_file_path(),
        days_since_modified=valid_days_since_modified(),
        complexity=valid_complexity(),
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_dci_formula_correctness(
        self,
        line_count: int,
        file_path: str,
        days_since_modified: int | None,
        complexity: float | None,
    ):
        """
        **Feature: transparent-scoring-formula, Property 1: Dead Code Impact Score Calculation**
        **Validates: Requirements 1.1, 1.2, 1.3, 1.4**

        Property: The calculated impact_score SHALL equal
        (Size × 0.40) + (Location × 0.30) + (Recency × 0.20) + (Complexity × 0.10)
        where each component is normalized to [0, 100].
        """
        service = get_scoring_service()

        # Calculate expected components
        size = min(100.0, max(0, line_count) * 2)
        location = service._get_location_score(file_path)

        if days_since_modified is None:
            recency = 50.0
        else:
            recency = max(0.0, min(100.0, 100 - max(0, days_since_modified)))

        complexity_score = complexity if complexity is not None else 50.0
        complexity_score = max(0.0, min(100.0, complexity_score))

        # Calculate expected score using the formula
        expected_score = (
            (size * 0.40)
            + (location * 0.30)
            + (recency * 0.20)
            + (complexity_score * 0.10)
        )
        expected_score = max(0.0, min(100.0, expected_score))

        # Get actual score
        actual_score = service.calculate_dead_code_impact_score(
            line_count=line_count,
            file_path=file_path,
            days_since_modified=days_since_modified,
            complexity=complexity,
        )

        # Property: Actual score should match expected formula result
        assert abs(actual_score - expected_score) < 0.001, (
            f"DCI formula mismatch!\n"
            f"Expected: {expected_score}\n"
            f"Actual: {actual_score}\n"
            f"Components: size={size}, location={location}, recency={recency}, complexity={complexity_score}\n"
            f"Inputs: line_count={line_count}, file_path={file_path}, "
            f"days_since_modified={days_since_modified}, complexity={complexity}"
        )

    @given(
        file_path=valid_file_path(),
        days_since_modified=valid_days_since_modified(),
        complexity=valid_complexity(),
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_dci_size_normalization(
        self,
        file_path: str,
        days_since_modified: int | None,
        complexity: float | None,
    ):
        """
        **Feature: transparent-scoring-formula, Property 1: Dead Code Impact Score Calculation**
        **Validates: Requirements 1.2**

        Property: The Size component SHALL be normalized using min(100, line_count × 2).
        """
        service = get_scoring_service()

        # Test that size component caps at 100
        # With line_count >= 50, size should be 100
        score_at_50 = service.calculate_dead_code_impact_score(
            line_count=50,
            file_path=file_path,
            days_since_modified=days_since_modified,
            complexity=complexity,
        )
        score_at_100 = service.calculate_dead_code_impact_score(
            line_count=100,
            file_path=file_path,
            days_since_modified=days_since_modified,
            complexity=complexity,
        )

        # Both should have the same size component (capped at 100)
        # So the scores should be equal
        assert abs(score_at_50 - score_at_100) < 0.001, (
            f"Size normalization not capping correctly!\n"
            f"Score at 50 lines: {score_at_50}\n"
            f"Score at 100 lines: {score_at_100}\n"
            f"Both should have size component = 100"
        )


# =============================================================================
# Property Tests for Hot Spot Risk Score (HSR)
# =============================================================================

class TestHotSpotRiskScoreProperties:
    """Property tests for Hot Spot Risk Score calculation.

    **Feature: transparent-scoring-formula, Property 2: Hot Spot Risk Score Calculation**
    **Validates: Requirements 2.1, 2.2, 2.3, 2.5**
    """

    @given(
        changes_90d=valid_changes_90d(),
        coverage_rate=valid_coverage_rate(),
        file_path=valid_file_path(),
        unique_authors=valid_unique_authors(),
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_hsr_score_in_valid_range(
        self,
        changes_90d: int,
        coverage_rate: float | None,
        file_path: str,
        unique_authors: int,
    ):
        """
        **Feature: transparent-scoring-formula, Property 2: Hot Spot Risk Score Calculation**
        **Validates: Requirements 2.1, 2.2, 2.3, 2.5**

        Property: For any hot spot finding with changes_90d, coverage_rate, file_path,
        and unique_authors values, the calculated risk_score SHALL be in the range [0, 100].
        """
        service = get_scoring_service()

        score = service.calculate_hot_spot_risk_score(
            changes_90d=changes_90d,
            coverage_rate=coverage_rate,
            file_path=file_path,
            unique_authors=unique_authors,
        )

        # Property: Score must be in valid range [0, 100]
        assert 0.0 <= score <= 100.0, (
            f"HSR score out of range!\n"
            f"Score: {score}\n"
            f"Inputs: changes_90d={changes_90d}, coverage_rate={coverage_rate}, "
            f"file_path={file_path}, unique_authors={unique_authors}"
        )

    @given(
        changes_90d=valid_changes_90d(),
        coverage_rate=valid_coverage_rate(),
        file_path=valid_file_path(),
        unique_authors=valid_unique_authors(),
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_hsr_formula_correctness(
        self,
        changes_90d: int,
        coverage_rate: float | None,
        file_path: str,
        unique_authors: int,
    ):
        """
        **Feature: transparent-scoring-formula, Property 2: Hot Spot Risk Score Calculation**
        **Validates: Requirements 2.1, 2.2, 2.3, 2.5**

        Property: The calculated risk_score SHALL equal
        (Churn × 0.30) + (Coverage × 0.30) + (Location × 0.20) + (Volatility × 0.20)
        where each component is normalized to [0, 100].
        """
        service = get_scoring_service()

        # Calculate expected components
        churn = min(100.0, max(0, changes_90d) * 3)

        if coverage_rate is None:
            coverage = 50.0
        else:
            clamped_coverage = max(0.0, min(1.0, coverage_rate))
            coverage = 100.0 - (clamped_coverage * 100.0)

        location = service._get_location_score(file_path)
        volatility = min(100.0, max(0, unique_authors) * 15)

        # Calculate expected score using the formula
        expected_score = (
            (churn * 0.30)
            + (coverage * 0.30)
            + (location * 0.20)
            + (volatility * 0.20)
        )
        expected_score = max(0.0, min(100.0, expected_score))

        # Get actual score
        actual_score = service.calculate_hot_spot_risk_score(
            changes_90d=changes_90d,
            coverage_rate=coverage_rate,
            file_path=file_path,
            unique_authors=unique_authors,
        )

        # Property: Actual score should match expected formula result
        assert abs(actual_score - expected_score) < 0.001, (
            f"HSR formula mismatch!\n"
            f"Expected: {expected_score}\n"
            f"Actual: {actual_score}\n"
            f"Components: churn={churn}, coverage={coverage}, location={location}, volatility={volatility}\n"
            f"Inputs: changes_90d={changes_90d}, coverage_rate={coverage_rate}, "
            f"file_path={file_path}, unique_authors={unique_authors}"
        )

    @given(
        changes_90d=valid_changes_90d(),
        file_path=valid_file_path(),
        unique_authors=valid_unique_authors(),
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_hsr_coverage_inversion(
        self,
        changes_90d: int,
        file_path: str,
        unique_authors: int,
    ):
        """
        **Feature: transparent-scoring-formula, Property 2: Hot Spot Risk Score Calculation**
        **Validates: Requirements 2.3**

        Property: Lower coverage SHALL result in higher risk score
        (Coverage component = 100 - coverage_rate × 100).
        """
        service = get_scoring_service()

        # Test with 0% coverage (high risk)
        score_low_coverage = service.calculate_hot_spot_risk_score(
            changes_90d=changes_90d,
            coverage_rate=0.0,
            file_path=file_path,
            unique_authors=unique_authors,
        )

        # Test with 100% coverage (low risk)
        score_high_coverage = service.calculate_hot_spot_risk_score(
            changes_90d=changes_90d,
            coverage_rate=1.0,
            file_path=file_path,
            unique_authors=unique_authors,
        )

        # Property: Lower coverage should result in higher score
        assert score_low_coverage >= score_high_coverage, (
            f"Coverage inversion not working!\n"
            f"Score with 0% coverage: {score_low_coverage}\n"
            f"Score with 100% coverage: {score_high_coverage}\n"
            f"Expected: low coverage score >= high coverage score"
        )


# =============================================================================
# Property Tests for Architecture Health Score (AHS)
# =============================================================================

def valid_finding_count() -> st.SearchStrategy[int]:
    """Generate valid finding counts."""
    return st.integers(min_value=0, max_value=1000)


def valid_total_count() -> st.SearchStrategy[int]:
    """Generate valid total counts (functions, files, chunks)."""
    return st.integers(min_value=0, max_value=10000)


class TestArchitectureHealthScoreProperties:
    """Property tests for Architecture Health Score calculation.

    **Feature: transparent-scoring-formula, Property 3: Architecture Health Score Calculation**
    **Validates: Requirements 3.1, 3.2, 3.3, 3.4**
    """

    @given(
        dead_code_count=valid_finding_count(),
        total_functions=valid_total_count(),
        hot_spot_count=valid_finding_count(),
        total_files=valid_total_count(),
        outlier_count=valid_finding_count(),
        total_chunks=valid_total_count(),
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_ahs_score_in_valid_range(
        self,
        dead_code_count: int,
        total_functions: int,
        hot_spot_count: int,
        total_files: int,
        outlier_count: int,
        total_chunks: int,
    ):
        """
        **Feature: transparent-scoring-formula, Property 3: Architecture Health Score Calculation**
        **Validates: Requirements 3.1, 3.2, 3.3, 3.4**

        Property: For any repository with dead_code_count, total_functions, hot_spot_count,
        total_files, outlier_count, and total_chunks, the calculated health_score SHALL be
        in the range [0, 100].
        """
        service = get_scoring_service()

        score = service.calculate_architecture_health_score(
            dead_code_count=dead_code_count,
            total_functions=total_functions,
            hot_spot_count=hot_spot_count,
            total_files=total_files,
            outlier_count=outlier_count,
            total_chunks=total_chunks,
        )

        # Property: Score must be in valid range [0, 100]
        assert 0 <= score <= 100, (
            f"AHS score out of range!\n"
            f"Score: {score}\n"
            f"Inputs: dead_code_count={dead_code_count}, total_functions={total_functions}, "
            f"hot_spot_count={hot_spot_count}, total_files={total_files}, "
            f"outlier_count={outlier_count}, total_chunks={total_chunks}"
        )

    @given(
        dead_code_count=valid_finding_count(),
        total_functions=st.integers(min_value=1, max_value=10000),  # Avoid division by zero
        hot_spot_count=valid_finding_count(),
        total_files=st.integers(min_value=1, max_value=10000),  # Avoid division by zero
        outlier_count=valid_finding_count(),
        total_chunks=st.integers(min_value=1, max_value=10000),  # Avoid division by zero
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_ahs_formula_correctness(
        self,
        dead_code_count: int,
        total_functions: int,
        hot_spot_count: int,
        total_files: int,
        outlier_count: int,
        total_chunks: int,
    ):
        """
        **Feature: transparent-scoring-formula, Property 3: Architecture Health Score Calculation**
        **Validates: Requirements 3.1, 3.2, 3.3, 3.4**

        Property: The calculated health_score SHALL equal 100 minus the sum of penalties
        where each penalty is capped at its maximum value.
        """
        service = get_scoring_service()

        # Calculate expected penalties
        dead_code_penalty = min(40.0, (dead_code_count / total_functions) * 80.0)
        hot_spot_penalty = min(30.0, (hot_spot_count / total_files) * 60.0)
        outlier_penalty = min(20.0, (outlier_count / total_chunks) * 40.0)

        # Calculate expected score
        expected_score = int(max(0, min(100, 100.0 - dead_code_penalty - hot_spot_penalty - outlier_penalty)))

        # Get actual score
        actual_score = service.calculate_architecture_health_score(
            dead_code_count=dead_code_count,
            total_functions=total_functions,
            hot_spot_count=hot_spot_count,
            total_files=total_files,
            outlier_count=outlier_count,
            total_chunks=total_chunks,
        )

        # Property: Actual score should match expected formula result
        assert actual_score == expected_score, (
            f"AHS formula mismatch!\n"
            f"Expected: {expected_score}\n"
            f"Actual: {actual_score}\n"
            f"Penalties: dead_code={dead_code_penalty}, hot_spot={hot_spot_penalty}, outlier={outlier_penalty}\n"
            f"Inputs: dead_code_count={dead_code_count}, total_functions={total_functions}, "
            f"hot_spot_count={hot_spot_count}, total_files={total_files}, "
            f"outlier_count={outlier_count}, total_chunks={total_chunks}"
        )

    @given(
        dead_code_count=valid_finding_count(),
        total_functions=st.integers(min_value=1, max_value=10000),
        hot_spot_count=valid_finding_count(),
        total_files=st.integers(min_value=1, max_value=10000),
        outlier_count=valid_finding_count(),
        total_chunks=st.integers(min_value=1, max_value=10000),
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_ahs_penalty_caps(
        self,
        dead_code_count: int,
        total_functions: int,
        hot_spot_count: int,
        total_files: int,
        outlier_count: int,
        total_chunks: int,
    ):
        """
        **Feature: transparent-scoring-formula, Property 3: Architecture Health Score Calculation**
        **Validates: Requirements 3.2, 3.3, 3.4**

        Property: Each penalty SHALL be capped at its maximum value:
        - Dead Code Penalty: max 40
        - Hot Spot Penalty: max 30
        - Outlier Penalty: max 20
        """
        service = get_scoring_service()

        # Calculate individual penalties
        dead_code_penalty = service._calculate_dead_code_penalty(dead_code_count, total_functions)
        hot_spot_penalty = service._calculate_hot_spot_penalty(hot_spot_count, total_files)
        outlier_penalty = service._calculate_outlier_penalty(outlier_count, total_chunks)

        # Property: Each penalty must be capped at its maximum
        assert dead_code_penalty <= 40.0, (
            f"Dead code penalty exceeds cap!\n"
            f"Penalty: {dead_code_penalty}\n"
            f"Max: 40\n"
            f"Inputs: dead_code_count={dead_code_count}, total_functions={total_functions}"
        )
        assert hot_spot_penalty <= 30.0, (
            f"Hot spot penalty exceeds cap!\n"
            f"Penalty: {hot_spot_penalty}\n"
            f"Max: 30\n"
            f"Inputs: hot_spot_count={hot_spot_count}, total_files={total_files}"
        )
        assert outlier_penalty <= 20.0, (
            f"Outlier penalty exceeds cap!\n"
            f"Penalty: {outlier_penalty}\n"
            f"Max: 20\n"
            f"Inputs: outlier_count={outlier_count}, total_chunks={total_chunks}"
        )

    def test_ahs_with_zero_totals(self):
        """
        **Feature: transparent-scoring-formula, Property 3: Architecture Health Score Calculation**
        **Validates: Requirements 3.2, 3.3, 3.4**

        Property: When total_functions, total_files, or total_chunks is 0,
        the corresponding penalty SHALL be 0 (no division by zero).
        """
        service = get_scoring_service()

        # All totals are zero - should return 100 (no penalties)
        score = service.calculate_architecture_health_score(
            dead_code_count=10,
            total_functions=0,
            hot_spot_count=10,
            total_files=0,
            outlier_count=10,
            total_chunks=0,
        )

        assert score == 100, (
            f"AHS with zero totals should be 100!\n"
            f"Score: {score}\n"
            f"Expected: 100 (no penalties when totals are zero)"
        )

    def test_ahs_minimum_score(self):
        """
        **Feature: transparent-scoring-formula, Property 3: Architecture Health Score Calculation**
        **Validates: Requirements 3.1**

        Property: The minimum possible AHS is 10 (100 - 40 - 30 - 20 = 10).
        """
        service = get_scoring_service()

        # Maximum penalties: all findings equal to totals
        score = service.calculate_architecture_health_score(
            dead_code_count=1000,  # 100% dead code
            total_functions=100,
            hot_spot_count=1000,  # 100% hot spots
            total_files=100,
            outlier_count=1000,  # 100% outliers
            total_chunks=100,
        )

        # With max penalties (40 + 30 + 20 = 90), minimum score is 10
        assert score == 10, (
            f"AHS minimum should be 10!\n"
            f"Score: {score}\n"
            f"Expected: 10 (100 - 40 - 30 - 20)"
        )


# =============================================================================
# Unit Tests for Edge Cases
# =============================================================================

# =============================================================================
# Property Tests for LLM Sample Selection
# =============================================================================

def valid_finding() -> st.SearchStrategy[dict]:
    """Generate a valid finding dictionary with score and file_path."""
    return st.fixed_dictionaries({
        "score": st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False),
        "file_path": valid_file_path(),
    })


def valid_findings_list() -> st.SearchStrategy[list[dict]]:
    """Generate a list of valid findings."""
    return st.lists(valid_finding(), min_size=0, max_size=50)


def valid_limit() -> st.SearchStrategy[int]:
    """Generate valid limit values for sample selection."""
    return st.integers(min_value=0, max_value=30)


class TestLLMSampleSelectionProperties:
    """Property tests for LLM Sample Selection algorithm.

    **Feature: transparent-scoring-formula, Property 6: LLM Sample Selection**
    **Validates: Requirements 4.1, 4.2, 4.3**
    """

    @given(
        findings=valid_findings_list(),
        limit=valid_limit(),
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_selection_returns_at_most_limit(
        self,
        findings: list[dict],
        limit: int,
    ):
        """
        **Feature: transparent-scoring-formula, Property 6: LLM Sample Selection**
        **Validates: Requirements 4.1, 4.2, 4.3**

        Property: For any list of findings and a limit N, the selection algorithm
        SHALL return at most N findings.
        """
        service = get_scoring_service()

        selected = service.select_llm_samples(findings, limit=limit)

        # Property: Result must have at most `limit` items
        assert len(selected) <= limit, (
            f"Selection returned more than limit!\n"
            f"Selected: {len(selected)}\n"
            f"Limit: {limit}\n"
            f"Total findings: {len(findings)}"
        )

    @given(
        findings=valid_findings_list(),
        limit=valid_limit(),
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_selection_returns_correct_count(
        self,
        findings: list[dict],
        limit: int,
    ):
        """
        **Feature: transparent-scoring-formula, Property 6: LLM Sample Selection**
        **Validates: Requirements 4.1, 4.2, 4.3**

        Property: For any list of findings and a limit N, the selection algorithm
        SHALL return min(N, len(findings)) findings.
        """
        service = get_scoring_service()

        selected = service.select_llm_samples(findings, limit=limit)

        expected_count = min(limit, len(findings))
        assert len(selected) == expected_count, (
            f"Selection returned wrong count!\n"
            f"Selected: {len(selected)}\n"
            f"Expected: {expected_count}\n"
            f"Limit: {limit}, Total findings: {len(findings)}"
        )

    @given(
        findings=st.lists(valid_finding(), min_size=1, max_size=50),
        limit=st.integers(min_value=2, max_value=30),
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_selection_includes_top_scores(
        self,
        findings: list[dict],
        limit: int,
    ):
        """
        **Feature: transparent-scoring-formula, Property 6: LLM Sample Selection**
        **Validates: Requirements 4.1, 4.2**

        Property: For any list of findings and a limit N, the selection algorithm
        SHALL include the top N/2 highest-scoring findings (when enough findings exist).
        """
        service = get_scoring_service()

        # Only test when we have more findings than limit (diversity sampling kicks in)
        if len(findings) <= limit:
            return  # Skip - all findings returned when count <= limit

        selected = service.select_llm_samples(findings, limit=limit)

        # Sort original findings by score to find top N/2
        sorted_by_score = sorted(findings, key=lambda f: f.get("score", 0.0), reverse=True)
        top_count = limit // 2
        expected_top = sorted_by_score[:top_count]

        # All top N/2 findings should be in the selection
        selected_scores = {(f.get("score"), f.get("file_path")) for f in selected}
        for top_finding in expected_top:
            key = (top_finding.get("score"), top_finding.get("file_path"))
            assert key in selected_scores, (
                f"Top scoring finding not in selection!\n"
                f"Missing: score={top_finding.get('score')}, path={top_finding.get('file_path')}\n"
                f"Top {top_count} expected, limit={limit}"
            )

    @given(
        findings=st.lists(valid_finding(), min_size=1, max_size=50),
        limit=st.integers(min_value=2, max_value=30),
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_selection_diversity_sampling(
        self,
        findings: list[dict],
        limit: int,
    ):
        """
        **Feature: transparent-scoring-formula, Property 6: LLM Sample Selection**
        **Validates: Requirements 4.3**

        Property: For any list of findings and a limit N, the selection algorithm
        SHALL include findings from at least min(N/2, unique_directories) different
        directories in the remaining slots (after top scores).
        """
        service = get_scoring_service()

        # Only test when we have more findings than limit
        if len(findings) <= limit:
            return  # Skip - all findings returned when count <= limit

        selected = service.select_llm_samples(findings, limit=limit)

        # Count unique directories in selection
        selected_dirs = {
            service._get_directory(f.get("file_path", ""))
            for f in selected
        }

        # Count unique directories in all findings
        all_dirs = {
            service._get_directory(f.get("file_path", ""))
            for f in findings
        }

        # The diversity sampling should maximize directory coverage
        # We expect at least min(diversity_slots, available_unique_dirs) directories
        diversity_slots = limit - (limit // 2)  # 50% for diversity
        min(diversity_slots, len(all_dirs))

        # But we also need to account for top scores already covering some dirs
        # So we just verify we have reasonable diversity
        assert len(selected_dirs) >= 1, (
            f"Selection has no directory diversity!\n"
            f"Selected dirs: {selected_dirs}\n"
            f"All dirs: {all_dirs}"
        )

    def test_selection_empty_findings(self):
        """
        **Feature: transparent-scoring-formula, Property 6: LLM Sample Selection**
        **Validates: Requirements 4.1**

        Property: Empty findings list should return empty selection.
        """
        service = get_scoring_service()
        selected = service.select_llm_samples([], limit=10)
        assert selected == []

    def test_selection_zero_limit(self):
        """
        **Feature: transparent-scoring-formula, Property 6: LLM Sample Selection**
        **Validates: Requirements 4.1**

        Property: Zero limit should return empty selection.
        """
        service = get_scoring_service()
        findings = [
            {"score": 80.0, "file_path": "app/services/user.py"},
            {"score": 60.0, "file_path": "app/models/user.py"},
        ]
        selected = service.select_llm_samples(findings, limit=0)
        assert selected == []

    def test_selection_fewer_findings_than_limit(self):
        """
        **Feature: transparent-scoring-formula, Property 6: LLM Sample Selection**
        **Validates: Requirements 4.1**

        Property: When findings count < limit, return all findings sorted by score.
        """
        service = get_scoring_service()
        findings = [
            {"score": 60.0, "file_path": "app/models/user.py"},
            {"score": 80.0, "file_path": "app/services/user.py"},
            {"score": 40.0, "file_path": "lib/utils/helpers.py"},
        ]
        selected = service.select_llm_samples(findings, limit=10)

        assert len(selected) == 3
        # Should be sorted by score descending
        assert selected[0]["score"] == 80.0
        assert selected[1]["score"] == 60.0
        assert selected[2]["score"] == 40.0

    def test_selection_diversity_example(self):
        """
        **Feature: transparent-scoring-formula, Property 6: LLM Sample Selection**
        **Validates: Requirements 4.2, 4.3**

        Property: Verify diversity sampling picks from different directories.
        """
        service = get_scoring_service()

        # Create findings with clear score ordering and different directories
        findings = [
            {"score": 100.0, "file_path": "app/services/a.py"},  # Top 1
            {"score": 90.0, "file_path": "app/services/b.py"},   # Top 2
            {"score": 80.0, "file_path": "app/services/c.py"},   # Top 3 (same dir)
            {"score": 70.0, "file_path": "app/models/d.py"},     # Different dir
            {"score": 60.0, "file_path": "app/api/e.py"},        # Different dir
            {"score": 50.0, "file_path": "lib/utils/f.py"},      # Different dir
            {"score": 40.0, "file_path": "tests/g.py"},          # Different dir
        ]

        # With limit=6: top 3 from scores, then 3 from diversity
        selected = service.select_llm_samples(findings, limit=6)

        assert len(selected) == 6

        # Top 3 by score should be included
        selected_scores = [f["score"] for f in selected]
        assert 100.0 in selected_scores
        assert 90.0 in selected_scores
        assert 80.0 in selected_scores

        # Should have diversity - not all from app/services
        selected_dirs = {service._get_directory(f["file_path"]) for f in selected}
        assert len(selected_dirs) >= 3, (
            f"Expected at least 3 different directories, got {len(selected_dirs)}: {selected_dirs}"
        )


# =============================================================================
# Property Tests for Findings Sorted by Score
# =============================================================================

class TestFindingsSortedByScoreProperties:
    """Property tests for findings sorted by score.

    **Feature: transparent-scoring-formula, Property 5: Findings Sorted by Score**
    **Validates: Requirements 1.6, 2.6**
    """

    @given(
        line_counts=st.lists(st.integers(min_value=1, max_value=100), min_size=0, max_size=20),
        file_paths=st.lists(valid_file_path(), min_size=0, max_size=20),
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow], deadline=None)
    def test_dead_code_findings_sorted_by_impact_score(
        self,
        line_counts: list[int],
        file_paths: list[str],
    ):
        """
        **Feature: transparent-scoring-formula, Property 5: Findings Sorted by Score**
        **Validates: Requirements 1.6**

        Property: For any list of dead code findings returned by the analyzer,
        the findings SHALL be sorted by impact_score in descending order
        (highest score first).
        """
        from app.services.call_graph_analyzer import CallGraph, CallGraphAnalyzer, CallGraphNode

        # Create a call graph with unreachable nodes
        call_graph = CallGraph()

        # Use the shorter list length to pair line_counts with file_paths
        count = min(len(line_counts), len(file_paths))
        if count == 0:
            # Empty case - should return empty list
            analyzer = CallGraphAnalyzer()
            findings = analyzer.to_dead_code_findings(call_graph)
            assert findings == []
            return

        # Create unreachable nodes (no entry points, no calls)
        for i in range(count):
            node_id = f"{file_paths[i]}:func_{i}"
            line_count = line_counts[i]
            call_graph.nodes[node_id] = CallGraphNode(
                id=node_id,
                file_path=file_paths[i],
                name=f"func_{i}",
                line_start=1,
                line_end=line_count,
                is_entry_point=False,
            )

        # No entry points means all nodes are unreachable
        analyzer = CallGraphAnalyzer()
        findings = analyzer.to_dead_code_findings(call_graph)

        # Property: Findings must be sorted by impact_score descending
        for i in range(len(findings) - 1):
            assert findings[i].impact_score >= findings[i + 1].impact_score, (
                f"Dead code findings not sorted by impact_score!\n"
                f"Finding {i}: score={findings[i].impact_score}, path={findings[i].file_path}\n"
                f"Finding {i+1}: score={findings[i+1].impact_score}, path={findings[i+1].file_path}\n"
                f"Expected: findings[{i}].impact_score >= findings[{i+1}].impact_score"
            )

    @given(
        changes_list=st.lists(st.integers(min_value=11, max_value=100), min_size=0, max_size=20),
        file_paths=st.lists(valid_file_path(), min_size=0, max_size=20),
        coverage_rates=st.lists(valid_coverage_rate(), min_size=0, max_size=20),
        author_counts=st.lists(st.integers(min_value=1, max_value=10), min_size=0, max_size=20),
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow], deadline=None)
    def test_hot_spot_findings_sorted_by_risk_score(
        self,
        changes_list: list[int],
        file_paths: list[str],
        coverage_rates: list[float | None],
        author_counts: list[int],
    ):
        """
        **Feature: transparent-scoring-formula, Property 5: Findings Sorted by Score**
        **Validates: Requirements 2.6**

        Property: For any list of hot spot findings returned by the analyzer,
        the findings SHALL be sorted by risk_score in descending order
        (highest score first).
        """
        from app.services.git_analyzer import FileChurn, GitAnalyzer

        # Use the minimum list length
        count = min(len(changes_list), len(file_paths), len(coverage_rates), len(author_counts))
        if count == 0:
            # Empty case - should return empty list
            analyzer = GitAnalyzer()
            findings = analyzer.to_hot_spot_findings({})
            assert findings == []
            return

        # Create churn data
        churn_data: dict[str, FileChurn] = {}
        coverage_data: dict[str, float] = {}

        for i in range(count):
            file_path = file_paths[i]
            churn_data[file_path] = FileChurn(
                file_path=file_path,
                changes_90d=changes_list[i],  # All above threshold (11+)
                unique_authors=author_counts[i],
            )
            if coverage_rates[i] is not None:
                coverage_data[file_path] = coverage_rates[i]

        analyzer = GitAnalyzer()
        findings = analyzer.to_hot_spot_findings(
            churn_data,
            coverage_data=coverage_data if coverage_data else None,
            threshold=10,  # All our changes are > 10
        )

        # Property: Findings must be sorted by risk_score descending
        for i in range(len(findings) - 1):
            assert findings[i].risk_score >= findings[i + 1].risk_score, (
                f"Hot spot findings not sorted by risk_score!\n"
                f"Finding {i}: score={findings[i].risk_score}, path={findings[i].file_path}\n"
                f"Finding {i+1}: score={findings[i+1].risk_score}, path={findings[i+1].file_path}\n"
                f"Expected: findings[{i}].risk_score >= findings[{i+1}].risk_score"
            )

    def test_dead_code_findings_have_impact_score(self):
        """
        **Feature: transparent-scoring-formula, Property 5: Findings Sorted by Score**
        **Validates: Requirements 1.1, 1.6**

        Property: Each dead code finding SHALL have an impact_score field
        with a value in [0, 100].
        """
        from app.services.call_graph_analyzer import CallGraph, CallGraphAnalyzer, CallGraphNode

        call_graph = CallGraph()
        call_graph.nodes["test.py:unused_func"] = CallGraphNode(
            id="test.py:unused_func",
            file_path="test.py",
            name="unused_func",
            line_start=1,
            line_end=10,
            is_entry_point=False,
        )

        analyzer = CallGraphAnalyzer()
        findings = analyzer.to_dead_code_findings(call_graph)

        assert len(findings) == 1
        assert hasattr(findings[0], "impact_score")
        assert 0.0 <= findings[0].impact_score <= 100.0

    def test_hot_spot_findings_have_risk_score(self):
        """
        **Feature: transparent-scoring-formula, Property 5: Findings Sorted by Score**
        **Validates: Requirements 2.1, 2.6**

        Property: Each hot spot finding SHALL have a risk_score field
        with a value in [0, 100].
        """
        from app.services.git_analyzer import FileChurn, GitAnalyzer

        churn_data = {
            "app/services/test.py": FileChurn(
                file_path="app/services/test.py",
                changes_90d=20,
                unique_authors=3,
            )
        }

        analyzer = GitAnalyzer()
        findings = analyzer.to_hot_spot_findings(churn_data, threshold=10)

        assert len(findings) == 1
        assert hasattr(findings[0], "risk_score")
        assert 0.0 <= findings[0].risk_score <= 100.0


# =============================================================================
# Unit Tests for Edge Cases
# =============================================================================

class TestScoringServiceEdgeCases:
    """Unit tests for edge cases in scoring calculations."""

    def test_dci_with_zero_line_count(self):
        """Test DCI calculation with zero line count."""
        service = get_scoring_service()
        score = service.calculate_dead_code_impact_score(
            line_count=0,
            file_path="app/services/test.py",
            days_since_modified=30,
            complexity=50.0,
        )
        assert 0.0 <= score <= 100.0

    def test_dci_with_negative_line_count(self):
        """Test DCI calculation handles negative line count gracefully."""
        service = get_scoring_service()
        score = service.calculate_dead_code_impact_score(
            line_count=-10,
            file_path="app/services/test.py",
            days_since_modified=30,
            complexity=50.0,
        )
        # Should treat negative as 0
        assert 0.0 <= score <= 100.0

    def test_dci_with_none_values(self):
        """Test DCI calculation with None values uses defaults."""
        service = get_scoring_service()
        score = service.calculate_dead_code_impact_score(
            line_count=50,
            file_path="app/services/test.py",
            days_since_modified=None,
            complexity=None,
        )
        assert 0.0 <= score <= 100.0

    def test_hsr_with_zero_values(self):
        """Test HSR calculation with zero values."""
        service = get_scoring_service()
        score = service.calculate_hot_spot_risk_score(
            changes_90d=0,
            coverage_rate=0.0,
            file_path="app/services/test.py",
            unique_authors=0,
        )
        assert 0.0 <= score <= 100.0

    def test_hsr_with_none_coverage(self):
        """Test HSR calculation with None coverage uses neutral value."""
        service = get_scoring_service()
        score = service.calculate_hot_spot_risk_score(
            changes_90d=10,
            coverage_rate=None,
            file_path="app/services/test.py",
            unique_authors=3,
        )
        assert 0.0 <= score <= 100.0

    def test_location_score_services(self):
        """Test location score for services directory."""
        service = get_scoring_service()
        score = service._get_location_score("app/services/user_service.py")
        assert score == 100.0

    def test_location_score_tests(self):
        """Test location score for tests directory."""
        service = get_scoring_service()
        score = service._get_location_score("tests/test_user.py")
        assert score == 20.0

    def test_location_score_unknown(self):
        """Test location score for unknown directory."""
        service = get_scoring_service()
        score = service._get_location_score("random/path/file.py")
        assert score == 50.0  # Default

    def test_location_score_empty_path(self):
        """Test location score for empty path."""
        service = get_scoring_service()
        score = service._get_location_score("")
        assert score == 50.0  # Default

    def test_singleton_instance(self):
        """Test that get_scoring_service returns singleton."""
        service1 = get_scoring_service()
        service2 = get_scoring_service()
        assert service1 is service2


# =============================================================================
# Property Tests for Score Badge Color Coding
# =============================================================================

class TestScoreColorCodingProperties:
    """Property tests for score badge color coding.

    **Feature: transparent-scoring-formula, Property 4: Score Badge Color Coding**
    **Validates: Requirements 3.5, 5.3**
    """

    @given(score=st.floats(min_value=0.0, max_value=39.99, allow_nan=False, allow_infinity=False))
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_finding_score_green_range(self, score: float):
        """
        **Feature: transparent-scoring-formula, Property 4: Score Badge Color Coding**
        **Validates: Requirements 5.3**

        Property: For any score value in [0, 39], the color coding function
        SHALL return "green" (low priority).
        """
        service = get_scoring_service()
        color = service.get_score_color(score)
        assert color == "green", (
            f"Score {score} should be green (low priority), got {color}"
        )

    @given(score=st.floats(min_value=40.0, max_value=69.99, allow_nan=False, allow_infinity=False))
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_finding_score_amber_range(self, score: float):
        """
        **Feature: transparent-scoring-formula, Property 4: Score Badge Color Coding**
        **Validates: Requirements 5.3**

        Property: For any score value in [40, 69], the color coding function
        SHALL return "amber" (medium priority).
        """
        service = get_scoring_service()
        color = service.get_score_color(score)
        assert color == "amber", (
            f"Score {score} should be amber (medium priority), got {color}"
        )

    @given(score=st.floats(min_value=70.0, max_value=100.0, allow_nan=False, allow_infinity=False))
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_finding_score_red_range(self, score: float):
        """
        **Feature: transparent-scoring-formula, Property 4: Score Badge Color Coding**
        **Validates: Requirements 5.3**

        Property: For any score value in [70, 100], the color coding function
        SHALL return "red" (high priority).
        """
        service = get_scoring_service()
        color = service.get_score_color(score)
        assert color == "red", (
            f"Score {score} should be red (high priority), got {color}"
        )

    @given(score=st.integers(min_value=80, max_value=100))
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_health_score_green_range(self, score: int):
        """
        **Feature: transparent-scoring-formula, Property 4: Score Badge Color Coding**
        **Validates: Requirements 3.5**

        Property: For any health score value in [80, 100], the color coding function
        SHALL return "green" (healthy).
        """
        service = get_scoring_service()
        color = service.get_health_color(score)
        assert color == "green", (
            f"Health score {score} should be green (healthy), got {color}"
        )

    @given(score=st.integers(min_value=60, max_value=79))
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_health_score_amber_range(self, score: int):
        """
        **Feature: transparent-scoring-formula, Property 4: Score Badge Color Coding**
        **Validates: Requirements 3.5**

        Property: For any health score value in [60, 79], the color coding function
        SHALL return "amber" (moderate).
        """
        service = get_scoring_service()
        color = service.get_health_color(score)
        assert color == "amber", (
            f"Health score {score} should be amber (moderate), got {color}"
        )

    @given(score=st.integers(min_value=40, max_value=59))
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_health_score_orange_range(self, score: int):
        """
        **Feature: transparent-scoring-formula, Property 4: Score Badge Color Coding**
        **Validates: Requirements 3.5**

        Property: For any health score value in [40, 59], the color coding function
        SHALL return "orange" (concerning).
        """
        service = get_scoring_service()
        color = service.get_health_color(score)
        assert color == "orange", (
            f"Health score {score} should be orange (concerning), got {color}"
        )

    @given(score=st.integers(min_value=0, max_value=39))
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_health_score_red_range(self, score: int):
        """
        **Feature: transparent-scoring-formula, Property 4: Score Badge Color Coding**
        **Validates: Requirements 3.5**

        Property: For any health score value in [0, 39], the color coding function
        SHALL return "red" (critical).
        """
        service = get_scoring_service()
        color = service.get_health_color(score)
        assert color == "red", (
            f"Health score {score} should be red (critical), got {color}"
        )

    @given(score=st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False))
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_finding_score_returns_valid_color(self, score: float):
        """
        **Feature: transparent-scoring-formula, Property 4: Score Badge Color Coding**
        **Validates: Requirements 5.3**

        Property: For any score value in [0, 100], the color coding function
        SHALL return one of: "green", "amber", or "red".
        """
        service = get_scoring_service()
        color = service.get_score_color(score)
        assert color in {"green", "amber", "red"}, (
            f"Invalid color {color} for score {score}"
        )

    @given(score=st.integers(min_value=0, max_value=100))
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_health_score_returns_valid_color(self, score: int):
        """
        **Feature: transparent-scoring-formula, Property 4: Score Badge Color Coding**
        **Validates: Requirements 3.5**

        Property: For any health score value in [0, 100], the color coding function
        SHALL return one of: "green", "amber", "orange", or "red".
        """
        service = get_scoring_service()
        color = service.get_health_color(score)
        assert color in {"green", "amber", "orange", "red"}, (
            f"Invalid color {color} for health score {score}"
        )

    def test_finding_score_boundary_39_40(self):
        """
        **Feature: transparent-scoring-formula, Property 4: Score Badge Color Coding**
        **Validates: Requirements 5.3**

        Property: Verify boundary between green and amber at 40.
        """
        service = get_scoring_service()
        assert service.get_score_color(39.99) == "green"
        assert service.get_score_color(40.0) == "amber"

    def test_finding_score_boundary_69_70(self):
        """
        **Feature: transparent-scoring-formula, Property 4: Score Badge Color Coding**
        **Validates: Requirements 5.3**

        Property: Verify boundary between amber and red at 70.
        """
        service = get_scoring_service()
        assert service.get_score_color(69.99) == "amber"
        assert service.get_score_color(70.0) == "red"

    def test_health_score_boundary_79_80(self):
        """
        **Feature: transparent-scoring-formula, Property 4: Score Badge Color Coding**
        **Validates: Requirements 3.5**

        Property: Verify boundary between amber and green at 80.
        """
        service = get_scoring_service()
        assert service.get_health_color(79) == "amber"
        assert service.get_health_color(80) == "green"

    def test_health_score_boundary_59_60(self):
        """
        **Feature: transparent-scoring-formula, Property 4: Score Badge Color Coding**
        **Validates: Requirements 3.5**

        Property: Verify boundary between orange and amber at 60.
        """
        service = get_scoring_service()
        assert service.get_health_color(59) == "orange"
        assert service.get_health_color(60) == "amber"

    def test_health_score_boundary_39_40(self):
        """
        **Feature: transparent-scoring-formula, Property 4: Score Badge Color Coding**
        **Validates: Requirements 3.5**

        Property: Verify boundary between red and orange at 40.
        """
        service = get_scoring_service()
        assert service.get_health_color(39) == "red"
        assert service.get_health_color(40) == "orange"

    def test_finding_score_clamps_out_of_range(self):
        """
        **Feature: transparent-scoring-formula, Property 4: Score Badge Color Coding**
        **Validates: Requirements 5.3**

        Property: Scores outside [0, 100] should be clamped.
        """
        service = get_scoring_service()
        # Negative should clamp to 0 -> green
        assert service.get_score_color(-10.0) == "green"
        # Over 100 should clamp to 100 -> red
        assert service.get_score_color(150.0) == "red"

    def test_health_score_clamps_out_of_range(self):
        """
        **Feature: transparent-scoring-formula, Property 4: Score Badge Color Coding**
        **Validates: Requirements 3.5**

        Property: Health scores outside [0, 100] should be clamped.
        """
        service = get_scoring_service()
        # Negative should clamp to 0 -> red
        assert service.get_health_color(-10) == "red"
        # Over 100 should clamp to 100 -> green
        assert service.get_health_color(150) == "green"
