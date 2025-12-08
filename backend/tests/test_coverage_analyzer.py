"""Property-based tests for Coverage Analyzer.

Uses Hypothesis for property-based testing to verify correctness properties
defined in the design document for the cluster-map-refactoring feature.

Requirements: 3.1, 3.2
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.services.coverage_analyzer import CoverageAnalyzer


# =============================================================================
# Custom Strategies for Cobertura XML Generation
# =============================================================================


@st.composite
def valid_file_path(draw) -> str:
    """Generate valid file paths for coverage data."""
    return draw(
        st.from_regex(
            r"[a-zA-Z_][a-zA-Z0-9_/]*\.(py|js|ts|tsx)",
            fullmatch=True
        ).filter(lambda s: 4 <= len(s) <= 100)
    )


@st.composite
def valid_coverage_rate(draw) -> float:
    """Generate valid coverage rates in [0.0, 1.0]."""
    return draw(st.floats(min_value=0.0, max_value=1.0, allow_nan=False))


@st.composite
def coverage_file_entry(draw) -> tuple[str, float]:
    """Generate a single file coverage entry."""
    # Generate unique path with index to avoid collisions
    base_path = draw(valid_file_path())
    index = draw(st.integers(min_value=0, max_value=999))
    file_path = f"src/module_{index}/{base_path}"
    coverage_rate = draw(valid_coverage_rate())
    return (file_path, coverage_rate)


@st.composite
def cobertura_xml_content(draw) -> tuple[str, dict[str, float]]:
    """Generate valid Cobertura XML content with expected coverage data.
    
    Returns:
        Tuple of (xml_string, expected_coverage_dict)
    """
    num_files = draw(st.integers(min_value=1, max_value=20))
    
    expected_coverage: dict[str, float] = {}
    class_elements: list[str] = []
    
    for i in range(num_files):
        file_path = f"src/module_{i}/file_{i}.py"
        coverage_rate = draw(valid_coverage_rate())
        expected_coverage[file_path] = coverage_rate
        
        class_elements.append(
            f'<class filename="{file_path}" line-rate="{coverage_rate:.6f}">'
            f'<lines></lines></class>'
        )
    
    xml_content = f'''<?xml version="1.0" ?>
<coverage version="1.0">
    <packages>
        <package name="src">
            <classes>
                {chr(10).join(class_elements)}
            </classes>
        </package>
    </packages>
</coverage>'''
    
    return (xml_content, expected_coverage)


# =============================================================================
# Property Tests for Coverage Parsing
# =============================================================================


class TestCoverageParsingProperties:
    """Property tests for coverage parsing.

    **Feature: cluster-map-refactoring, Property 8: Coverage Parsing**
    **Validates: Requirements 3.1**
    """

    @given(cobertura_xml_content())
    @settings(max_examples=100)
    def test_coverage_rates_in_valid_range(
        self, xml_and_expected: tuple[str, dict[str, float]]
    ):
        """
        **Feature: cluster-map-refactoring, Property 8: Coverage Parsing**
        **Validates: Requirements 3.1**

        Property: For any valid Cobertura XML coverage report, parsing SHALL
        produce coverage rates in range [0.0, 1.0] for each file.
        """
        xml_content, _ = xml_and_expected
        
        analyzer = CoverageAnalyzer()
        coverage_data = analyzer.parse_cobertura_xml_string(xml_content)
        
        # Property: All coverage rates must be in [0.0, 1.0]
        for file_path, rate in coverage_data.items():
            assert 0.0 <= rate <= 1.0, (
                f"Coverage rate for {file_path} must be in [0.0, 1.0], got {rate}"
            )

    @given(cobertura_xml_content())
    @settings(max_examples=100)
    def test_coverage_parsing_preserves_files(
        self, xml_and_expected: tuple[str, dict[str, float]]
    ):
        """
        **Feature: cluster-map-refactoring, Property 8: Coverage Parsing**
        **Validates: Requirements 3.1**

        Property: For any valid Cobertura XML, all files in the XML SHALL
        appear in the parsed output.
        """
        xml_content, expected_coverage = xml_and_expected
        
        analyzer = CoverageAnalyzer()
        coverage_data = analyzer.parse_cobertura_xml_string(xml_content)
        
        # Property: All expected files should be present
        for file_path in expected_coverage:
            assert file_path in coverage_data, (
                f"File {file_path} should be in parsed coverage data"
            )

    @given(cobertura_xml_content())
    @settings(max_examples=100)
    def test_coverage_parsing_accuracy(
        self, xml_and_expected: tuple[str, dict[str, float]]
    ):
        """
        **Feature: cluster-map-refactoring, Property 8: Coverage Parsing**
        **Validates: Requirements 3.1**

        Property: For any valid Cobertura XML, parsed coverage rates SHALL
        match the values in the XML (within floating point tolerance).
        """
        xml_content, expected_coverage = xml_and_expected
        
        analyzer = CoverageAnalyzer()
        coverage_data = analyzer.parse_cobertura_xml_string(xml_content)
        
        # Property: Coverage rates should match expected values
        for file_path, expected_rate in expected_coverage.items():
            actual_rate = coverage_data.get(file_path)
            assert actual_rate is not None, (
                f"File {file_path} should have coverage data"
            )
            assert abs(actual_rate - expected_rate) < 1e-5, (
                f"Coverage rate for {file_path} should be {expected_rate}, "
                f"got {actual_rate}"
            )


# =============================================================================
# Property Tests for Missing Coverage File
# =============================================================================


class TestCoverageMissingFileProperties:
    """Property tests for graceful degradation when coverage file is missing.

    **Validates: Requirements 3.3**
    """

    def test_returns_none_when_no_coverage_file(self):
        """
        **Validates: Requirements 3.3**

        Property: When coverage file is not found, parse_if_exists SHALL
        return None.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)
            
            analyzer = CoverageAnalyzer()
            result = analyzer.parse_if_exists(repo_path)
            
            assert result is None, (
                "Should return None when no coverage file exists"
            )

    def test_parses_existing_coverage_file(self):
        """
        **Validates: Requirements 3.1**

        Property: When coverage.xml exists, parse_if_exists SHALL return
        a dictionary of coverage data.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)
            
            # Create a coverage.xml file
            coverage_xml = '''<?xml version="1.0" ?>
<coverage version="1.0">
    <packages>
        <package name="src">
            <classes>
                <class filename="src/main.py" line-rate="0.85">
                    <lines></lines>
                </class>
            </classes>
        </package>
    </packages>
</coverage>'''
            
            coverage_file = repo_path / "coverage.xml"
            coverage_file.write_text(coverage_xml)
            
            analyzer = CoverageAnalyzer()
            result = analyzer.parse_if_exists(repo_path)
            
            assert result is not None, "Should return coverage data"
            assert "src/main.py" in result, "Should contain src/main.py"
            assert abs(result["src/main.py"] - 0.85) < 1e-5, (
                f"Coverage should be 0.85, got {result['src/main.py']}"
            )


# =============================================================================
# Edge Case Tests
# =============================================================================


class TestCoverageEdgeCases:
    """Edge case tests for coverage parsing."""

    def test_handles_empty_coverage_file(self):
        """Test handling of empty coverage XML."""
        xml_content = '''<?xml version="1.0" ?>
<coverage version="1.0">
    <packages>
    </packages>
</coverage>'''
        
        analyzer = CoverageAnalyzer()
        coverage_data = analyzer.parse_cobertura_xml_string(xml_content)
        
        assert coverage_data == {}, "Empty coverage should return empty dict"

    def test_handles_invalid_line_rate(self):
        """Test handling of invalid line-rate values."""
        xml_content = '''<?xml version="1.0" ?>
<coverage version="1.0">
    <packages>
        <package name="src">
            <classes>
                <class filename="src/valid.py" line-rate="0.75">
                    <lines></lines>
                </class>
                <class filename="src/invalid.py" line-rate="not-a-number">
                    <lines></lines>
                </class>
            </classes>
        </package>
    </packages>
</coverage>'''
        
        analyzer = CoverageAnalyzer()
        coverage_data = analyzer.parse_cobertura_xml_string(xml_content)
        
        # Valid file should be parsed
        assert "src/valid.py" in coverage_data
        assert abs(coverage_data["src/valid.py"] - 0.75) < 1e-5
        
        # Invalid file should be skipped
        assert "src/invalid.py" not in coverage_data

    def test_clamps_out_of_range_values(self):
        """Test that out-of-range values are clamped to [0.0, 1.0]."""
        xml_content = '''<?xml version="1.0" ?>
<coverage version="1.0">
    <packages>
        <package name="src">
            <classes>
                <class filename="src/negative.py" line-rate="-0.5">
                    <lines></lines>
                </class>
                <class filename="src/over_one.py" line-rate="1.5">
                    <lines></lines>
                </class>
            </classes>
        </package>
    </packages>
</coverage>'''
        
        analyzer = CoverageAnalyzer()
        coverage_data = analyzer.parse_cobertura_xml_string(xml_content)
        
        # Negative should be clamped to 0.0
        assert coverage_data["src/negative.py"] == 0.0
        
        # Over 1.0 should be clamped to 1.0
        assert coverage_data["src/over_one.py"] == 1.0


# =============================================================================
# Property Tests for Coverage in Risk Factors (Property 9)
# =============================================================================


class TestCoverageInRiskFactorsProperties:
    """Property tests for coverage integration with risk factors.

    **Feature: cluster-map-refactoring, Property 9: Coverage in Risk Factors**
    **Validates: Requirements 3.2**
    """

    @given(st.floats(min_value=0.0, max_value=0.49, allow_nan=False))
    @settings(max_examples=100, deadline=None)
    def test_low_coverage_mentioned_in_risk_factors(self, coverage_rate: float):
        """
        **Feature: cluster-map-refactoring, Property 9: Coverage in Risk Factors**
        **Validates: Requirements 3.2**

        Property: For any hot spot with coverage_rate < 0.5, the risk_factors
        list SHALL contain a string mentioning low test coverage.
        """
        from app.services.git_analyzer import FileChurn, GitAnalyzer

        # Create a file with high churn (above threshold)
        churn = FileChurn(
            file_path="src/test_file.py",
            changes_30d=15,
            changes_90d=20,  # Above default threshold of 10
            lines_added_90d=100,
            lines_removed_90d=50,
            unique_authors=2,
        )

        analyzer = GitAnalyzer()
        churn_data = {churn.file_path: churn}
        coverage_data = {churn.file_path: coverage_rate}

        findings = analyzer.to_hot_spot_findings(
            churn_data, coverage_data=coverage_data, threshold=10
        )

        assert len(findings) == 1, "Should have exactly one finding"
        finding = findings[0]

        # Property: Risk factors should mention low coverage
        coverage_mentioned = any(
            "coverage" in factor.lower() for factor in finding.risk_factors
        )
        assert coverage_mentioned, (
            f"Low coverage ({coverage_rate:.0%}) should be mentioned in risk factors.\n"
            f"Risk factors: {finding.risk_factors}"
        )

        # Property: Coverage rate should be stored in finding
        assert finding.coverage_rate is not None, (
            "coverage_rate should be set in finding"
        )
        assert abs(finding.coverage_rate - coverage_rate) < 1e-5, (
            f"coverage_rate should be {coverage_rate}, got {finding.coverage_rate}"
        )

    @given(st.floats(min_value=0.5, max_value=1.0, allow_nan=False))
    @settings(max_examples=100, deadline=None)
    def test_adequate_coverage_not_flagged_as_low(self, coverage_rate: float):
        """
        **Feature: cluster-map-refactoring, Property 9: Coverage in Risk Factors**
        **Validates: Requirements 3.2**

        Property: For any hot spot with coverage_rate >= 0.5, the risk_factors
        list SHALL NOT contain a string mentioning "low" test coverage.
        """
        from app.services.git_analyzer import FileChurn, GitAnalyzer

        # Create a file with high churn (above threshold)
        churn = FileChurn(
            file_path="src/test_file.py",
            changes_30d=15,
            changes_90d=20,  # Above default threshold of 10
            lines_added_90d=100,
            lines_removed_90d=50,
            unique_authors=2,
        )

        analyzer = GitAnalyzer()
        churn_data = {churn.file_path: churn}
        coverage_data = {churn.file_path: coverage_rate}

        findings = analyzer.to_hot_spot_findings(
            churn_data, coverage_data=coverage_data, threshold=10
        )

        assert len(findings) == 1, "Should have exactly one finding"
        finding = findings[0]

        # Property: Risk factors should NOT mention "low" coverage
        low_coverage_mentioned = any(
            "low" in factor.lower() and "coverage" in factor.lower()
            for factor in finding.risk_factors
        )
        assert not low_coverage_mentioned, (
            f"Adequate coverage ({coverage_rate:.0%}) should NOT be flagged as low.\n"
            f"Risk factors: {finding.risk_factors}"
        )

    def test_missing_coverage_noted_in_risk_factors(self):
        """
        **Feature: cluster-map-refactoring, Property 9: Coverage in Risk Factors**
        **Validates: Requirements 3.3**

        Property: When coverage data is unavailable, risk_factors SHALL
        note that coverage data is unavailable.
        """
        from app.services.git_analyzer import FileChurn, GitAnalyzer

        # Create a file with high churn (above threshold)
        churn = FileChurn(
            file_path="src/test_file.py",
            changes_30d=15,
            changes_90d=20,  # Above default threshold of 10
            lines_added_90d=100,
            lines_removed_90d=50,
            unique_authors=2,
        )

        analyzer = GitAnalyzer()
        churn_data = {churn.file_path: churn}

        # No coverage data provided
        findings = analyzer.to_hot_spot_findings(
            churn_data, coverage_data=None, threshold=10
        )

        assert len(findings) == 1, "Should have exactly one finding"
        finding = findings[0]

        # Property: Risk factors should note coverage unavailable
        unavailable_mentioned = any(
            "unavailable" in factor.lower() for factor in finding.risk_factors
        )
        assert unavailable_mentioned, (
            f"Missing coverage should be noted as unavailable.\n"
            f"Risk factors: {finding.risk_factors}"
        )

        # Property: coverage_rate should be None
        assert finding.coverage_rate is None, (
            "coverage_rate should be None when coverage data unavailable"
        )
