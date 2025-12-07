"""Property-based tests for IssueMerger.

Uses Hypothesis for property-based testing to verify correctness properties
defined in the design document.
"""

from typing import Any

from hypothesis import assume, given, settings
from hypothesis import strategies as st

from app.services.broad_scan_agent import CandidateIssue
from app.services.issue_merger import (
    DIMENSION_PREFIXES,
    SIMILARITY_THRESHOLD,
    IssueMerger,
    get_issue_merger,
)

# =============================================================================
# Custom Strategies for Test Data Generation
# =============================================================================


@st.composite
def valid_dimension(draw) -> str:
    """Generate valid issue dimensions."""
    return draw(st.sampled_from([
        "security", "db_consistency", "api_correctness", "code_health", "other"
    ]))


@st.composite
def valid_severity(draw) -> str:
    """Generate valid severity levels."""
    return draw(st.sampled_from(["critical", "high", "medium", "low"]))


@st.composite
def valid_confidence(draw) -> str:
    """Generate valid confidence levels."""
    return draw(st.sampled_from(["high", "medium", "low"]))


@st.composite
def file_location(draw) -> dict[str, Any]:
    """Generate a valid file location dict."""
    line_start = draw(st.integers(min_value=1, max_value=1000))
    line_end = draw(st.integers(min_value=line_start, max_value=line_start + 100))
    dirname = draw(st.text(
        alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd"), whitelist_characters="_-"),
        min_size=1,
        max_size=20
    ).filter(lambda s: s.strip()))
    filename = draw(st.text(
        alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd"), whitelist_characters="_-"),
        min_size=1,
        max_size=20
    ).filter(lambda s: s.strip()))
    ext = draw(st.sampled_from([".py", ".js", ".ts", ".go", ".rs", ".java"]))
    return {
        "path": f"{dirname}/{filename}{ext}",
        "line_start": line_start,
        "line_end": line_end,
    }


@st.composite
def model_name(draw) -> str:
    """Generate a valid model name."""
    return draw(st.sampled_from([
        "gemini/gemini-3-pro-preview",
        "bedrock/anthropic.claude-sonnet-4-5-20250929-v1:0",
        "anthropic/claude-sonnet-4-20250514",
        "openai/gpt-4o",
    ]))


@st.composite
def candidate_issue(draw,
                    file_path: str | None = None,
                    summary: str | None = None,
                    source_model: str | None = None) -> CandidateIssue:
    """Generate a valid CandidateIssue.

    Args:
        file_path: Optional fixed file path for the issue
        summary: Optional fixed summary for the issue
        source_model: Optional fixed source model
    """
    # Generate file location
    if file_path:
        files = [{
            "path": file_path,
            "line_start": draw(st.integers(min_value=1, max_value=100)),
            "line_end": draw(st.integers(min_value=100, max_value=200)),
        }]
    else:
        files = draw(st.lists(file_location(), min_size=1, max_size=3))

    # Generate summary
    if summary is None:
        summary = draw(st.text(min_size=10, max_size=100).filter(lambda s: s.strip()))

    # Generate source model
    if source_model is None:
        source_model = draw(model_name())

    return CandidateIssue(
        id_hint=draw(st.text(min_size=1, max_size=20).filter(lambda s: s.strip())),
        dimension=draw(valid_dimension()),
        severity=draw(valid_severity()),
        files=files,
        summary=summary,
        detailed_description=draw(st.text(min_size=10, max_size=500).filter(lambda s: s.strip())),
        evidence_snippets=draw(st.lists(
            st.text(min_size=5, max_size=200).filter(lambda s: s.strip()),
            min_size=1,
            max_size=3
        )),
        potential_impact=draw(st.text(min_size=5, max_size=200).filter(lambda s: s.strip())),
        remediation_idea=draw(st.text(min_size=5, max_size=200).filter(lambda s: s.strip())),
        confidence=draw(valid_confidence()),
        source_model=source_model,
    )


@st.composite
def candidate_issue_list(draw, min_size: int = 1, max_size: int = 10) -> list[CandidateIssue]:
    """Generate a list of candidate issues."""
    return draw(st.lists(candidate_issue(), min_size=min_size, max_size=max_size))


@st.composite
def duplicate_issue_pair(draw) -> tuple[CandidateIssue, CandidateIssue]:
    """Generate a pair of duplicate issues (same file, similar summary).

    Generates two issues that will be detected as duplicates:
    - Same file path
    - Identical summary (>0.8 similarity guaranteed)
    - Different source models
    """
    # Generate a valid file path
    dirname = draw(st.text(
        alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd"), whitelist_characters="_"),
        min_size=3,
        max_size=15
    ).filter(lambda s: s.strip()))
    filename = draw(st.text(
        alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd"), whitelist_characters="_"),
        min_size=3,
        max_size=15
    ).filter(lambda s: s.strip()))
    ext = draw(st.sampled_from([".py", ".js", ".ts"]))
    file_path = f"{dirname}/{filename}{ext}"

    # Base summary - must be non-empty
    base_summary = draw(st.text(min_size=20, max_size=80).filter(lambda s: s.strip()))

    # Common fields
    dimension = draw(valid_dimension())
    severity = draw(valid_severity())

    # Generate distinct evidence for each issue
    evidence1 = draw(st.lists(
        st.text(min_size=5, max_size=100).filter(lambda s: s.strip()),
        min_size=1,
        max_size=2
    ))
    evidence2 = draw(st.lists(
        st.text(min_size=5, max_size=100).filter(lambda s: s.strip()),
        min_size=1,
        max_size=2
    ))

    # Create first issue
    issue1 = CandidateIssue(
        id_hint=draw(st.text(min_size=1, max_size=10).filter(lambda s: s.strip())),
        dimension=dimension,
        severity=severity,
        files=[{"path": file_path, "line_start": 1, "line_end": 10}],
        summary=base_summary,
        detailed_description=draw(st.text(min_size=10, max_size=200).filter(lambda s: s.strip())),
        evidence_snippets=evidence1,
        potential_impact=draw(st.text(min_size=5, max_size=100).filter(lambda s: s.strip())),
        remediation_idea=draw(st.text(min_size=5, max_size=100).filter(lambda s: s.strip())),
        confidence=draw(valid_confidence()),
        source_model="gemini/gemini-3-pro-preview",
    )

    # Create second issue with same file and summary but different model
    issue2 = CandidateIssue(
        id_hint=draw(st.text(min_size=1, max_size=10).filter(lambda s: s.strip())),
        dimension=dimension,
        severity=severity,
        files=[{"path": file_path, "line_start": 5, "line_end": 15}],
        summary=base_summary,  # Same summary = will be detected as duplicate
        detailed_description=draw(st.text(min_size=10, max_size=200).filter(lambda s: s.strip())),
        evidence_snippets=evidence2,
        potential_impact=draw(st.text(min_size=5, max_size=100).filter(lambda s: s.strip())),
        remediation_idea=draw(st.text(min_size=5, max_size=100).filter(lambda s: s.strip())),
        confidence=draw(valid_confidence()),
        source_model="bedrock/anthropic.claude-sonnet-4-5-20250929-v1:0",
    )

    return issue1, issue2


# =============================================================================
# Property Tests for Confidence Boosting
# =============================================================================


class TestConfidenceBoosting:
    """Property tests for confidence boosting.

    **Feature: ai-scan-integration, Property 9: Confidence Boosting**
    **Validates: Requirements 3.3**
    """

    @given(duplicate_issue_pair())
    @settings(max_examples=100)
    def test_multi_model_issues_get_high_confidence(
        self,
        issue_pair: tuple[CandidateIssue, CandidateIssue]
    ):
        """
        **Feature: ai-scan-integration, Property 9: Confidence Boosting**
        **Validates: Requirements 3.3**

        Property: For any issue identified by two or more models, the merged
        issue's confidence SHALL be "high".
        """
        issue1, issue2 = issue_pair

        # duplicate_issue_pair guarantees different models
        assert issue1.source_model != issue2.source_model

        merger = IssueMerger()
        merged = merger.merge([issue1, issue2])

        # Should merge into one issue
        assert len(merged) == 1, (
            f"Expected 1 merged issue, got {len(merged)}"
        )

        # Property: Confidence should be "high" when found by 2+ models
        assert merged[0].confidence == "high", (
            f"Expected confidence 'high', got '{merged[0].confidence}'"
        )

        # Property: Both models should be tracked
        assert len(merged[0].found_by_models) == 2, (
            f"Expected 2 models, got {len(merged[0].found_by_models)}"
        )

    @given(candidate_issue())
    @settings(max_examples=100)
    def test_single_model_keeps_original_confidence(self, issue: CandidateIssue):
        """
        **Feature: ai-scan-integration, Property 9: Confidence Boosting**
        **Validates: Requirements 3.3**

        Property: For any issue found by only one model, the merged issue
        should keep the original confidence level.
        """
        original_confidence = issue.confidence

        merger = IssueMerger()
        merged = merger.merge([issue])

        assert len(merged) == 1

        # Property: Single-model issues keep original confidence
        assert merged[0].confidence == original_confidence, (
            f"Expected confidence '{original_confidence}', got '{merged[0].confidence}'"
        )

    @given(st.integers(min_value=2, max_value=5))
    @settings(max_examples=50)
    def test_confidence_boost_with_n_models(self, num_models: int):
        """
        **Feature: ai-scan-integration, Property 9: Confidence Boosting**
        **Validates: Requirements 3.3**

        Property: Issues found by any number >= 2 models should have "high" confidence.
        """
        models = [
            "gemini/gemini-3-pro-preview",
            "bedrock/anthropic.claude-sonnet-4-5-20250929-v1:0",
            "anthropic/claude-sonnet-4-20250514",
            "openai/gpt-4o",
            "gemini/gemini-2.0-flash-exp",
        ][:num_models]

        # Create duplicate issues from different models
        file_path = "src/main.py"
        summary = "Security vulnerability in authentication"

        issues = []
        for model in models:
            issues.append(CandidateIssue(
                id_hint="sec-001",
                dimension="security",
                severity="high",
                files=[{"path": file_path, "line_start": 10, "line_end": 20}],
                summary=summary,
                detailed_description="Detailed description",
                evidence_snippets=["code snippet"],
                potential_impact="Impact",
                remediation_idea="Fix",
                confidence="low",  # Start with low confidence
                source_model=model,
            ))

        merger = IssueMerger()
        merged = merger.merge(issues)

        assert len(merged) == 1

        # Property: 2+ models = high confidence
        assert merged[0].confidence == "high", (
            f"Expected 'high' confidence with {num_models} models, got '{merged[0].confidence}'"
        )
        assert len(merged[0].found_by_models) == num_models


# =============================================================================
# Property Tests for Issue Deduplication
# =============================================================================


class TestIssueDeduplication:
    """Property tests for issue deduplication.

    **Feature: ai-scan-integration, Property 11: Issue Deduplication**
    **Validates: Requirements 4.1**
    """

    @given(duplicate_issue_pair())
    @settings(max_examples=100)
    def test_duplicates_merged_into_single_issue(
        self,
        issue_pair: tuple[CandidateIssue, CandidateIssue]
    ):
        """
        **Feature: ai-scan-integration, Property 11: Issue Deduplication**
        **Validates: Requirements 4.1**

        Property: For any set of candidate issues with the same file path and
        similar summary (>0.8 similarity), the merger SHALL produce a single
        merged issue.
        """
        issue1, issue2 = issue_pair
        # duplicate_issue_pair guarantees different models
        assert issue1.source_model != issue2.source_model

        merger = IssueMerger()
        merged = merger.merge([issue1, issue2])

        # Property: Duplicates should be merged into one
        assert len(merged) == 1, (
            f"Expected 1 merged issue for duplicates, got {len(merged)}"
        )

    @given(candidate_issue(), candidate_issue())
    @settings(max_examples=100)
    def test_different_files_not_merged(
        self,
        issue1: CandidateIssue,
        issue2: CandidateIssue
    ):
        """
        **Feature: ai-scan-integration, Property 11: Issue Deduplication**
        **Validates: Requirements 4.1**

        Property: Issues with different file paths should NOT be merged,
        even if summaries are similar.
        """
        # Ensure different file paths
        paths1 = {f.get("path") for f in issue1.files if isinstance(f, dict)}
        paths2 = {f.get("path") for f in issue2.files if isinstance(f, dict)}
        assume(not (paths1 & paths2))  # No overlap

        merger = IssueMerger()
        merged = merger.merge([issue1, issue2])

        # Property: Different files = separate issues
        assert len(merged) == 2, (
            f"Expected 2 separate issues for different files, got {len(merged)}"
        )

    @given(st.text(min_size=20, max_size=100).filter(lambda s: s.strip()))
    @settings(max_examples=50)
    def test_similarity_threshold_respected(self, base_summary: str):
        """
        **Feature: ai-scan-integration, Property 11: Issue Deduplication**
        **Validates: Requirements 4.1**

        Property: Issues with similarity <= threshold should NOT be merged.
        """
        file_path = "src/test.py"

        # Create two issues with same file but very different summaries
        issue1 = CandidateIssue(
            id_hint="sec-001",
            dimension="security",
            severity="high",
            files=[{"path": file_path, "line_start": 1, "line_end": 10}],
            summary=base_summary,
            detailed_description="Description 1",
            evidence_snippets=["snippet 1"],
            potential_impact="Impact 1",
            remediation_idea="Fix 1",
            confidence="high",
            source_model="model1",
        )

        # Completely different summary
        different_summary = "ZZZZZ completely unrelated text YYYYY"
        issue2 = CandidateIssue(
            id_hint="sec-002",
            dimension="security",
            severity="high",
            files=[{"path": file_path, "line_start": 50, "line_end": 60}],
            summary=different_summary,
            detailed_description="Description 2",
            evidence_snippets=["snippet 2"],
            potential_impact="Impact 2",
            remediation_idea="Fix 2",
            confidence="high",
            source_model="model2",
        )

        merger = IssueMerger()

        # Check similarity is below threshold
        similarity = merger._calculate_similarity(base_summary, different_summary)
        assume(similarity <= SIMILARITY_THRESHOLD)

        merged = merger.merge([issue1, issue2])

        # Property: Low similarity = separate issues
        assert len(merged) == 2, (
            f"Expected 2 issues for low similarity ({similarity:.2f}), got {len(merged)}"
        )


# =============================================================================
# Property Tests for Merge Attribution and Evidence
# =============================================================================


class TestMergeAttributionAndEvidence:
    """Property tests for merge attribution and evidence.

    **Feature: ai-scan-integration, Property 12: Merge Attribution and Evidence**
    **Validates: Requirements 4.2, 4.3**
    """

    @given(duplicate_issue_pair())
    @settings(max_examples=100)
    def test_all_models_tracked_in_found_by(
        self,
        issue_pair: tuple[CandidateIssue, CandidateIssue]
    ):
        """
        **Feature: ai-scan-integration, Property 12: Merge Attribution and Evidence**
        **Validates: Requirements 4.2, 4.3**

        Property: For any merged issue, the found_by_models field SHALL contain
        all models that found the issue.
        """
        issue1, issue2 = issue_pair
        # duplicate_issue_pair guarantees different models
        assert issue1.source_model != issue2.source_model

        merger = IssueMerger()
        merged = merger.merge([issue1, issue2])

        assert len(merged) == 1

        # Property: Both models should be in found_by_models
        assert issue1.source_model in merged[0].found_by_models, (
            f"Model {issue1.source_model} not in found_by_models"
        )
        assert issue2.source_model in merged[0].found_by_models, (
            f"Model {issue2.source_model} not in found_by_models"
        )

    @given(duplicate_issue_pair())
    @settings(max_examples=100)
    def test_evidence_combined_from_all_sources(
        self,
        issue_pair: tuple[CandidateIssue, CandidateIssue]
    ):
        """
        **Feature: ai-scan-integration, Property 12: Merge Attribution and Evidence**
        **Validates: Requirements 4.2, 4.3**

        Property: For any merged issue, evidence_snippets SHALL contain evidence
        from all sources.
        """
        issue1, issue2 = issue_pair
        # duplicate_issue_pair guarantees different models
        assert issue1.source_model != issue2.source_model

        merger = IssueMerger()
        merged = merger.merge([issue1, issue2])

        assert len(merged) == 1

        # Property: All unique evidence should be included
        merged_evidence = set(merged[0].evidence_snippets)
        for snippet in issue1.evidence_snippets:
            if snippet:  # Non-empty snippets
                assert snippet in merged_evidence, (
                    f"Evidence '{snippet[:30]}...' from issue1 not in merged"
                )
        for snippet in issue2.evidence_snippets:
            if snippet:
                assert snippet in merged_evidence, (
                    f"Evidence '{snippet[:30]}...' from issue2 not in merged"
                )

    @given(candidate_issue_list(min_size=3, max_size=5))
    @settings(max_examples=50)
    def test_no_duplicate_models_in_found_by(self, issues: list[CandidateIssue]):
        """
        **Feature: ai-scan-integration, Property 12: Merge Attribution and Evidence**
        **Validates: Requirements 4.2, 4.3**

        Property: found_by_models should not contain duplicate model names.
        """
        merger = IssueMerger()
        merged = merger.merge(issues)

        for issue in merged:
            # Property: No duplicate models
            assert len(issue.found_by_models) == len(set(issue.found_by_models)), (
                f"Duplicate models in found_by_models: {issue.found_by_models}"
            )


# =============================================================================
# Property Tests for Unique Issue IDs
# =============================================================================


class TestUniqueIssueIDs:
    """Property tests for unique issue IDs.

    **Feature: ai-scan-integration, Property 13: Unique Issue IDs**
    **Validates: Requirements 4.4**
    """

    @given(candidate_issue_list(min_size=1, max_size=20))
    @settings(max_examples=100)
    def test_all_ids_unique(self, issues: list[CandidateIssue]):
        """
        **Feature: ai-scan-integration, Property 13: Unique Issue IDs**
        **Validates: Requirements 4.4**

        Property: For any set of merged issues, all issue IDs SHALL be unique.
        """
        merger = IssueMerger()
        merged = merger.merge(issues)

        ids = [issue.id for issue in merged]

        # Property: All IDs should be unique
        assert len(ids) == len(set(ids)), (
            f"Duplicate IDs found: {ids}"
        )

    @given(candidate_issue_list(min_size=1, max_size=10))
    @settings(max_examples=100)
    def test_id_format_correct(self, issues: list[CandidateIssue]):
        """
        **Feature: ai-scan-integration, Property 13: Unique Issue IDs**
        **Validates: Requirements 4.4**

        Property: Issue IDs should follow the format {prefix}-{sequence}.
        """
        merger = IssueMerger()
        merged = merger.merge(issues)

        valid_prefixes = set(DIMENSION_PREFIXES.values())

        for issue in merged:
            # Property: ID should have correct format
            parts = issue.id.split("-")
            assert len(parts) == 2, (
                f"ID '{issue.id}' should have format 'prefix-sequence'"
            )

            prefix, sequence = parts
            assert prefix in valid_prefixes, (
                f"Invalid prefix '{prefix}' in ID '{issue.id}'"
            )

            # Sequence should be numeric
            assert sequence.isdigit(), (
                f"Sequence '{sequence}' in ID '{issue.id}' should be numeric"
            )

    @given(valid_dimension())
    @settings(max_examples=50)
    def test_dimension_prefix_mapping(self, dimension: str):
        """
        **Feature: ai-scan-integration, Property 13: Unique Issue IDs**
        **Validates: Requirements 4.4**

        Property: Each dimension should map to its correct prefix.
        """
        issue = CandidateIssue(
            id_hint="test",
            dimension=dimension,
            severity="high",
            files=[{"path": "test.py", "line_start": 1, "line_end": 10}],
            summary="Test summary for dimension mapping",
            detailed_description="Description",
            evidence_snippets=["snippet"],
            potential_impact="Impact",
            remediation_idea="Fix",
            confidence="high",
            source_model="test/model",
        )

        merger = IssueMerger()
        merged = merger.merge([issue])

        assert len(merged) == 1

        expected_prefix = DIMENSION_PREFIXES[dimension]
        actual_prefix = merged[0].id.split("-")[0]

        # Property: Dimension should map to correct prefix
        assert actual_prefix == expected_prefix, (
            f"Dimension '{dimension}' should map to prefix '{expected_prefix}', "
            f"got '{actual_prefix}'"
        )


# =============================================================================
# Unit Tests for IssueMerger
# =============================================================================


class TestIssueMergerUnit:
    """Unit tests for IssueMerger."""

    def test_empty_input_returns_empty_list(self):
        """Empty input should return empty list."""
        merger = IssueMerger()
        result = merger.merge([])
        assert result == []

    def test_similarity_calculation(self):
        """Test similarity calculation."""
        merger = IssueMerger()

        # Identical strings
        assert merger._calculate_similarity("hello world", "hello world") == 1.0

        # Empty strings
        assert merger._calculate_similarity("", "") == 0.0
        assert merger._calculate_similarity("hello", "") == 0.0

        # Similar strings
        sim = merger._calculate_similarity("hello world", "hello there")
        assert 0 < sim < 1

    def test_file_path_extraction(self):
        """Test file path extraction from issues."""
        merger = IssueMerger()

        issue = CandidateIssue(
            id_hint="test",
            dimension="security",
            severity="high",
            files=[
                {"path": "src/main.py", "line_start": 1, "line_end": 10},
                {"path": "src/utils.py", "line_start": 20, "line_end": 30},
            ],
            summary="Test",
            detailed_description="Test",
            evidence_snippets=[],
            potential_impact="Test",
            remediation_idea="Test",
            confidence="high",
            source_model="test",
        )

        paths = merger._get_file_paths(issue)
        assert paths == {"src/main.py", "src/utils.py"}

    def test_get_issue_merger_factory(self):
        """Test factory function."""
        merger = get_issue_merger()
        assert isinstance(merger, IssueMerger)
        assert merger.similarity_threshold == SIMILARITY_THRESHOLD

        custom_merger = get_issue_merger(similarity_threshold=0.5)
        assert custom_merger.similarity_threshold == 0.5
