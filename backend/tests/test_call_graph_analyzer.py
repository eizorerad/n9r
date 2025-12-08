"""Property-based tests for Call Graph Analyzer.

Uses Hypothesis for property-based testing to verify correctness properties
defined in the design document for the cluster-map-refactoring feature.

Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 4.2
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from app.services.call_graph_analyzer import (
    TREE_SITTER_AVAILABLE,
    CallGraph,
    CallGraphAnalyzer,
    CallGraphNode,
    is_entry_point,
)


# =============================================================================
# Custom Strategies for Python Function Generation
# =============================================================================


def valid_python_identifier() -> st.SearchStrategy[str]:
    """Generate valid Python identifiers (function names)."""
    return st.from_regex(r"[a-zA-Z_][a-zA-Z0-9_]*", fullmatch=True).filter(
        lambda s: len(s) >= 1 and len(s) <= 50 and s not in {"def", "class", "return", "if", "else", "for", "while", "import", "from", "pass", "None", "True", "False"}
    )


def valid_file_path() -> st.SearchStrategy[str]:
    """Generate valid file paths."""
    return st.from_regex(r"[a-zA-Z_][a-zA-Z0-9_/]*\.py", fullmatch=True).filter(
        lambda s: len(s) >= 4 and len(s) <= 100
    )


@st.composite
def python_function_definition(draw) -> tuple[str, str, int, int]:
    """Generate a Python function definition.

    Returns:
        A tuple of (code_string, function_name, line_start, line_end)
    """
    name = draw(valid_python_identifier())
    # Generate function body with 1-5 lines
    body_lines = draw(st.integers(min_value=1, max_value=5))
    body = "\n".join(["    pass"] * body_lines)

    code = f"def {name}():\n{body}"
    line_start = 1
    line_end = 1 + body_lines

    return code, name, line_start, line_end


@st.composite
def python_file_with_functions(draw) -> tuple[str, list[tuple[str, int, int]]]:
    """Generate a Python file with multiple function definitions.

    Returns:
        A tuple of (code_string, list of (function_name, line_start, line_end))
    """
    num_functions = draw(st.integers(min_value=1, max_value=5))
    functions = []
    code_lines = []
    current_line = 1

    for _ in range(num_functions):
        name = draw(valid_python_identifier())
        body_lines = draw(st.integers(min_value=1, max_value=3))
        body = "\n".join(["    pass"] * body_lines)

        func_code = f"def {name}():\n{body}"
        code_lines.append(func_code)
        code_lines.append("")  # Empty line between functions

        line_start = current_line
        line_end = current_line + body_lines
        functions.append((name, line_start, line_end))

        current_line = line_end + 2  # +2 for the empty line

    code = "\n".join(code_lines)
    return code, functions


# =============================================================================
# Custom Strategies for Entry Point Names
# =============================================================================


def entry_point_name() -> st.SearchStrategy[str]:
    """Generate function names that should be classified as entry points."""
    return st.one_of(
        st.just("main"),
        st.just("__init__"),
        st.from_regex(r"test_[a-zA-Z0-9_]+", fullmatch=True).filter(lambda s: len(s) <= 50),
        st.from_regex(r"[a-zA-Z0-9_]+_handler", fullmatch=True).filter(lambda s: len(s) <= 50),
        st.from_regex(r"[a-zA-Z0-9_]+_route", fullmatch=True).filter(lambda s: len(s) <= 50),
        st.from_regex(r"[a-zA-Z0-9_]+_endpoint", fullmatch=True).filter(lambda s: len(s) <= 50),
        st.from_regex(r"[a-zA-Z0-9_]+_view", fullmatch=True).filter(lambda s: len(s) <= 50),
    )


def non_entry_point_name() -> st.SearchStrategy[str]:
    """Generate function names that should NOT be classified as entry points."""
    return st.from_regex(r"[a-zA-Z_][a-zA-Z0-9_]*", fullmatch=True).filter(
        lambda s: (
            len(s) >= 2
            and len(s) <= 50
            and s != "main"
            and s != "__init__"
            and not s.startswith("test_")
            and not s.endswith("_handler")
            and not s.endswith("_route")
            and not s.endswith("_endpoint")
            and not s.endswith("_view")
            and s not in {"def", "class", "return", "if", "else", "for", "while", "import", "from", "pass", "None", "True", "False"}
        )
    )


# =============================================================================
# Custom Strategies for Call Graph Generation
# =============================================================================


@st.composite
def call_graph_with_entry_points(draw) -> CallGraph:
    """Generate a call graph with entry points and some reachable/unreachable nodes."""
    num_entry_points = draw(st.integers(min_value=1, max_value=3))
    num_reachable = draw(st.integers(min_value=0, max_value=5))
    num_unreachable = draw(st.integers(min_value=0, max_value=5))

    call_graph = CallGraph()

    # Create entry points
    entry_point_ids = []
    for i in range(num_entry_points):
        name = f"entry_{i}"
        node_id = f"test.py:{name}"
        call_graph.nodes[node_id] = CallGraphNode(
            id=node_id,
            file_path="test.py",
            name=name,
            line_start=i * 10 + 1,
            line_end=i * 10 + 5,
            is_entry_point=True,
        )
        call_graph.entry_points.append(node_id)
        entry_point_ids.append(node_id)

    # Create reachable nodes (called by entry points or other reachable nodes)
    reachable_ids = []
    for i in range(num_reachable):
        name = f"reachable_{i}"
        node_id = f"test.py:{name}"
        call_graph.nodes[node_id] = CallGraphNode(
            id=node_id,
            file_path="test.py",
            name=name,
            line_start=100 + i * 10,
            line_end=100 + i * 10 + 5,
            is_entry_point=False,
        )
        reachable_ids.append(node_id)

        # Link from an entry point or previous reachable node
        if i == 0:
            caller_id = draw(st.sampled_from(entry_point_ids))
        else:
            caller_id = draw(st.sampled_from(entry_point_ids + reachable_ids[:-1]))

        call_graph.nodes[caller_id].calls.add(node_id)
        call_graph.nodes[node_id].called_by.add(caller_id)

    # Create unreachable nodes (not called by anyone)
    for i in range(num_unreachable):
        name = f"unreachable_{i}"
        node_id = f"test.py:{name}"
        call_graph.nodes[node_id] = CallGraphNode(
            id=node_id,
            file_path="test.py",
            name=name,
            line_start=200 + i * 10,
            line_end=200 + i * 10 + 5,
            is_entry_point=False,
        )

    return call_graph


# =============================================================================
# Property Tests for Call Graph Node Completeness
# =============================================================================


class TestCallGraphNodeCompletenessProperties:
    """Property tests for call graph node completeness.

    **Feature: cluster-map-refactoring, Property 1: Call Graph Node Completeness**
    **Validates: Requirements 1.1**
    """

    @pytest.mark.skipif(not TREE_SITTER_AVAILABLE, reason="tree-sitter not installed")
    @given(python_file_with_functions())
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_call_graph_node_completeness(self, code_and_functions: tuple[str, list[tuple[str, int, int]]]):
        """
        **Feature: cluster-map-refactoring, Property 1: Call Graph Node Completeness**
        **Validates: Requirements 1.1**

        Property: For any valid Python source file, when parsed by CallGraphAnalyzer,
        every function definition SHALL produce a CallGraphNode with non-empty id,
        file_path, name, and valid line_start <= line_end.
        """
        code, expected_functions = code_and_functions

        # Create a temporary file with the code
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)
            test_file = repo_path / "test_module.py"
            test_file.write_text(code)

            # Analyze the repository
            analyzer = CallGraphAnalyzer()
            call_graph = analyzer.analyze(repo_path)

            # Verify each expected function has a corresponding node
            for func_name, expected_start, expected_end in expected_functions:
                node_id = f"test_module.py:{func_name}"

                # Property 1: Node exists
                assert node_id in call_graph.nodes, (
                    f"Function '{func_name}' not found in call graph.\n"
                    f"Expected node_id: {node_id}\n"
                    f"Available nodes: {list(call_graph.nodes.keys())}\n"
                    f"Code:\n{code}"
                )

                node = call_graph.nodes[node_id]

                # Property 2: Non-empty id
                assert node.id, f"Node id is empty for function '{func_name}'"

                # Property 3: Non-empty file_path
                assert node.file_path, f"Node file_path is empty for function '{func_name}'"

                # Property 4: Non-empty name
                assert node.name, f"Node name is empty for function '{func_name}'"

                # Property 5: Valid line range (line_start <= line_end)
                assert node.line_start <= node.line_end, (
                    f"Invalid line range for function '{func_name}': "
                    f"line_start={node.line_start}, line_end={node.line_end}"
                )

                # Property 6: Line numbers are positive
                assert node.line_start > 0, f"line_start must be positive for function '{func_name}'"
                assert node.line_end > 0, f"line_end must be positive for function '{func_name}'"


# =============================================================================
# Property Tests for Entry Point Classification
# =============================================================================


class TestEntryPointClassificationProperties:
    """Property tests for entry point classification.

    **Feature: cluster-map-refactoring, Property 2: Entry Point Classification**
    **Validates: Requirements 1.2**
    """

    @given(entry_point_name())
    @settings(max_examples=100)
    def test_entry_point_names_classified_correctly(self, name: str):
        """
        **Feature: cluster-map-refactoring, Property 2: Entry Point Classification**
        **Validates: Requirements 1.2**

        Property: For any function with name matching entry point patterns
        (main, __init__, test_*, *_handler, *_route, *_endpoint, *_view),
        the is_entry_point function SHALL return True.
        """
        result = is_entry_point(name)
        assert result is True, (
            f"Function '{name}' should be classified as entry point but was not.\n"
            f"is_entry_point('{name}') returned {result}"
        )

    @given(non_entry_point_name())
    @settings(max_examples=100)
    def test_non_entry_point_names_classified_correctly(self, name: str):
        """
        **Feature: cluster-map-refactoring, Property 2: Entry Point Classification**
        **Validates: Requirements 1.2**

        Property: For any function with name NOT matching entry point patterns,
        the is_entry_point function SHALL return False.
        """
        result = is_entry_point(name)
        assert result is False, (
            f"Function '{name}' should NOT be classified as entry point but was.\n"
            f"is_entry_point('{name}') returned {result}"
        )


# =============================================================================
# Property Tests for Reachability Partition
# =============================================================================


class TestReachabilityPartitionProperties:
    """Property tests for reachability partition.

    **Feature: cluster-map-refactoring, Property 3: Reachability Partition**
    **Validates: Requirements 1.3, 1.4**
    """

    @given(call_graph_with_entry_points())
    @settings(max_examples=100)
    def test_reachability_partition(self, call_graph: CallGraph):
        """
        **Feature: cluster-map-refactoring, Property 3: Reachability Partition**
        **Validates: Requirements 1.3, 1.4**

        Property: For any call graph with defined entry points, the set of all nodes
        SHALL be partitioned into exactly two disjoint sets: reachable (transitively
        called from entry points) and unreachable (dead code), with no overlap.
        """
        # Get unreachable nodes
        unreachable = call_graph.get_unreachable()
        unreachable_ids = {node.id for node in unreachable}

        # Calculate reachable nodes (complement of unreachable)
        all_node_ids = set(call_graph.nodes.keys())
        reachable_ids = all_node_ids - unreachable_ids

        # Property 1: Partition is complete (union equals all nodes)
        assert reachable_ids | unreachable_ids == all_node_ids, (
            "Partition is not complete - some nodes are missing.\n"
            f"All nodes: {all_node_ids}\n"
            f"Reachable: {reachable_ids}\n"
            f"Unreachable: {unreachable_ids}"
        )

        # Property 2: Partition is disjoint (no overlap)
        assert reachable_ids & unreachable_ids == set(), (
            "Partition is not disjoint - some nodes are in both sets.\n"
            f"Overlap: {reachable_ids & unreachable_ids}"
        )

        # Property 3: All entry points are reachable
        for entry_id in call_graph.entry_points:
            assert entry_id in reachable_ids, (
                f"Entry point '{entry_id}' is not in reachable set"
            )

        # Property 4: Unreachable nodes have no path from entry points
        for unreachable_node in unreachable:
            # Verify no entry point can reach this node
            for entry_id in call_graph.entry_points:
                assert not self._can_reach(call_graph, entry_id, unreachable_node.id), (
                    f"Unreachable node '{unreachable_node.id}' is actually reachable from '{entry_id}'"
                )

    def _can_reach(self, call_graph: CallGraph, from_id: str, to_id: str) -> bool:
        """Check if from_id can reach to_id through calls."""
        visited = set()
        to_visit = [from_id]

        while to_visit:
            current = to_visit.pop(0)
            if current == to_id:
                return True
            if current in visited:
                continue
            visited.add(current)

            if current in call_graph.nodes:
                for called_id in call_graph.nodes[current].calls:
                    if called_id not in visited:
                        to_visit.append(called_id)

        return False


# =============================================================================
# Property Tests for Dead Code Finding Format
# =============================================================================


class TestDeadCodeFindingFormatProperties:
    """Property tests for dead code finding format.

    **Feature: cluster-map-refactoring, Property 4: Dead Code Finding Format**
    **Validates: Requirements 1.5, 4.2**
    """

    @given(call_graph_with_entry_points())
    @settings(max_examples=100)
    def test_dead_code_finding_format(self, call_graph: CallGraph):
        """
        **Feature: cluster-map-refactoring, Property 4: Dead Code Finding Format**
        **Validates: Requirements 1.5, 4.2**

        Property: For any dead code finding, the DeadCodeFinding SHALL have:
        non-empty file_path, non-empty function_name, line_count > 0,
        confidence == 1.0, non-empty evidence string, and non-empty suggested_action string.
        """
        analyzer = CallGraphAnalyzer()
        findings = analyzer.to_dead_code_findings(call_graph)

        # Get expected unreachable count
        unreachable = call_graph.get_unreachable()

        # Property 1: Number of findings matches unreachable nodes
        assert len(findings) == len(unreachable), (
            f"Number of findings ({len(findings)}) doesn't match "
            f"unreachable nodes ({len(unreachable)})"
        )

        for finding in findings:
            # Property 2: Non-empty file_path
            assert finding.file_path, (
                f"file_path is empty for finding: {finding}"
            )

            # Property 3: Non-empty function_name
            assert finding.function_name, (
                f"function_name is empty for finding: {finding}"
            )

            # Property 4: line_count > 0
            assert finding.line_count > 0, (
                f"line_count must be > 0, got {finding.line_count} for {finding.function_name}"
            )

            # Property 5: confidence == 1.0 (call-graph proven)
            assert finding.confidence == 1.0, (
                f"confidence must be 1.0 for call-graph proven dead code, "
                f"got {finding.confidence} for {finding.function_name}"
            )

            # Property 6: Non-empty evidence string
            assert finding.evidence, (
                f"evidence is empty for finding: {finding.function_name}"
            )

            # Property 7: Non-empty suggested_action string
            assert finding.suggested_action, (
                f"suggested_action is empty for finding: {finding.function_name}"
            )

            # Property 8: Evidence is human-readable (contains function name)
            assert finding.function_name in finding.evidence, (
                f"evidence should mention function name '{finding.function_name}', "
                f"but got: '{finding.evidence}'"
            )

            # Property 9: Suggested action is human-readable
            assert len(finding.suggested_action) > 10, (
                f"suggested_action should be a meaningful sentence, "
                f"got: '{finding.suggested_action}'"
            )
