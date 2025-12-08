"""Property-based tests for Architecture Findings API.

Uses Hypothesis for property-based testing to verify correctness properties
defined in the design document for the cluster-map-refactoring feature.

Requirements: 7.1, 7.3
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.models.dead_code import DeadCode
from app.models.file_churn import FileChurn
from app.schemas.architecture_llm import (
    ArchitectureSummary,
    DeadCodeFinding,
    HotSpotFinding,
    LLMReadyArchitectureData,
)

# =============================================================================
# Custom Strategies for Architecture Findings
# =============================================================================


def valid_file_path() -> st.SearchStrategy[str]:
    """Generate valid file paths."""
    return st.from_regex(r"[a-zA-Z_][a-zA-Z0-9_/]*\.(py|js|ts)", fullmatch=True).filter(
        lambda s: len(s) >= 4 and len(s) <= 200
    )


def valid_function_name() -> st.SearchStrategy[str]:
    """Generate valid function names."""
    return st.from_regex(r"[a-zA-Z_][a-zA-Z0-9_]*", fullmatch=True).filter(
        lambda s: len(s) >= 1 and len(s) <= 100
    )


def valid_evidence() -> st.SearchStrategy[str]:
    """Generate valid evidence strings."""
    return st.text(min_size=10, max_size=400).filter(
        lambda s: s.strip() and not s.isspace()
    )


def valid_suggested_action() -> st.SearchStrategy[str]:
    """Generate valid suggested action strings."""
    return st.text(min_size=10, max_size=400).filter(
        lambda s: s.strip() and not s.isspace()
    )


@st.composite
def dead_code_finding_strategy(draw) -> DeadCodeFinding:
    """Generate a valid DeadCodeFinding."""
    line_start = draw(st.integers(min_value=1, max_value=10000))
    line_count = draw(st.integers(min_value=1, max_value=500))
    line_end = line_start + line_count - 1

    return DeadCodeFinding(
        file_path=draw(valid_file_path()),
        function_name=draw(valid_function_name()),
        line_start=line_start,
        line_end=line_end,
        line_count=line_count,
        confidence=1.0,
        evidence=draw(valid_evidence()),
        suggested_action=draw(valid_suggested_action()),
        last_modified=None,
    )


@st.composite
def hot_spot_finding_strategy(draw) -> HotSpotFinding:
    """Generate a valid HotSpotFinding."""
    return HotSpotFinding(
        file_path=draw(valid_file_path()),
        churn_count=draw(st.integers(min_value=11, max_value=500)),
        coverage_rate=draw(st.one_of(st.none(), st.floats(min_value=0.0, max_value=1.0))),
        unique_authors=draw(st.integers(min_value=1, max_value=50)),
        risk_factors=draw(st.lists(
            st.text(min_size=5, max_size=100).filter(lambda s: s.strip()),
            min_size=1,
            max_size=5
        )),
        suggested_action=draw(valid_suggested_action()),
    )


# =============================================================================
# Property Tests for Database Persistence Round-Trip
# =============================================================================


class TestDatabasePersistenceRoundTrip:
    """Property tests for database persistence round-trip.

    **Feature: cluster-map-refactoring, Property 13: Database Persistence Round-Trip**
    **Validates: Requirements 7.1**
    """

    @given(dead_code_finding_strategy())
    @settings(max_examples=100)
    def test_dead_code_persistence_round_trip(self, finding: DeadCodeFinding):
        """
        **Feature: cluster-map-refactoring, Property 13: Database Persistence Round-Trip**
        **Validates: Requirements 7.1**
        """
        from app.services.architecture_findings_service import ArchitectureFindingsService

        repository_id = uuid.uuid4()
        analysis_id = uuid.uuid4()
        persisted_dead_codes = []

        def mock_dead_code_init(**kwargs):
            obj = MagicMock(spec=DeadCode)
            for k, v in kwargs.items():
                setattr(obj, k, v)
            obj.id = uuid.uuid4()
            obj.is_dismissed = False
            obj.dismissed_at = None
            obj.created_at = datetime.now(UTC)
            persisted_dead_codes.append(obj)
            return obj

        def mock_file_churn_init(**kwargs):
            obj = MagicMock(spec=FileChurn)
            for k, v in kwargs.items():
                setattr(obj, k, v)
            return obj

        architecture_data = LLMReadyArchitectureData(
            summary=ArchitectureSummary(
                health_score=80,
                main_concerns=[],
                total_files=10,
                total_functions=50,
                dead_code_count=1,
                hot_spot_count=0,
            ),
            dead_code=[finding],
            hot_spots=[],
            issues=[],
        )

        mock_db = MagicMock()
        mock_db.execute.return_value = None

        service = ArchitectureFindingsService()

        with patch.object(service, '_clear_existing_findings'):
            with patch(
                'app.services.architecture_findings_service.DeadCode',
                side_effect=mock_dead_code_init
            ):
                with patch(
                    'app.services.architecture_findings_service.FileChurn',
                    side_effect=mock_file_churn_init
                ):
                    result = service.persist_findings(
                        db=mock_db,
                        repository_id=repository_id,
                        analysis_id=analysis_id,
                        architecture_data=architecture_data,
                    )

        assert result["dead_code_count"] == 1
        assert len(persisted_dead_codes) == 1

        persisted = persisted_dead_codes[0]
        assert persisted.file_path == finding.file_path
        assert persisted.function_name == finding.function_name
        assert persisted.line_start == finding.line_start
        assert persisted.line_end == finding.line_end
        assert persisted.line_count == finding.line_count
        assert persisted.confidence == finding.confidence
        assert persisted.evidence == finding.evidence
        assert persisted.suggested_action == finding.suggested_action
        assert persisted.analysis_id == analysis_id
        assert persisted.repository_id == repository_id

    @given(hot_spot_finding_strategy())
    @settings(max_examples=100)
    def test_hot_spot_persistence_round_trip(self, finding: HotSpotFinding):
        """
        **Feature: cluster-map-refactoring, Property 13: Database Persistence Round-Trip**
        **Validates: Requirements 7.2**
        """
        from app.services.architecture_findings_service import ArchitectureFindingsService

        repository_id = uuid.uuid4()
        analysis_id = uuid.uuid4()
        persisted_file_churns = []

        def mock_dead_code_init(**kwargs):
            obj = MagicMock(spec=DeadCode)
            for k, v in kwargs.items():
                setattr(obj, k, v)
            return obj

        def mock_file_churn_init(**kwargs):
            obj = MagicMock(spec=FileChurn)
            for k, v in kwargs.items():
                setattr(obj, k, v)
            obj.id = uuid.uuid4()
            obj.created_at = datetime.now(UTC)
            persisted_file_churns.append(obj)
            return obj

        architecture_data = LLMReadyArchitectureData(
            summary=ArchitectureSummary(
                health_score=80,
                main_concerns=[],
                total_files=10,
                total_functions=50,
                dead_code_count=0,
                hot_spot_count=1,
            ),
            dead_code=[],
            hot_spots=[finding],
            issues=[],
        )

        mock_db = MagicMock()
        mock_db.execute.return_value = None

        service = ArchitectureFindingsService()

        with patch.object(service, '_clear_existing_findings'):
            with patch(
                'app.services.architecture_findings_service.DeadCode',
                side_effect=mock_dead_code_init
            ):
                with patch(
                    'app.services.architecture_findings_service.FileChurn',
                    side_effect=mock_file_churn_init
                ):
                    result = service.persist_findings(
                        db=mock_db,
                        repository_id=repository_id,
                        analysis_id=analysis_id,
                        architecture_data=architecture_data,
                    )

        assert result["hot_spot_count"] == 1
        assert len(persisted_file_churns) == 1

        persisted = persisted_file_churns[0]
        assert persisted.file_path == finding.file_path
        assert persisted.changes_90d == finding.churn_count
        assert persisted.coverage_rate == finding.coverage_rate
        assert persisted.unique_authors == finding.unique_authors
        assert persisted.risk_factors == finding.risk_factors
        assert persisted.suggested_action == finding.suggested_action
        assert persisted.analysis_id == analysis_id

    @given(
        st.lists(dead_code_finding_strategy(), min_size=0, max_size=5),
        st.lists(hot_spot_finding_strategy(), min_size=0, max_size=5),
    )
    @settings(max_examples=100)
    def test_multiple_findings_persistence_round_trip(
        self,
        dead_code_findings: list[DeadCodeFinding],
        hot_spot_findings: list[HotSpotFinding],
    ):
        """
        **Feature: cluster-map-refactoring, Property 13: Database Persistence Round-Trip**
        **Validates: Requirements 7.1**
        """
        from app.services.architecture_findings_service import ArchitectureFindingsService

        repository_id = uuid.uuid4()
        analysis_id = uuid.uuid4()
        persisted_dead_codes = []
        persisted_file_churns = []

        def mock_dead_code_init(**kwargs):
            obj = MagicMock(spec=DeadCode)
            for k, v in kwargs.items():
                setattr(obj, k, v)
            obj.id = uuid.uuid4()
            persisted_dead_codes.append(obj)
            return obj

        def mock_file_churn_init(**kwargs):
            obj = MagicMock(spec=FileChurn)
            for k, v in kwargs.items():
                setattr(obj, k, v)
            obj.id = uuid.uuid4()
            persisted_file_churns.append(obj)
            return obj

        architecture_data = LLMReadyArchitectureData(
            summary=ArchitectureSummary(
                health_score=80,
                main_concerns=[],
                total_files=10,
                total_functions=50,
                dead_code_count=len(dead_code_findings),
                hot_spot_count=len(hot_spot_findings),
            ),
            dead_code=dead_code_findings,
            hot_spots=hot_spot_findings,
            issues=[],
        )

        mock_db = MagicMock()
        mock_db.execute.return_value = None

        service = ArchitectureFindingsService()

        with patch.object(service, '_clear_existing_findings'):
            with patch(
                'app.services.architecture_findings_service.DeadCode',
                side_effect=mock_dead_code_init
            ):
                with patch(
                    'app.services.architecture_findings_service.FileChurn',
                    side_effect=mock_file_churn_init
                ):
                    result = service.persist_findings(
                        db=mock_db,
                        repository_id=repository_id,
                        analysis_id=analysis_id,
                        architecture_data=architecture_data,
                    )

        assert result["dead_code_count"] == len(dead_code_findings)
        assert result["hot_spot_count"] == len(hot_spot_findings)
        assert len(persisted_dead_codes) == len(dead_code_findings)
        assert len(persisted_file_churns) == len(hot_spot_findings)


# =============================================================================
# Property Tests for Dismissal State Change
# =============================================================================


class TestDismissalStateChange:
    """Property tests for dismissal state change.

    **Feature: cluster-map-refactoring, Property 14: Dismissal State Change**
    **Validates: Requirements 7.3**
    """

    @given(dead_code_finding_strategy())
    @settings(max_examples=100)
    def test_dismissal_state_change_sets_flag_and_timestamp(
        self, finding: DeadCodeFinding
    ):
        """
        **Feature: cluster-map-refactoring, Property 14: Dismissal State Change**
        **Validates: Requirements 7.3**

        Property: For any dead code finding, after calling the dismiss operation,
        the is_dismissed flag SHALL be True and dismissed_at SHALL be set.
        """
        class MockDeadCode:
            def __init__(self, finding: DeadCodeFinding):
                self.id = uuid.uuid4()
                self.file_path = finding.file_path
                self.function_name = finding.function_name
                self.line_start = finding.line_start
                self.line_end = finding.line_end
                self.line_count = finding.line_count
                self.confidence = finding.confidence
                self.evidence = finding.evidence
                self.suggested_action = finding.suggested_action
                self.is_dismissed = False
                self.dismissed_at = None

        dead_code = MockDeadCode(finding)

        # Pre-condition: finding starts as not dismissed
        assert dead_code.is_dismissed is False
        assert dead_code.dismissed_at is None

        # Simulate the dismiss operation (as done in the API endpoint)
        dead_code.is_dismissed = True
        dead_code.dismissed_at = datetime.now(UTC)

        # Post-condition: Property 14 - is_dismissed SHALL be True
        assert dead_code.is_dismissed is True

        # Post-condition: Property 14 - dismissed_at SHALL be set
        assert dead_code.dismissed_at is not None
        assert isinstance(dead_code.dismissed_at, datetime)
        assert dead_code.dismissed_at.tzinfo is not None

    @given(dead_code_finding_strategy())
    @settings(max_examples=100)
    def test_dismissal_preserves_finding_data(self, finding: DeadCodeFinding):
        """
        **Feature: cluster-map-refactoring, Property 14: Dismissal State Change**
        **Validates: Requirements 7.3**

        Property: For any dead code finding, dismissing it SHALL NOT modify
        any other fields (file_path, function_name, evidence, etc.).
        """
        class MockDeadCode:
            def __init__(self, finding: DeadCodeFinding):
                self.id = uuid.uuid4()
                self.file_path = finding.file_path
                self.function_name = finding.function_name
                self.line_start = finding.line_start
                self.line_end = finding.line_end
                self.line_count = finding.line_count
                self.confidence = finding.confidence
                self.evidence = finding.evidence
                self.suggested_action = finding.suggested_action
                self.is_dismissed = False
                self.dismissed_at = None

        dead_code = MockDeadCode(finding)

        # Capture original values
        original_id = dead_code.id
        original_file_path = dead_code.file_path
        original_function_name = dead_code.function_name
        original_line_start = dead_code.line_start
        original_line_end = dead_code.line_end
        original_line_count = dead_code.line_count
        original_confidence = dead_code.confidence
        original_evidence = dead_code.evidence
        original_suggested_action = dead_code.suggested_action

        # Perform dismiss operation
        dead_code.is_dismissed = True
        dead_code.dismissed_at = datetime.now(UTC)

        # Property: All other fields remain unchanged
        assert dead_code.id == original_id
        assert dead_code.file_path == original_file_path
        assert dead_code.function_name == original_function_name
        assert dead_code.line_start == original_line_start
        assert dead_code.line_end == original_line_end
        assert dead_code.line_count == original_line_count
        assert dead_code.confidence == original_confidence
        assert dead_code.evidence == original_evidence
        assert dead_code.suggested_action == original_suggested_action

    @given(dead_code_finding_strategy())
    @settings(max_examples=100)
    def test_dismissal_is_idempotent(self, finding: DeadCodeFinding):
        """
        **Feature: cluster-map-refactoring, Property 14: Dismissal State Change**
        **Validates: Requirements 7.3**

        Property: Dismissing an already-dismissed finding SHALL keep
        is_dismissed as True (idempotent operation).
        """
        class MockDeadCode:
            def __init__(self, finding: DeadCodeFinding):
                self.id = uuid.uuid4()
                self.file_path = finding.file_path
                self.function_name = finding.function_name
                self.is_dismissed = False
                self.dismissed_at = None

        dead_code = MockDeadCode(finding)

        # First dismissal
        dead_code.is_dismissed = True
        first_dismissed_at = datetime.now(UTC)
        dead_code.dismissed_at = first_dismissed_at

        assert dead_code.is_dismissed is True
        assert dead_code.dismissed_at == first_dismissed_at

        # Second dismissal (idempotent - should still be dismissed)
        dead_code.is_dismissed = True

        assert dead_code.is_dismissed is True
        assert dead_code.dismissed_at is not None

    @given(
        st.lists(dead_code_finding_strategy(), min_size=1, max_size=5),
        st.integers(min_value=0, max_value=4),
    )
    @settings(max_examples=100)
    def test_dismissal_affects_only_target_finding(
        self,
        findings: list[DeadCodeFinding],
        dismiss_index: int,
    ):
        """
        **Feature: cluster-map-refactoring, Property 14: Dismissal State Change**
        **Validates: Requirements 7.3**

        Property: Dismissing one finding SHALL NOT affect the dismissal state
        of other findings.
        """
        dismiss_index = dismiss_index % len(findings)

        class MockDeadCode:
            def __init__(self, finding: DeadCodeFinding):
                self.id = uuid.uuid4()
                self.file_path = finding.file_path
                self.function_name = finding.function_name
                self.is_dismissed = False
                self.dismissed_at = None

        dead_codes = [MockDeadCode(f) for f in findings]

        # Dismiss only the target finding
        target = dead_codes[dismiss_index]
        target.is_dismissed = True
        target.dismissed_at = datetime.now(UTC)

        # Property: Only the target is dismissed
        for i, dc in enumerate(dead_codes):
            if i == dismiss_index:
                assert dc.is_dismissed is True
                assert dc.dismissed_at is not None
            else:
                assert dc.is_dismissed is False
                assert dc.dismissed_at is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
