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
    AnalyzerConfig,
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
            for func_name, _expected_start, _expected_end in expected_functions:
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


# =============================================================================
# Tests for Enhanced Entry Point Detection (Framework Patterns)
# =============================================================================


class TestFrameworkEntryPointDetection:
    """Tests for framework-specific entry point detection.

    Validates that the analyzer correctly identifies:
    - FastAPI route decorators
    - Celery task decorators
    - Pytest fixtures
    - Pydantic validators
    - Functions passed as callbacks
    - Test file functions
    """

    @pytest.mark.skipif(not TREE_SITTER_AVAILABLE, reason="tree-sitter not installed")
    def test_fastapi_route_decorator_is_entry_point(self):
        """FastAPI route handlers should be detected as entry points."""
        code = '''
from fastapi import FastAPI

app = FastAPI()

@app.get("/")
def root():
    return {"message": "Hello"}

@app.post("/users")
async def create_user():
    return {"id": 1}
'''
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)
            test_file = repo_path / "main.py"
            test_file.write_text(code)

            analyzer = CallGraphAnalyzer()
            call_graph = analyzer.analyze(repo_path)

            # Both route handlers should be entry points
            root_node = call_graph.nodes.get("main.py:root")
            create_user_node = call_graph.nodes.get("main.py:create_user")

            assert root_node is not None, "root function not found"
            assert create_user_node is not None, "create_user function not found"
            assert root_node.is_entry_point, "root should be entry point (FastAPI route)"
            assert create_user_node.is_entry_point, "create_user should be entry point (FastAPI route)"

    @pytest.mark.skipif(not TREE_SITTER_AVAILABLE, reason="tree-sitter not installed")
    def test_pytest_fixture_is_entry_point(self):
        """Pytest fixtures should be detected as entry points."""
        code = '''
import pytest

@pytest.fixture
def db_session():
    return "session"

@pytest.fixture(scope="module")
def app_client():
    return "client"
'''
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)
            test_file = repo_path / "conftest.py"
            test_file.write_text(code)

            analyzer = CallGraphAnalyzer()
            call_graph = analyzer.analyze(repo_path)

            db_session_node = call_graph.nodes.get("conftest.py:db_session")
            app_client_node = call_graph.nodes.get("conftest.py:app_client")

            assert db_session_node is not None
            assert app_client_node is not None
            # conftest.py is an entry point file, so all functions are entry points
            assert db_session_node.is_entry_point, "db_session should be entry point"
            assert app_client_node.is_entry_point, "app_client should be entry point"

    @pytest.mark.skipif(not TREE_SITTER_AVAILABLE, reason="tree-sitter not installed")
    def test_celery_task_is_entry_point(self):
        """Celery tasks should be detected as entry points."""
        code = '''
from celery import shared_task

@shared_task
def process_data(data):
    return data

@shared_task(bind=True)
def long_running_task(self, item_id):
    return item_id
'''
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)
            test_file = repo_path / "tasks.py"
            test_file.write_text(code)

            analyzer = CallGraphAnalyzer()
            call_graph = analyzer.analyze(repo_path)

            process_node = call_graph.nodes.get("tasks.py:process_data")
            long_running_node = call_graph.nodes.get("tasks.py:long_running_task")

            assert process_node is not None
            assert long_running_node is not None
            assert process_node.is_entry_point, "Celery task should be entry point"
            assert long_running_node.is_entry_point, "Celery task should be entry point"

    @pytest.mark.skipif(not TREE_SITTER_AVAILABLE, reason="tree-sitter not installed")
    def test_pydantic_validator_is_entry_point(self):
        """Pydantic validators should be detected as entry points."""
        code = '''
from pydantic import BaseModel, model_validator, field_validator

class User(BaseModel):
    name: str
    email: str

    @model_validator(mode="before")
    def validate_model(cls, values):
        return values

    @field_validator("email")
    def validate_email(cls, v):
        return v
'''
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)
            test_file = repo_path / "models.py"
            test_file.write_text(code)

            analyzer = CallGraphAnalyzer()
            call_graph = analyzer.analyze(repo_path)

            validate_model_node = call_graph.nodes.get("models.py:validate_model")
            validate_email_node = call_graph.nodes.get("models.py:validate_email")

            assert validate_model_node is not None
            assert validate_email_node is not None
            assert validate_model_node.is_entry_point, "model_validator should be entry point"
            assert validate_email_node.is_entry_point, "field_validator should be entry point"

    @pytest.mark.skipif(not TREE_SITTER_AVAILABLE, reason="tree-sitter not installed")
    def test_callback_passed_as_argument_is_entry_point(self):
        """Functions passed as callback arguments should be detected as entry points."""
        code = '''
from fastapi import FastAPI
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app):
    yield

app = FastAPI(lifespan=lifespan)

def on_startup():
    print("Starting")

app.add_event_handler("startup", on_startup)
'''
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)
            test_file = repo_path / "main.py"
            test_file.write_text(code)

            analyzer = CallGraphAnalyzer()
            call_graph = analyzer.analyze(repo_path)

            lifespan_node = call_graph.nodes.get("main.py:lifespan")
            on_startup_node = call_graph.nodes.get("main.py:on_startup")

            assert lifespan_node is not None, "lifespan function not found"
            assert on_startup_node is not None, "on_startup function not found"
            # lifespan is passed as keyword arg, on_startup matches callback pattern
            assert lifespan_node.is_entry_point, "lifespan should be entry point (passed as callback)"
            assert on_startup_node.is_entry_point, "on_startup should be entry point (callback pattern)"

    @pytest.mark.skipif(not TREE_SITTER_AVAILABLE, reason="tree-sitter not installed")
    def test_test_file_functions_are_entry_points(self):
        """All functions in test files should be entry points."""
        code = '''
def helper_function():
    return 42

def another_helper():
    return "test"

class TestSomething:
    def test_case(self):
        pass

    def helper_method(self):
        pass
'''
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)
            # File named test_*.py - all functions should be entry points
            test_file = repo_path / "test_example.py"
            test_file.write_text(code)

            analyzer = CallGraphAnalyzer()
            call_graph = analyzer.analyze(repo_path)

            helper_node = call_graph.nodes.get("test_example.py:helper_function")
            another_node = call_graph.nodes.get("test_example.py:another_helper")

            assert helper_node is not None
            assert another_node is not None
            # All functions in test_*.py are entry points
            assert helper_node.is_entry_point, "Functions in test files should be entry points"
            assert another_node.is_entry_point, "Functions in test files should be entry points"

    @pytest.mark.skipif(not TREE_SITTER_AVAILABLE, reason="tree-sitter not installed")
    def test_hypothesis_strategy_is_entry_point(self):
        """Hypothesis strategy functions should be detected as entry points."""
        code = '''
from hypothesis import strategies as st

def my_strategy():
    return st.integers()

def custom_strategy():
    return st.text()

def analysis_status_strategy():
    return st.sampled_from(["pending", "running", "completed"])
'''
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)
            test_file = repo_path / "strategies.py"
            test_file.write_text(code)

            analyzer = CallGraphAnalyzer()
            call_graph = analyzer.analyze(repo_path)

            # Functions ending in _strategy should be entry points
            status_node = call_graph.nodes.get("strategies.py:analysis_status_strategy")
            assert status_node is not None
            assert status_node.is_entry_point, "*_strategy functions should be entry points"

    @pytest.mark.skipif(not TREE_SITTER_AVAILABLE, reason="tree-sitter not installed")
    def test_dunder_methods_are_entry_points(self):
        """Python dunder methods should be detected as entry points."""
        code = '''
class MyClass:
    def __init__(self):
        pass

    def __str__(self):
        return "MyClass"

    def __repr__(self):
        return "MyClass()"

    def __eq__(self, other):
        return True

    def regular_method(self):
        pass
'''
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)
            test_file = repo_path / "myclass.py"
            test_file.write_text(code)

            analyzer = CallGraphAnalyzer()
            call_graph = analyzer.analyze(repo_path)

            init_node = call_graph.nodes.get("myclass.py:__init__")
            str_node = call_graph.nodes.get("myclass.py:__str__")
            repr_node = call_graph.nodes.get("myclass.py:__repr__")
            eq_node = call_graph.nodes.get("myclass.py:__eq__")

            assert init_node is not None
            assert str_node is not None
            assert repr_node is not None
            assert eq_node is not None

            assert init_node.is_entry_point, "__init__ should be entry point"
            assert str_node.is_entry_point, "__str__ should be entry point"
            assert repr_node.is_entry_point, "__repr__ should be entry point"
            assert eq_node.is_entry_point, "__eq__ should be entry point"

    @pytest.mark.skipif(not TREE_SITTER_AVAILABLE, reason="tree-sitter not installed")
    def test_property_decorator_is_entry_point(self):
        """Property decorators should mark functions as entry points."""
        code = '''
class Config:
    def __init__(self):
        self._value = 42

    @property
    def value(self):
        return self._value

    @staticmethod
    def create():
        return Config()

    @classmethod
    def from_dict(cls, data):
        return cls()
'''
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)
            test_file = repo_path / "config.py"
            test_file.write_text(code)

            analyzer = CallGraphAnalyzer()
            call_graph = analyzer.analyze(repo_path)

            value_node = call_graph.nodes.get("config.py:value")
            create_node = call_graph.nodes.get("config.py:create")
            from_dict_node = call_graph.nodes.get("config.py:from_dict")

            assert value_node is not None
            assert create_node is not None
            assert from_dict_node is not None

            assert value_node.is_entry_point, "@property should be entry point"
            assert create_node.is_entry_point, "@staticmethod should be entry point"
            assert from_dict_node.is_entry_point, "@classmethod should be entry point"

    @pytest.mark.skipif(not TREE_SITTER_AVAILABLE, reason="tree-sitter not installed")
    def test_unreachable_detection_with_framework_patterns(self):
        """Verify that framework-registered functions are NOT marked as dead code."""
        code = '''
from fastapi import FastAPI

app = FastAPI()

@app.get("/")
def root():
    return helper()

def helper():
    return {"message": "Hello"}

def truly_dead_code():
    """This function is never called."""
    return "dead"
'''
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)
            test_file = repo_path / "main.py"
            test_file.write_text(code)

            analyzer = CallGraphAnalyzer()
            call_graph = analyzer.analyze(repo_path)
            findings = analyzer.to_dead_code_findings(call_graph)

            # root is entry point (FastAPI route)
            # helper is called by root
            # truly_dead_code is never called
            dead_names = [f.function_name for f in findings]

            assert "root" not in dead_names, "FastAPI route should not be dead code"
            assert "helper" not in dead_names, "helper is called by root"
            assert "truly_dead_code" in dead_names, "truly_dead_code should be detected as dead"


# =============================================================================
# Tests for Function Name Sanitization
# =============================================================================


class TestSanitizeFunctionName:
    """Tests for the sanitize_function_name helper function."""

    def test_sanitize_clean_names(self):
        """Clean function names should be returned as-is."""
        from app.services.call_graph_analyzer import sanitize_function_name

        assert sanitize_function_name("_hotspots") == "_hotspots"
        assert sanitize_function_name("render") == "render"
        assert sanitize_function_name("__init__") == "__init__"
        assert sanitize_function_name("handleClick") == "handleClick"
        assert sanitize_function_name("_private_method") == "_private_method"

    def test_sanitize_malformed_names(self):
        """Malformed function names should be cleaned."""
        from app.services.call_graph_analyzer import sanitize_function_name

        # Names with parentheses and parameters
        assert sanitize_function_name("_hotspots(\n        self") == "_hotspots"
        assert sanitize_function_name("_content_section(\n        self") == "_content_section"
        assert sanitize_function_name("render(") == "render"
        assert sanitize_function_name("handleClick(event)") == "handleClick"

        # Names with trailing newlines
        assert sanitize_function_name("handleClick\n") == "handleClick"
        assert sanitize_function_name("render\n  ") == "render"

        # Names with spaces
        assert sanitize_function_name("render props") == "render"

    def test_sanitize_empty_and_whitespace(self):
        """Empty and whitespace-only names should be handled."""
        from app.services.call_graph_analyzer import sanitize_function_name

        assert sanitize_function_name("") == ""
        assert sanitize_function_name("   ") == ""
        assert sanitize_function_name(None) is None  # type: ignore


# =============================================================================
# Tests for Entry Point Helper Functions
# =============================================================================


class TestEntryPointHelperFunctions:
    """Tests for the entry point detection helper functions."""

    def test_is_entry_point_file_test_files(self):
        """Test file patterns should be detected."""
        from app.services.call_graph_analyzer import is_entry_point_file

        assert is_entry_point_file("test_example.py") is True
        assert is_entry_point_file("example_test.py") is True
        assert is_entry_point_file("tests/test_api.py") is True
        assert is_entry_point_file("conftest.py") is True
        assert is_entry_point_file("src/conftest.py") is True

    def test_is_entry_point_file_js_ts_test_files(self):
        """JavaScript/TypeScript test file patterns should be detected."""
        from app.services.call_graph_analyzer import is_entry_point_file

        # .test.ts/.test.tsx patterns
        assert is_entry_point_file("Button.test.ts") is True
        assert is_entry_point_file("Button.test.tsx") is True
        assert is_entry_point_file("src/components/Button.test.tsx") is True
        assert is_entry_point_file("frontend/__tests__/hooks/use-analysis-status.test.ts") is True

        # .spec.ts/.spec.tsx patterns
        assert is_entry_point_file("Button.spec.ts") is True
        assert is_entry_point_file("Button.spec.tsx") is True
        assert is_entry_point_file("src/components/Button.spec.tsx") is True

        # .test.js/.test.jsx patterns
        assert is_entry_point_file("Button.test.js") is True
        assert is_entry_point_file("Button.test.jsx") is True

        # __tests__ directory patterns
        assert is_entry_point_file("__tests__/Button.tsx") is True
        assert is_entry_point_file("frontend/__tests__/components/ai-insights-panel.test.tsx") is True
        assert is_entry_point_file("__tests__/hooks/useAuth.ts") is True

        # Cypress and E2E patterns
        assert is_entry_point_file("cypress/e2e/login.cy.ts") is True
        assert is_entry_point_file("e2e/auth.spec.ts") is True

        # Config files
        assert is_entry_point_file("jest.config.ts") is True
        assert is_entry_point_file("vitest.config.ts") is True

        # Regular files should NOT match
        assert is_entry_point_file("src/components/Button.tsx") is False
        assert is_entry_point_file("lib/utils.ts") is False

    def test_is_entry_point_file_migrations(self):
        """Migration files should be detected."""
        from app.services.call_graph_analyzer import is_entry_point_file

        assert is_entry_point_file("alembic/versions/001_init.py") is True
        assert is_entry_point_file("migrations/0001_initial.py") is True

    def test_is_entry_point_file_regular_files(self):
        """Regular files should not be entry point files."""
        from app.services.call_graph_analyzer import is_entry_point_file

        assert is_entry_point_file("main.py") is False
        assert is_entry_point_file("app/services/analyzer.py") is False
        assert is_entry_point_file("utils.py") is False

    def test_is_decorator_entry_point_fastapi(self):
        """FastAPI decorators should be detected."""
        from app.services.call_graph_analyzer import is_decorator_entry_point

        assert is_decorator_entry_point("app.get") is True
        assert is_decorator_entry_point("app.post") is True
        assert is_decorator_entry_point("router.get") is True
        assert is_decorator_entry_point("router.delete") is True

    def test_is_decorator_entry_point_celery(self):
        """Celery decorators should be detected."""
        from app.services.call_graph_analyzer import is_decorator_entry_point

        assert is_decorator_entry_point("shared_task") is True
        assert is_decorator_entry_point("celery_app.task") is True
        assert is_decorator_entry_point("app.task") is True

    def test_is_decorator_entry_point_pytest(self):
        """Pytest decorators should be detected."""
        from app.services.call_graph_analyzer import is_decorator_entry_point

        assert is_decorator_entry_point("pytest.fixture") is True
        assert is_decorator_entry_point("fixture") is True
        assert is_decorator_entry_point("pytest.mark.parametrize") is True

    def test_is_decorator_entry_point_pydantic(self):
        """Pydantic decorators should be detected."""
        from app.services.call_graph_analyzer import is_decorator_entry_point

        assert is_decorator_entry_point("model_validator") is True
        assert is_decorator_entry_point("field_validator") is True
        assert is_decorator_entry_point("validator") is True

    def test_is_callback_by_name(self):
        """Callback name patterns should be detected."""
        from app.services.call_graph_analyzer import is_callback_by_name

        assert is_callback_by_name("on_startup") is True
        assert is_callback_by_name("on_shutdown") is True
        assert is_callback_by_name("handle_error") is True
        assert is_callback_by_name("request_callback") is True
        assert is_callback_by_name("event_listener") is True
        assert is_callback_by_name("session_factory") is True
        assert is_callback_by_name("analysis_status_strategy") is True

        # Non-callbacks
        assert is_callback_by_name("process_data") is False
        assert is_callback_by_name("calculate") is False


# =============================================================================
# Tests for __main__ Block and Scripts Directory Detection
# =============================================================================


class TestMainBlockAndScriptsDetection:
    """Tests for if __name__ == "__main__": block detection and scripts directory."""

    @pytest.mark.skipif(not TREE_SITTER_AVAILABLE, reason="tree-sitter not installed")
    def test_main_block_direct_call_is_entry_point(self):
        """Functions called directly from __main__ block should be entry points."""
        code = '''
def init_database():
    print("Initializing database")

def helper():
    print("Helper function")

if __name__ == "__main__":
    init_database()
'''
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)
            test_file = repo_path / "init_db.py"
            test_file.write_text(code)

            analyzer = CallGraphAnalyzer()
            call_graph = analyzer.analyze(repo_path)
            findings = analyzer.to_dead_code_findings(call_graph)

            dead_names = [f.function_name for f in findings]

            # init_database is called from __main__, should NOT be dead code
            assert "init_database" not in dead_names, "Function called from __main__ should not be dead code"
            # helper is never called, should be dead code
            assert "helper" in dead_names, "Uncalled helper should be dead code"

    @pytest.mark.skipif(not TREE_SITTER_AVAILABLE, reason="tree-sitter not installed")
    def test_main_block_asyncio_run_is_entry_point(self):
        """Functions called via asyncio.run() in __main__ block should be entry points."""
        code = '''
import asyncio

async def init_qdrant():
    print("Initializing Qdrant")

async def helper_async():
    print("Helper async function")

if __name__ == "__main__":
    asyncio.run(init_qdrant())
'''
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)
            test_file = repo_path / "init_qdrant.py"
            test_file.write_text(code)

            analyzer = CallGraphAnalyzer()
            call_graph = analyzer.analyze(repo_path)
            findings = analyzer.to_dead_code_findings(call_graph)

            dead_names = [f.function_name for f in findings]

            # init_qdrant is called via asyncio.run from __main__
            assert "init_qdrant" not in dead_names, "Function called via asyncio.run from __main__ should not be dead code"
            # helper_async is never called
            assert "helper_async" in dead_names, "Uncalled async helper should be dead code"

    @pytest.mark.skipif(not TREE_SITTER_AVAILABLE, reason="tree-sitter not installed")
    def test_main_block_with_main_function(self):
        """Standard pattern: main() called from __main__ block."""
        code = '''
def print_header(msg):
    print(f"=== {msg} ===")

def init_db():
    print_header("Database")
    print("Initializing DB")

def init_cache():
    print_header("Cache")
    print("Initializing cache")

def main():
    init_db()
    init_cache()

if __name__ == "__main__":
    main()
'''
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)
            test_file = repo_path / "init_all.py"
            test_file.write_text(code)

            analyzer = CallGraphAnalyzer()
            call_graph = analyzer.analyze(repo_path)
            findings = analyzer.to_dead_code_findings(call_graph)

            dead_names = [f.function_name for f in findings]

            # main is called from __main__ (and matches name pattern)
            assert "main" not in dead_names, "main() should not be dead code"
            # init_db and init_cache are called by main
            assert "init_db" not in dead_names, "init_db called by main should not be dead code"
            assert "init_cache" not in dead_names, "init_cache called by main should not be dead code"
            # print_header is called by init_db and init_cache
            assert "print_header" not in dead_names, "print_header called transitively should not be dead code"

    @pytest.mark.skipif(not TREE_SITTER_AVAILABLE, reason="tree-sitter not installed")
    def test_scripts_directory_functions_are_entry_points(self):
        """All functions in scripts/ directory should be entry points."""
        code = '''
def recreate_collection():
    print("Recreating collection")

def helper_function():
    print("Helper")
'''
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)
            scripts_dir = repo_path / "scripts"
            scripts_dir.mkdir()
            test_file = scripts_dir / "recreate_qdrant.py"
            test_file.write_text(code)

            analyzer = CallGraphAnalyzer()
            call_graph = analyzer.analyze(repo_path)

            recreate_node = call_graph.nodes.get("scripts/recreate_qdrant.py:recreate_collection")
            helper_node = call_graph.nodes.get("scripts/recreate_qdrant.py:helper_function")

            assert recreate_node is not None
            assert helper_node is not None
            # All functions in scripts/ are entry points
            assert recreate_node.is_entry_point, "Functions in scripts/ should be entry points"
            assert helper_node.is_entry_point, "Functions in scripts/ should be entry points"

    def test_is_entry_point_file_scripts_directory(self):
        """Scripts directory should be detected as entry point file pattern."""
        from app.services.call_graph_analyzer import is_entry_point_file

        assert is_entry_point_file("scripts/init_db.py") is True
        assert is_entry_point_file("scripts/recreate_qdrant_collection.py") is True
        assert is_entry_point_file("backend/scripts/init_all.py") is True

        # Non-scripts directories
        assert is_entry_point_file("app/services/analyzer.py") is False
        assert is_entry_point_file("lib/scripts.py") is False  # Not in scripts/ dir


# =============================================================================
# Tests for React/JS Patterns and Async Generators
# =============================================================================


class TestReactAndAsyncPatterns:
    """Tests for React callback patterns and async generator detection."""

    def test_react_callback_patterns_detected(self):
        """React callback naming patterns should be detected."""
        from app.services.call_graph_analyzer import is_callback_by_name

        # React event handlers
        assert is_callback_by_name("handleMount") is True
        assert is_callback_by_name("handleClick") is True
        assert is_callback_by_name("handleSubmit") is True
        assert is_callback_by_name("onClick") is True
        assert is_callback_by_name("onChange") is True

        # Toggle/format helpers
        assert is_callback_by_name("toggleExpand") is True
        assert is_callback_by_name("toggleOpen") is True
        assert is_callback_by_name("formatTime") is True
        assert is_callback_by_name("formatDate") is True

        # Color helpers
        assert is_callback_by_name("getFileColor") is True
        assert is_callback_by_name("getStatusColor") is True

        # Render functions
        assert is_callback_by_name("renderItem") is True
        assert is_callback_by_name("renderRow") is True

        # Custom hooks
        assert is_callback_by_name("useCustomHook") is True

    def test_async_generator_patterns_detected(self):
        """Async generator/stream patterns should be detected."""
        from app.services.call_graph_analyzer import is_async_generator_name

        assert is_async_generator_name("subscribe_analysis_events") is True
        assert is_async_generator_name("subscribe_updates") is True
        assert is_async_generator_name("stream_results") is True
        assert is_async_generator_name("stream_data") is True
        assert is_async_generator_name("event_stream") is True
        assert is_async_generator_name("data_generator") is True

        # Non-async patterns
        assert is_async_generator_name("process_data") is False
        assert is_async_generator_name("get_results") is False

    @pytest.mark.skipif(not TREE_SITTER_AVAILABLE, reason="tree-sitter not installed")
    def test_async_generator_function_is_entry_point(self):
        """Async generator functions should be detected as entry points."""
        code = '''
async def subscribe_analysis_events(analysis_id: str):
    """SSE subscription for analysis events."""
    yield {"status": "started"}

async def stream_results(query: str):
    """Stream search results."""
    yield {"result": "data"}

def regular_function():
    pass
'''
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)
            test_file = repo_path / "sse.py"
            test_file.write_text(code)

            analyzer = CallGraphAnalyzer()
            call_graph = analyzer.analyze(repo_path)

            subscribe_node = call_graph.nodes.get("sse.py:subscribe_analysis_events")
            stream_node = call_graph.nodes.get("sse.py:stream_results")
            regular_node = call_graph.nodes.get("sse.py:regular_function")

            assert subscribe_node is not None
            assert stream_node is not None
            assert regular_node is not None

            assert subscribe_node.is_entry_point, "subscribe_* should be entry point"
            assert stream_node.is_entry_point, "stream_* should be entry point"
            assert not regular_node.is_entry_point, "regular_function should not be entry point"

    @pytest.mark.skipif(not TREE_SITTER_AVAILABLE, reason="tree-sitter not installed")
    def test_module_level_calls_mark_entry_points(self):
        """Functions called at module level should be marked as entry points."""
        code = '''
def create_runner():
    return "runner"

def helper():
    return "helper"

# Module-level call - create_runner is called outside any function
runner = create_runner()

def main():
    pass
'''
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)
            test_file = repo_path / "module.py"
            test_file.write_text(code)

            analyzer = CallGraphAnalyzer()
            call_graph = analyzer.analyze(repo_path)
            findings = analyzer.to_dead_code_findings(call_graph)

            dead_names = [f.function_name for f in findings]

            # create_runner is called at module level, should NOT be dead code
            assert "create_runner" not in dead_names, "Module-level called function should not be dead code"
            # helper is never called, should be dead code
            assert "helper" in dead_names, "Uncalled helper should be dead code"
            # main matches entry point pattern
            assert "main" not in dead_names, "main should not be dead code"


class TestHelperFunctionPatterns:
    """Tests for helper function patterns commonly used in React/frontend."""

    def test_is_callback_by_name_comprehensive(self):
        """Comprehensive test for callback name patterns."""
        from app.services.call_graph_analyzer import is_callback_by_name

        # Should match
        callbacks = [
            "on_startup", "on_shutdown", "on_event",  # Python style
            "onClick", "onChange", "onSubmit",  # React style
            "handleMount", "handleClick", "handleError",  # React handlers
            "handle_error", "handle_request",  # Python handlers
            "request_callback", "event_callback",  # *_callback
            "pre_hook", "post_hook",  # *_hook
            "event_listener", "change_listener",  # *_listener
            "session_factory", "connection_factory",  # *_factory
            "analysis_status_strategy", "data_strategy",  # *_strategy
            "toggleExpand", "toggleOpen", "toggleVisible",  # toggle*
            "formatTime", "formatDate", "formatCurrency",  # format*
            "getFileColor", "getStatusColor",  # get*Color
            "renderItem", "renderRow", "renderCell",  # render*
            "useCustomHook", "useAnalysis",  # use* (React hooks)
        ]

        for name in callbacks:
            assert is_callback_by_name(name) is True, f"{name} should be detected as callback"

        # Should NOT match
        non_callbacks = [
            "process_data",
            "calculate_total",
            "fetch_results",
            "save_file",
            "load_config",
            "validate_input",
        ]

        for name in non_callbacks:
            assert is_callback_by_name(name) is False, f"{name} should NOT be detected as callback"


# =============================================================================
# Tests for Class Method Tracking (self.method())
# =============================================================================


class TestClassMethodTracking:
    """Tests for Python class method call tracking via self.method()."""

    @pytest.mark.skipif(not TREE_SITTER_AVAILABLE, reason="tree-sitter not installed")
    def test_self_method_calls_are_tracked(self):
        """Methods called via self.method() should be tracked and not flagged as dead."""
        code = '''
class RepoViewGenerator:
    def __init__(self):
        self._ensure_image()

    def _ensure_image(self):
        print("Ensuring image")

    def _estimate_tokens(self, text):
        return len(text) // 4

    def _should_exclude_dir(self, path):
        return path.startswith(".")

    def _build_file_tree(self, root_path):
        if self._should_exclude_dir(root_path):
            return None
        tokens = self._estimate_tokens("test")
        return {"path": root_path, "tokens": tokens}

    def generate(self):
        return self._build_file_tree("/repo")
'''
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)
            test_file = repo_path / "generator.py"
            test_file.write_text(code)

            analyzer = CallGraphAnalyzer()
            call_graph = analyzer.analyze(repo_path)
            findings = analyzer.to_dead_code_findings(call_graph)

            dead_names = [f.function_name for f in findings]

            # All methods are called via self., none should be dead
            assert "_ensure_image" not in dead_names, "_ensure_image called in __init__"
            assert "_estimate_tokens" not in dead_names, "_estimate_tokens called in _build_file_tree"
            assert "_should_exclude_dir" not in dead_names, "_should_exclude_dir called in _build_file_tree"
            assert "_build_file_tree" not in dead_names, "_build_file_tree called in generate"
            assert "generate" not in dead_names, "generate is a public method (entry point)"
            assert "__init__" not in dead_names, "__init__ is a dunder method (entry point)"

    @pytest.mark.skipif(not TREE_SITTER_AVAILABLE, reason="tree-sitter not installed")
    def test_nested_function_in_method_is_tracked(self):
        """Nested functions inside methods should be tracked."""
        code = '''
class FileProcessor:
    def process(self, root_path):
        def walk_dir(path):
            """Nested function."""
            return [f for f in path.iterdir()]

        return walk_dir(root_path)
'''
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)
            test_file = repo_path / "processor.py"
            test_file.write_text(code)

            analyzer = CallGraphAnalyzer()
            call_graph = analyzer.analyze(repo_path)
            findings = analyzer.to_dead_code_findings(call_graph)

            dead_names = [f.function_name for f in findings]

            # walk_dir is called within process, should not be dead
            assert "walk_dir" not in dead_names, "walk_dir is called within process"

    @pytest.mark.skipif(not TREE_SITTER_AVAILABLE, reason="tree-sitter not installed")
    def test_class_with_truly_dead_private_method(self):
        """Truly dead private methods should still be detected."""
        code = '''
class MyClass:
    def __init__(self):
        self._used_helper()

    def _used_helper(self):
        pass

    def _dead_helper(self):
        """This private method is never called."""
        pass

    def public_method(self):
        """Public methods are entry points, not dead code."""
        pass
'''
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)
            test_file = repo_path / "myclass.py"
            test_file.write_text(code)

            analyzer = CallGraphAnalyzer()
            call_graph = analyzer.analyze(repo_path)
            findings = analyzer.to_dead_code_findings(call_graph)

            dead_names = [f.function_name for f in findings]

            # _used_helper is called via self., should not be dead
            assert "_used_helper" not in dead_names, "_used_helper is called via self."
            # _dead_helper is never called, should be dead
            assert "_dead_helper" in dead_names, "_dead_helper is never called"
            # public_method is a public method (entry point), should not be dead
            assert "public_method" not in dead_names, "public methods are entry points"


# =============================================================================
# Tests for FastAPI Depends() Detection
# =============================================================================


class TestFastAPIDependsDetection:
    """Tests for FastAPI Depends() dependency injection detection.

    Functions passed to Depends() are called by FastAPI at runtime,
    so they should be detected as entry points.
    """

    @pytest.mark.skipif(not TREE_SITTER_AVAILABLE, reason="tree-sitter not installed")
    def test_depends_in_function_signature_is_entry_point(self):
        """Functions used in Depends() should be detected as entry points."""
        code = '''
from typing import Annotated
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

async def get_db():
    """Database session dependency."""
    yield "session"

async def get_redis():
    """Redis connection dependency."""
    return "redis"

async def get_current_user(
    db: Annotated[AsyncSession, Depends(get_db)],
    redis: Annotated[object, Depends(get_redis)],
):
    """Get current user - uses get_db and get_redis as dependencies."""
    return {"user": "test"}

# Type alias with Depends
DbSession = Annotated[AsyncSession, Depends(get_db)]
RedisSession = Annotated[object, Depends(get_redis)]
'''
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)
            test_file = repo_path / "deps.py"
            test_file.write_text(code)

            analyzer = CallGraphAnalyzer()
            call_graph = analyzer.analyze(repo_path)
            findings = analyzer.to_dead_code_findings(call_graph)

            dead_names = [f.function_name for f in findings]

            # get_db is used in Depends(), should NOT be dead
            assert "get_db" not in dead_names, "get_db is used in Depends() - should be entry point"
            # get_redis is also used in Depends()
            assert "get_redis" not in dead_names, "get_redis is used in Depends() - should be entry point"

    @pytest.mark.skipif(not TREE_SITTER_AVAILABLE, reason="tree-sitter not installed")
    def test_depends_with_class_dependency(self):
        """Class-based dependencies with Depends() should work."""
        code = '''
from fastapi import Depends

class DatabaseSession:
    def __call__(self):
        return "session"

def get_settings():
    return {"debug": True}

async def endpoint(
    db = Depends(DatabaseSession()),
    settings = Depends(get_settings),
):
    return {"db": db, "settings": settings}
'''
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)
            test_file = repo_path / "api.py"
            test_file.write_text(code)

            analyzer = CallGraphAnalyzer()
            call_graph = analyzer.analyze(repo_path)
            findings = analyzer.to_dead_code_findings(call_graph)

            dead_names = [f.function_name for f in findings]

            # get_settings is used in Depends(), should NOT be dead
            assert "get_settings" not in dead_names, "get_settings is used in Depends()"


# =============================================================================
# Tests for Class Attribute Function Calls
# =============================================================================


class TestClassAttributeFunctionCalls:
    """Tests for function calls in class attribute assignments.

    Functions called in class body (outside methods) should be tracked.
    e.g., model_config = SettingsConfigDict(env_file=_find_env_file())
    """

    @pytest.mark.skipif(not TREE_SITTER_AVAILABLE, reason="tree-sitter not installed")
    def test_function_call_in_class_attribute(self):
        """Functions called in class attributes should be entry points."""
        code = '''
def _find_env_file():
    """Find the .env file path."""
    return ".env"

def _get_default_value():
    """Get default configuration value."""
    return 42

class Settings:
    env_file = _find_env_file()
    default_value = _get_default_value()

    def __init__(self):
        pass
'''
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)
            test_file = repo_path / "config.py"
            test_file.write_text(code)

            analyzer = CallGraphAnalyzer()
            call_graph = analyzer.analyze(repo_path)
            findings = analyzer.to_dead_code_findings(call_graph)

            dead_names = [f.function_name for f in findings]

            # _find_env_file is called in class attribute, should NOT be dead
            assert "_find_env_file" not in dead_names, "_find_env_file is called in class attribute"
            assert "_get_default_value" not in dead_names, "_get_default_value is called in class attribute"

    @pytest.mark.skipif(not TREE_SITTER_AVAILABLE, reason="tree-sitter not installed")
    def test_pydantic_settings_config_dict(self):
        """Pydantic SettingsConfigDict with function calls should work."""
        code = '''
from pathlib import Path

def _find_env_file() -> str:
    """Find .env file in project root."""
    return str(Path(__file__).parent.parent / ".env")

class Settings:
    model_config = {"env_file": _find_env_file()}

    debug: bool = False
'''
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)
            test_file = repo_path / "settings.py"
            test_file.write_text(code)

            analyzer = CallGraphAnalyzer()
            call_graph = analyzer.analyze(repo_path)
            findings = analyzer.to_dead_code_findings(call_graph)

            dead_names = [f.function_name for f in findings]

            assert "_find_env_file" not in dead_names, "_find_env_file is called in class body"


# =============================================================================
# Tests for Function Name Validation
# =============================================================================


class TestFunctionNameValidation:
    """Tests to ensure function names are properly extracted.

    Function names should be clean identifiers, not include:
    - Parameters: settings() -
    - Return types: func() -> str
    - Random fragments: self,
    """

    @pytest.mark.skipif(not TREE_SITTER_AVAILABLE, reason="tree-sitter not installed")
    def test_function_names_are_valid_identifiers(self):
        """All extracted function names should be valid Python identifiers."""
        code = '''
def simple_function():
    pass

def function_with_args(arg1, arg2):
    pass

def function_with_return() -> str:
    return "hello"

def function_with_defaults(x: int = 10, y: str = "test") -> dict:
    return {"x": x, "y": y}

async def async_function(self, data: dict) -> None:
    pass

class MyClass:
    def method(self, value: int) -> bool:
        return True

    @staticmethod
    def static_method(x: str, y: str) -> str:
        return x + y
'''
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)
            test_file = repo_path / "functions.py"
            test_file.write_text(code)

            analyzer = CallGraphAnalyzer()
            call_graph = analyzer.analyze(repo_path)

            # Check all function names are valid identifiers
            for node_id, node in call_graph.nodes.items():
                name = node.name
                # Valid Python identifier: starts with letter/underscore, contains only alphanumeric/underscore
                assert name.isidentifier(), f"Invalid function name: '{name}' in {node_id}"
                # Should not contain special characters
                assert "(" not in name, f"Function name contains '(': '{name}'"
                assert ")" not in name, f"Function name contains ')': '{name}'"
                assert ":" not in name, f"Function name contains ':': '{name}'"
                assert "->" not in name, f"Function name contains '->': '{name}'"
                assert "," not in name, f"Function name contains ',': '{name}'"
                assert " " not in name, f"Function name contains space: '{name}'"

    @pytest.mark.skipif(not TREE_SITTER_AVAILABLE, reason="tree-sitter not installed")
    def test_complex_function_signatures_parsed_correctly(self):
        """Complex function signatures should still yield clean names."""
        code = '''
from typing import Optional, List, Dict, Annotated
from dataclasses import dataclass

@dataclass
class Config:
    value: int

def process_data(
    items: List[Dict[str, int]],
    config: Optional[Config] = None,
    *args,
    **kwargs
) -> Dict[str, List[int]]:
    """Complex signature with generics."""
    return {}

async def fetch_with_retry(
    url: str,
    retries: int = 3,
    timeout: float = 30.0,
) -> Optional[bytes]:
    """Async function with multiple typed params."""
    return None
'''
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)
            test_file = repo_path / "complex.py"
            test_file.write_text(code)

            analyzer = CallGraphAnalyzer()
            call_graph = analyzer.analyze(repo_path)

            # Verify specific function names
            assert "complex.py:process_data" in call_graph.nodes
            assert "complex.py:fetch_with_retry" in call_graph.nodes

            # Verify names are clean
            for node in call_graph.nodes.values():
                assert node.name.isidentifier(), f"Invalid name: '{node.name}'"


# =============================================================================
# Property Tests for Multi-File Same-Name Function Resolution
# =============================================================================


class TestMultiFileSameNameResolution:
    """Property tests for multi-file same-name function resolution.

    **Feature: call-graph-refactoring, Property 1 & 2**
    **Validates: Requirements 1.1, 1.2, 1.3, 1.4**

    These tests verify that when multiple files define functions with the same name,
    the call graph analyzer correctly links calls to ALL candidates while prioritizing
    same-file matches.
    """

    @pytest.mark.skipif(not TREE_SITTER_AVAILABLE, reason="tree-sitter not installed")
    @given(st.integers(min_value=2, max_value=5))
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_same_file_priority_inclusion(self, num_files: int):
        """
        **Feature: call-graph-refactoring, Property 2: Same-File Priority Inclusion**
        **Validates: Requirements 1.2**

        Property: For any function call where a matching function exists in the same file,
        the same-file function SHALL always be included in the linked candidates
        (regardless of whether cross-file matches also exist).
        """
        # Create multiple files with a function named "helper"
        # One file will call helper() and should link to its own helper first
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)

            # Create file1.py with helper() and caller() that calls helper()
            file1_code = '''
def helper():
    """Helper in file1."""
    return "file1"

def caller():
    """Calls helper - should link to same-file helper."""
    return helper()
'''
            (repo_path / "file1.py").write_text(file1_code)

            # Create additional files with their own helper() function
            for i in range(2, num_files + 1):
                file_code = f'''
def helper():
    """Helper in file{i}."""
    return "file{i}"
'''
                (repo_path / f"file{i}.py").write_text(file_code)

            # Analyze the repository
            analyzer = CallGraphAnalyzer()
            call_graph = analyzer.analyze(repo_path)

            # Verify caller exists
            caller_id = "file1.py:caller"
            assert caller_id in call_graph.nodes, "caller not found in call graph"

            caller_node = call_graph.nodes[caller_id]

            # Property: Same-file helper MUST be in caller's calls
            same_file_helper_id = "file1.py:helper"
            assert same_file_helper_id in caller_node.calls, (
                f"Same-file helper should be in caller's calls.\n"
                f"caller.calls = {caller_node.calls}\n"
                f"Expected: {same_file_helper_id}"
            )

            # Property: Same-file helper's called_by MUST include caller
            same_file_helper = call_graph.nodes.get(same_file_helper_id)
            assert same_file_helper is not None, "Same-file helper not found"
            assert caller_id in same_file_helper.called_by, (
                f"Caller should be in same-file helper's called_by.\n"
                f"helper.called_by = {same_file_helper.called_by}\n"
                f"Expected: {caller_id}"
            )

    @pytest.mark.skipif(not TREE_SITTER_AVAILABLE, reason="tree-sitter not installed")
    @given(st.integers(min_value=2, max_value=4))
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_multi_candidate_bidirectional_linking(self, num_files: int):
        """
        **Feature: call-graph-refactoring, Property 1: Multi-Candidate Bidirectional Linking**
        **Validates: Requirements 1.1, 1.3, 1.4**

        Property: For any function call that matches multiple functions with the same name
        across different files, linking the call SHALL result in:
        - The caller's `calls` set containing ALL candidate function IDs
        - Each candidate's `called_by` set containing the caller ID
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)

            # Create caller file that calls process() - no local process() defined
            caller_code = '''
def main():
    """Main entry point that calls process()."""
    return process()
'''
            (repo_path / "main.py").write_text(caller_code)

            # Create multiple files with process() function
            for i in range(1, num_files + 1):
                file_code = f'''
def process():
    """Process function in module{i}."""
    return "module{i}"
'''
                (repo_path / f"module{i}.py").write_text(file_code)

            # Analyze the repository
            analyzer = CallGraphAnalyzer()
            call_graph = analyzer.analyze(repo_path)

            # Verify main exists
            main_id = "main.py:main"
            assert main_id in call_graph.nodes, "main not found in call graph"

            main_node = call_graph.nodes[main_id]

            # Collect all process() function IDs
            process_ids = [
                node_id for node_id in call_graph.nodes
                if node_id.endswith(":process")
            ]

            # Property 1: ALL process functions should be in main's calls
            for process_id in process_ids:
                assert process_id in main_node.calls, (
                    f"All process() candidates should be in main's calls.\n"
                    f"Missing: {process_id}\n"
                    f"main.calls = {main_node.calls}"
                )

            # Property 2: main should be in each process function's called_by
            for process_id in process_ids:
                process_node = call_graph.nodes[process_id]
                assert main_id in process_node.called_by, (
                    f"main should be in {process_id}'s called_by.\n"
                    f"{process_id}.called_by = {process_node.called_by}"
                )

    @pytest.mark.skipif(not TREE_SITTER_AVAILABLE, reason="tree-sitter not installed")
    def test_same_file_match_with_cross_file_matches(self):
        """
        **Feature: call-graph-refactoring, Property 2: Same-File Priority Inclusion**
        **Validates: Requirements 1.2**

        Verify that same-file match is included even when cross-file matches exist.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)

            # File with both helper() and caller()
            file1_code = '''
def helper():
    return "local"

def caller():
    return helper()
'''
            (repo_path / "file1.py").write_text(file1_code)

            # Another file with helper()
            file2_code = '''
def helper():
    return "remote"
'''
            (repo_path / "file2.py").write_text(file2_code)

            analyzer = CallGraphAnalyzer()
            call_graph = analyzer.analyze(repo_path)

            caller_node = call_graph.nodes.get("file1.py:caller")
            assert caller_node is not None

            # Same-file helper MUST be included
            assert "file1.py:helper" in caller_node.calls, (
                "Same-file helper must be in calls even with cross-file matches"
            )

            # Cross-file helper should also be included (conservative linking)
            assert "file2.py:helper" in caller_node.calls, (
                "Cross-file helper should also be linked (conservative approach)"
            )

            # Bidirectional: both helpers should have caller in called_by
            file1_helper = call_graph.nodes.get("file1.py:helper")
            file2_helper = call_graph.nodes.get("file2.py:helper")

            assert "file1.py:caller" in file1_helper.called_by
            assert "file1.py:caller" in file2_helper.called_by

    @pytest.mark.skipif(not TREE_SITTER_AVAILABLE, reason="tree-sitter not installed")
    def test_no_false_positive_dead_code_with_same_name_functions(self):
        """
        **Feature: call-graph-refactoring, Property 1: Multi-Candidate Bidirectional Linking**
        **Validates: Requirements 1.1, 1.3, 1.4**

        Verify that functions with same name across files are not incorrectly
        flagged as dead code when one of them is called.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)

            # Entry point that calls validate()
            main_code = '''
def main():
    return validate()
'''
            (repo_path / "main.py").write_text(main_code)

            # Multiple files with validate() function
            for i in range(1, 4):
                file_code = f'''
def validate():
    return "validator{i}"
'''
                (repo_path / f"validator{i}.py").write_text(file_code)

            analyzer = CallGraphAnalyzer()
            call_graph = analyzer.analyze(repo_path)
            findings = analyzer.to_dead_code_findings(call_graph)

            dead_names = [f.function_name for f in findings]

            # None of the validate() functions should be flagged as dead
            # because main() calls validate() and links to ALL candidates
            assert "validate" not in dead_names, (
                "validate() should not be dead code - it's called by main().\n"
                f"Dead code findings: {dead_names}"
            )


# =============================================================================
# Property Tests for Config Round-Trip Consistency
# =============================================================================


@st.composite
def valid_regex_pattern(draw) -> str:
    """Generate valid regex patterns that can be compiled."""
    # Use simple patterns that are always valid
    prefix = draw(st.sampled_from(["^", ""]))
    suffix = draw(st.sampled_from(["$", ""]))
    # Generate a simple word pattern
    word = draw(st.from_regex(r"[a-zA-Z_][a-zA-Z0-9_]*", fullmatch=True).filter(
        lambda s: len(s) >= 1 and len(s) <= 20
    ))
    return f"{prefix}{word}{suffix}"


@st.composite
def analyzer_config_strategy(draw):
    """Generate valid AnalyzerConfig objects for property testing.

    Generates configs with:
    - 0-5 patterns per pattern list
    - 0-5 exclude directories
    - All patterns are valid regex strings
    """
    from app.services.call_graph_analyzer import AnalyzerConfig

    # Generate pattern lists (0-5 patterns each)
    entry_point_names = draw(st.lists(valid_regex_pattern(), min_size=0, max_size=5))
    entry_point_decorators = draw(st.lists(valid_regex_pattern(), min_size=0, max_size=5))
    entry_point_files = draw(st.lists(valid_regex_pattern(), min_size=0, max_size=5))
    callback_names = draw(st.lists(valid_regex_pattern(), min_size=0, max_size=5))
    async_generator_patterns = draw(st.lists(valid_regex_pattern(), min_size=0, max_size=5))
    api_file_patterns = draw(st.lists(valid_regex_pattern(), min_size=0, max_size=5))
    worker_file_patterns = draw(st.lists(valid_regex_pattern(), min_size=0, max_size=5))

    # Generate exclude directories (simple directory names)
    exclude_dirs = draw(st.sets(
        st.from_regex(r"[a-zA-Z_][a-zA-Z0-9_]*", fullmatch=True).filter(
            lambda s: len(s) >= 1 and len(s) <= 20
        ),
        min_size=0,
        max_size=5
    ))

    config = AnalyzerConfig(
        entry_point_name_patterns=entry_point_names,
        entry_point_decorator_patterns=entry_point_decorators,
        entry_point_file_patterns=entry_point_files,
        callback_name_patterns=callback_names,
        async_generator_patterns=async_generator_patterns,
        api_file_patterns=api_file_patterns,
        worker_file_patterns=worker_file_patterns,
        exclude_dirs=exclude_dirs,
    )
    config.compile_patterns()
    return config


class TestConfigRoundTripProperties:
    """Property tests for config serialization round-trip consistency.

    **Feature: call-graph-refactoring, Property 6: Config Round-Trip Consistency**
    **Validates: Requirements 5.7, 5.8**
    """

    @given(analyzer_config_strategy())
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_config_round_trip_consistency(self, config: AnalyzerConfig):
        """
        **Feature: call-graph-refactoring, Property 6: Config Round-Trip Consistency**
        **Validates: Requirements 5.7, 5.8**

        Property: For any valid AnalyzerConfig object, serializing to YAML and
        deserializing back SHALL produce an equivalent config (same patterns,
        same exclusions).
        """
        from app.services.call_graph_analyzer import AnalyzerConfig

        # Serialize to YAML
        yaml_str = config.to_yaml()

        # Deserialize back
        restored_config = AnalyzerConfig.from_yaml(yaml_str)

        # Property 1: Entry point name patterns are preserved
        assert config.entry_point_name_patterns == restored_config.entry_point_name_patterns, (
            f"Entry point name patterns not preserved.\n"
            f"Original: {config.entry_point_name_patterns}\n"
            f"Restored: {restored_config.entry_point_name_patterns}"
        )

        # Property 2: Entry point decorator patterns are preserved
        assert config.entry_point_decorator_patterns == restored_config.entry_point_decorator_patterns, (
            f"Entry point decorator patterns not preserved.\n"
            f"Original: {config.entry_point_decorator_patterns}\n"
            f"Restored: {restored_config.entry_point_decorator_patterns}"
        )

        # Property 3: Entry point file patterns are preserved
        assert config.entry_point_file_patterns == restored_config.entry_point_file_patterns, (
            f"Entry point file patterns not preserved.\n"
            f"Original: {config.entry_point_file_patterns}\n"
            f"Restored: {restored_config.entry_point_file_patterns}"
        )

        # Property 4: Callback name patterns are preserved
        assert config.callback_name_patterns == restored_config.callback_name_patterns, (
            f"Callback name patterns not preserved.\n"
            f"Original: {config.callback_name_patterns}\n"
            f"Restored: {restored_config.callback_name_patterns}"
        )

        # Property 5: Async generator patterns are preserved
        assert config.async_generator_patterns == restored_config.async_generator_patterns, (
            f"Async generator patterns not preserved.\n"
            f"Original: {config.async_generator_patterns}\n"
            f"Restored: {restored_config.async_generator_patterns}"
        )

        # Property 6: API file patterns are preserved
        assert config.api_file_patterns == restored_config.api_file_patterns, (
            f"API file patterns not preserved.\n"
            f"Original: {config.api_file_patterns}\n"
            f"Restored: {restored_config.api_file_patterns}"
        )

        # Property 7: Worker file patterns are preserved
        assert config.worker_file_patterns == restored_config.worker_file_patterns, (
            f"Worker file patterns not preserved.\n"
            f"Original: {config.worker_file_patterns}\n"
            f"Restored: {restored_config.worker_file_patterns}"
        )

        # Property 8: Exclude directories are preserved
        assert config.exclude_dirs == restored_config.exclude_dirs, (
            f"Exclude directories not preserved.\n"
            f"Original: {config.exclude_dirs}\n"
            f"Restored: {restored_config.exclude_dirs}"
        )

        # Property 9: Restored config is compiled
        assert restored_config._compiled, "Restored config should be compiled"

    @given(analyzer_config_strategy())
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_config_yaml_is_valid_yaml(self, config: AnalyzerConfig):
        """
        **Feature: call-graph-refactoring, Property 6: Config Round-Trip Consistency**
        **Validates: Requirements 5.7**

        Property: For any valid AnalyzerConfig, to_yaml() SHALL produce
        valid YAML that can be parsed without errors.
        """
        import yaml

        yaml_str = config.to_yaml()

        # Should not raise any exceptions
        parsed = yaml.safe_load(yaml_str)

        # Should be a dictionary
        assert isinstance(parsed, dict), f"YAML should parse to dict, got {type(parsed)}"

        # Should contain expected keys
        expected_keys = {
            "entry_point_names",
            "entry_point_decorators",
            "entry_point_files",
            "callback_names",
            "async_generator_patterns",
            "api_file_patterns",
            "worker_file_patterns",
            "exclude_dirs",
        }
        assert set(parsed.keys()) == expected_keys, (
            f"YAML keys mismatch.\n"
            f"Expected: {expected_keys}\n"
            f"Got: {set(parsed.keys())}"
        )

    def test_config_from_yaml_with_defaults(self):
        """
        **Feature: call-graph-refactoring, Property 6: Config Round-Trip Consistency**
        **Validates: Requirements 5.7, 5.8**

        Test that load_defaults() config can round-trip through YAML.
        """
        from app.services.call_graph_analyzer import AnalyzerConfig

        # Load defaults
        original = AnalyzerConfig.load_defaults()

        # Round-trip through YAML
        yaml_str = original.to_yaml()
        restored = AnalyzerConfig.from_yaml(yaml_str)

        # All patterns should match
        assert original.entry_point_name_patterns == restored.entry_point_name_patterns
        assert original.entry_point_decorator_patterns == restored.entry_point_decorator_patterns
        assert original.entry_point_file_patterns == restored.entry_point_file_patterns
        assert original.callback_name_patterns == restored.callback_name_patterns
        assert original.async_generator_patterns == restored.async_generator_patterns
        assert original.api_file_patterns == restored.api_file_patterns
        assert original.worker_file_patterns == restored.worker_file_patterns
        assert original.exclude_dirs == restored.exclude_dirs

    def test_config_from_yaml_invalid_format(self):
        """
        **Feature: call-graph-refactoring, Property 6: Config Round-Trip Consistency**
        **Validates: Requirements 5.8**

        Test that from_yaml() raises ValueError for invalid YAML format.
        """
        from app.services.call_graph_analyzer import AnalyzerConfig

        # YAML that parses to a list instead of dict
        invalid_yaml = "- item1\n- item2\n"

        with pytest.raises(ValueError, match="Invalid YAML format"):
            AnalyzerConfig.from_yaml(invalid_yaml)


# =============================================================================
# Property Tests for Directory Exclusion Completeness
# =============================================================================


@st.composite
def excluded_directory_name(draw) -> str:
    """Generate directory names that should be excluded by default config.

    Returns one of the default excluded directories from AnalyzerConfig.
    """
    from app.services.call_graph_analyzer import AnalyzerConfig

    config = AnalyzerConfig.load_defaults()
    return draw(st.sampled_from(sorted(config.exclude_dirs)))


@st.composite
def file_in_excluded_directory(draw) -> tuple[str, str]:
    """Generate a file path inside an excluded directory.

    Returns:
        Tuple of (excluded_dir_name, full_file_path)
    """
    excluded_dir = draw(excluded_directory_name())

    # Generate a valid Python filename
    filename = draw(st.from_regex(r"[a-zA-Z_][a-zA-Z0-9_]*\.py", fullmatch=True).filter(
        lambda s: len(s) >= 4 and len(s) <= 30
    ))

    # Optionally add subdirectory depth
    depth = draw(st.integers(min_value=0, max_value=2))
    subdirs = []
    for _ in range(depth):
        subdir = draw(st.from_regex(r"[a-zA-Z_][a-zA-Z0-9_]*", fullmatch=True).filter(
            lambda s: len(s) >= 1 and len(s) <= 15
        ))
        subdirs.append(subdir)

    # Build full path
    if subdirs:
        full_path = f"{excluded_dir}/{'/'.join(subdirs)}/{filename}"
    else:
        full_path = f"{excluded_dir}/{filename}"

    return excluded_dir, full_path


class TestDirectoryExclusionCompletenessProperties:
    """Property tests for directory exclusion completeness.

    **Feature: call-graph-refactoring, Property 5: Directory Exclusion Completeness**
    **Validates: Requirements 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7**
    """

    @given(excluded_directory_name())
    @settings(max_examples=100)
    def test_default_excluded_dirs_are_excluded(self, dir_name: str):
        """
        **Feature: call-graph-refactoring, Property 5: Directory Exclusion Completeness**
        **Validates: Requirements 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7**

        Property: For any directory in the default exclude_dirs set,
        should_exclude_dir() SHALL return True.
        """
        from app.services.call_graph_analyzer import AnalyzerConfig

        config = AnalyzerConfig.load_defaults()

        assert config.should_exclude_dir(dir_name), (
            f"Directory '{dir_name}' should be excluded but was not.\n"
            f"Default exclude_dirs: {sorted(config.exclude_dirs)}"
        )

    def test_all_required_directories_are_excluded(self):
        """
        **Feature: call-graph-refactoring, Property 5: Directory Exclusion Completeness**
        **Validates: Requirements 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7**

        Verify that all directories specified in requirements are excluded:
        - 4.1: node_modules (package managers)
        - 4.2: .venv, venv, env (Python virtual environments)
        - 4.3: __pycache__, .mypy_cache, .pytest_cache, .ruff_cache (Python caches)
        - 4.4: dist, build, _build, target (build outputs)
        - 4.5: .next, .nuxt, .output (framework-specific)
        - 4.6: .git, .hg, .svn (version control)
        - 4.7: coverage, htmlcov (test coverage)
        """
        from app.services.call_graph_analyzer import AnalyzerConfig

        config = AnalyzerConfig.load_defaults()

        # Requirement 4.1: Package manager directories
        assert config.should_exclude_dir("node_modules"), "node_modules should be excluded (Req 4.1)"

        # Requirement 4.2: Python virtual environment directories
        assert config.should_exclude_dir(".venv"), ".venv should be excluded (Req 4.2)"
        assert config.should_exclude_dir("venv"), "venv should be excluded (Req 4.2)"
        assert config.should_exclude_dir("env"), "env should be excluded (Req 4.2)"

        # Requirement 4.3: Python cache directories
        assert config.should_exclude_dir("__pycache__"), "__pycache__ should be excluded (Req 4.3)"
        assert config.should_exclude_dir(".mypy_cache"), ".mypy_cache should be excluded (Req 4.3)"
        assert config.should_exclude_dir(".pytest_cache"), ".pytest_cache should be excluded (Req 4.3)"
        assert config.should_exclude_dir(".ruff_cache"), ".ruff_cache should be excluded (Req 4.3)"

        # Requirement 4.4: Build output directories
        assert config.should_exclude_dir("dist"), "dist should be excluded (Req 4.4)"
        assert config.should_exclude_dir("build"), "build should be excluded (Req 4.4)"
        assert config.should_exclude_dir("_build"), "_build should be excluded (Req 4.4)"
        assert config.should_exclude_dir("target"), "target should be excluded (Req 4.4)"

        # Requirement 4.5: Framework-specific directories
        assert config.should_exclude_dir(".next"), ".next should be excluded (Req 4.5)"
        assert config.should_exclude_dir(".nuxt"), ".nuxt should be excluded (Req 4.5)"
        assert config.should_exclude_dir(".output"), ".output should be excluded (Req 4.5)"

        # Requirement 4.6: Version control directories
        assert config.should_exclude_dir(".git"), ".git should be excluded (Req 4.6)"
        assert config.should_exclude_dir(".hg"), ".hg should be excluded (Req 4.6)"
        assert config.should_exclude_dir(".svn"), ".svn should be excluded (Req 4.6)"

        # Requirement 4.7: Test coverage directories
        assert config.should_exclude_dir("coverage"), "coverage should be excluded (Req 4.7)"
        assert config.should_exclude_dir("htmlcov"), "htmlcov should be excluded (Req 4.7)"

    @given(st.from_regex(r"[a-zA-Z][a-zA-Z0-9_]*", fullmatch=True).filter(
        lambda s: len(s) >= 2 and len(s) <= 20 and s not in {
            "node_modules", ".venv", "venv", "env", ".env",
            "__pycache__", ".mypy_cache", ".pytest_cache", ".ruff_cache",
            "dist", "build", "_build", "target",
            ".next", ".nuxt", ".output",
            ".git", ".hg", ".svn",
            "coverage", "htmlcov", ".coverage",
            ".tox", "vendor", ".eggs"
        }
    ))
    @settings(max_examples=100)
    def test_non_excluded_dirs_are_not_excluded(self, dir_name: str):
        """
        **Feature: call-graph-refactoring, Property 5: Directory Exclusion Completeness**
        **Validates: Requirements 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7**

        Property: For any directory NOT in the default exclude_dirs set,
        should_exclude_dir() SHALL return False.
        """
        from app.services.call_graph_analyzer import AnalyzerConfig

        config = AnalyzerConfig.load_defaults()

        assert not config.should_exclude_dir(dir_name), (
            f"Directory '{dir_name}' should NOT be excluded but was.\n"
            f"Default exclude_dirs: {sorted(config.exclude_dirs)}"
        )

    @given(file_in_excluded_directory())
    @settings(max_examples=100)
    def test_should_exclude_dir_returns_true_for_excluded_dirs(self, dir_and_path: tuple[str, str]):
        """
        **Feature: call-graph-refactoring, Property 5: Directory Exclusion Completeness**
        **Validates: Requirements 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7**

        Property: For any directory in the exclude_dirs set, should_exclude_dir()
        SHALL return True, enabling the analyzer to filter out files in those directories.
        """
        from app.services.call_graph_analyzer import AnalyzerConfig

        excluded_dir, _file_path = dir_and_path

        config = AnalyzerConfig.load_defaults()

        # The config should correctly identify this directory as excluded
        assert config.should_exclude_dir(excluded_dir), (
            f"should_exclude_dir('{excluded_dir}') should return True.\n"
            f"This directory is in exclude_dirs: {excluded_dir in config.exclude_dirs}"
        )

    @pytest.mark.skipif(not TREE_SITTER_AVAILABLE, reason="tree-sitter not installed")
    def test_analyzer_excludes_common_directories(self):
        """
        **Feature: call-graph-refactoring, Property 5: Directory Exclusion Completeness**
        **Validates: Requirements 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7**

        Integration test: Verify that the analyzer excludes common directories
        that are in the hardcoded exclude_patterns (node_modules, .venv, etc.).

        Note: Full config integration (task 9.2) will expand this to all exclude_dirs.
        """
        # Create a temporary repo with files in excluded directories
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)

            # Create files in directories that ARE currently excluded by the analyzer
            # (these are in the hardcoded exclude_patterns in _find_source_files)
            excluded_dirs_in_analyzer = ["node_modules", ".venv", "venv", "__pycache__", ".git", "dist", "build", ".next"]

            for excluded_dir in excluded_dirs_in_analyzer:
                excluded_file = repo_path / excluded_dir / "module.py"
                excluded_file.parent.mkdir(parents=True, exist_ok=True)
                excluded_file.write_text('''
def excluded_function():
    """This function should not be analyzed."""
    return 42
''')

            # Also create a non-excluded file for comparison
            normal_file = repo_path / "normal_module.py"
            normal_file.write_text('''
def normal_function():
    """This function should be analyzed."""
    return 1
''')

            # Analyze the repository
            analyzer = CallGraphAnalyzer()
            call_graph = analyzer.analyze(repo_path)

            # The normal function SHOULD be in the call graph
            normal_node_id = "normal_module.py:normal_function"
            assert normal_node_id in call_graph.nodes, (
                f"Function in non-excluded directory should be analyzed.\n"
                f"Expected node: {normal_node_id}\n"
                f"Found nodes: {list(call_graph.nodes.keys())}"
            )

            # Functions in excluded directories should NOT be in the call graph
            for excluded_dir in excluded_dirs_in_analyzer:
                excluded_node_id = f"{excluded_dir}/module.py:excluded_function"
                assert excluded_node_id not in call_graph.nodes, (
                    f"Function in excluded directory '{excluded_dir}' should not be analyzed.\n"
                    f"Node ID: {excluded_node_id}\n"
                    f"Found nodes: {list(call_graph.nodes.keys())}"
                )

    def test_custom_exclude_dirs_via_config(self):
        """
        **Feature: call-graph-refactoring, Property 5: Directory Exclusion Completeness**
        **Validates: Requirements 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7**

        Test that custom exclude directories can be added via config merge.
        """
        from app.services.call_graph_analyzer import AnalyzerConfig

        # Start with defaults
        config = AnalyzerConfig.load_defaults()
        original_count = len(config.exclude_dirs)

        # Add custom directory
        config.exclude_dirs.add("my_custom_build")

        # Verify custom directory is now excluded
        assert config.should_exclude_dir("my_custom_build"), (
            "Custom directory should be excluded after adding to exclude_dirs"
        )

        # Verify original directories are still excluded
        assert config.should_exclude_dir("node_modules"), (
            "Original directories should still be excluded"
        )

        # Verify count increased
        assert len(config.exclude_dirs) == original_count + 1, (
            "Adding custom directory should increase exclude_dirs count"
        )


# =============================================================================
# Property Tests for Config Pattern Merge (Task 8.3)
# =============================================================================


@st.composite
def repo_config_yaml_content(draw) -> dict[str, list[str]]:
    """Generate valid repo config YAML content with custom patterns.

    Returns:
        Dictionary representing YAML content for .n9r/call_graph.yaml
    """
    # Generate custom entry point name patterns
    custom_names = draw(st.lists(
        st.from_regex(r"\^[a-z_]+\$", fullmatch=True).filter(lambda s: len(s) >= 3 and len(s) <= 20),
        min_size=0,
        max_size=3
    ))

    # Generate custom decorator patterns
    custom_decorators = draw(st.lists(
        st.from_regex(r"\^@?[a-z_]+\$", fullmatch=True).filter(lambda s: len(s) >= 3 and len(s) <= 20),
        min_size=0,
        max_size=3
    ))

    # Generate custom file patterns
    custom_files = draw(st.lists(
        st.from_regex(r"[a-z_]+/", fullmatch=True).filter(lambda s: len(s) >= 2 and len(s) <= 15),
        min_size=0,
        max_size=3
    ))

    # Generate custom exclude directories
    custom_exclude_dirs = draw(st.lists(
        st.from_regex(r"[a-z_]+", fullmatch=True).filter(
            lambda s: len(s) >= 2 and len(s) <= 15 and s not in {
                "node_modules", ".venv", "venv", "env", ".env",
                "__pycache__", ".mypy_cache", ".pytest_cache", ".ruff_cache",
                "dist", "build", "_build", "target",
                ".next", ".nuxt", ".output",
                ".git", ".hg", ".svn",
                "coverage", "htmlcov", ".coverage",
                ".tox", "vendor", ".eggs"
            }
        ),
        min_size=0,
        max_size=3
    ))

    return {
        "entry_point_names": custom_names,
        "entry_point_decorators": custom_decorators,
        "entry_point_files": custom_files,
        "exclude_dirs": custom_exclude_dirs,
    }


class TestConfigPatternMergeProperties:
    """Property tests for config pattern merge behavior.

    **Feature: call-graph-refactoring, Property 3: Config Pattern Merge is Additive**
    **Validates: Requirements 3.2, 3.3**
    """

    @given(repo_config_yaml_content())
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_config_merge_is_additive(self, custom_config: dict[str, list[str]]):
        """
        **Feature: call-graph-refactoring, Property 3: Config Pattern Merge is Additive**
        **Validates: Requirements 3.2, 3.3**

        Property: For any repository with a .n9r/call_graph.yaml config file,
        the resulting AnalyzerConfig SHALL contain all default patterns PLUS
        all patterns from the config file (superset relationship).
        """
        import yaml

        from app.services.call_graph_analyzer import AnalyzerConfig

        # Get default config patterns
        defaults = AnalyzerConfig.load_defaults()
        default_name_patterns = set(defaults.entry_point_name_patterns)
        default_decorator_patterns = set(defaults.entry_point_decorator_patterns)
        default_file_patterns = set(defaults.entry_point_file_patterns)
        default_exclude_dirs = set(defaults.exclude_dirs)

        # Create a temporary repo with custom config
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)
            config_dir = repo_path / ".n9r"
            config_dir.mkdir(parents=True)
            config_file = config_dir / "call_graph.yaml"

            # Write custom config
            config_file.write_text(yaml.dump(custom_config))

            # Load config for repo (should merge defaults + custom)
            merged_config = AnalyzerConfig.load_for_repo(repo_path)

            # Property 1: All default name patterns are preserved
            merged_name_patterns = set(merged_config.entry_point_name_patterns)
            assert default_name_patterns.issubset(merged_name_patterns), (
                f"Default name patterns should be preserved.\n"
                f"Missing: {default_name_patterns - merged_name_patterns}"
            )

            # Property 2: All custom name patterns are added
            custom_names = set(custom_config.get("entry_point_names", []))
            assert custom_names.issubset(merged_name_patterns), (
                f"Custom name patterns should be added.\n"
                f"Missing: {custom_names - merged_name_patterns}"
            )

            # Property 3: All default decorator patterns are preserved
            merged_decorator_patterns = set(merged_config.entry_point_decorator_patterns)
            assert default_decorator_patterns.issubset(merged_decorator_patterns), (
                f"Default decorator patterns should be preserved.\n"
                f"Missing: {default_decorator_patterns - merged_decorator_patterns}"
            )

            # Property 4: All custom decorator patterns are added
            custom_decorators = set(custom_config.get("entry_point_decorators", []))
            assert custom_decorators.issubset(merged_decorator_patterns), (
                f"Custom decorator patterns should be added.\n"
                f"Missing: {custom_decorators - merged_decorator_patterns}"
            )

            # Property 5: All default file patterns are preserved
            merged_file_patterns = set(merged_config.entry_point_file_patterns)
            assert default_file_patterns.issubset(merged_file_patterns), (
                f"Default file patterns should be preserved.\n"
                f"Missing: {default_file_patterns - merged_file_patterns}"
            )

            # Property 6: All custom file patterns are added
            custom_files = set(custom_config.get("entry_point_files", []))
            assert custom_files.issubset(merged_file_patterns), (
                f"Custom file patterns should be added.\n"
                f"Missing: {custom_files - merged_file_patterns}"
            )

            # Property 7: All default exclude dirs are preserved
            merged_exclude_dirs = set(merged_config.exclude_dirs)
            assert default_exclude_dirs.issubset(merged_exclude_dirs), (
                f"Default exclude dirs should be preserved.\n"
                f"Missing: {default_exclude_dirs - merged_exclude_dirs}"
            )

            # Property 8: All custom exclude dirs are added
            custom_exclude = set(custom_config.get("exclude_dirs", []))
            assert custom_exclude.issubset(merged_exclude_dirs), (
                f"Custom exclude dirs should be added.\n"
                f"Missing: {custom_exclude - merged_exclude_dirs}"
            )

            # Property 9: Merged config is compiled
            assert merged_config._compiled, "Merged config should be compiled"

    def test_config_merge_without_repo_config_returns_defaults(self):
        """
        **Feature: call-graph-refactoring, Property 3: Config Pattern Merge is Additive**
        **Validates: Requirements 3.2, 3.3**

        Test that load_for_repo() returns defaults when no config file exists.
        """
        from app.services.call_graph_analyzer import AnalyzerConfig

        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)

            # No .n9r/call_graph.yaml exists
            config = AnalyzerConfig.load_for_repo(repo_path)
            defaults = AnalyzerConfig.load_defaults()

            # Should be identical to defaults
            assert config.entry_point_name_patterns == defaults.entry_point_name_patterns
            assert config.entry_point_decorator_patterns == defaults.entry_point_decorator_patterns
            assert config.entry_point_file_patterns == defaults.entry_point_file_patterns
            assert config.exclude_dirs == defaults.exclude_dirs

    def test_config_merge_with_invalid_yaml_falls_back_to_defaults(self):
        """
        **Feature: call-graph-refactoring, Property 3: Config Pattern Merge is Additive**
        **Validates: Requirements 3.4**

        Test that invalid YAML in config file falls back to defaults gracefully.
        """
        from app.services.call_graph_analyzer import AnalyzerConfig

        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)
            config_dir = repo_path / ".n9r"
            config_dir.mkdir(parents=True)
            config_file = config_dir / "call_graph.yaml"

            # Write invalid YAML
            config_file.write_text("invalid: yaml: content: [")

            # Should not raise, should return defaults
            config = AnalyzerConfig.load_for_repo(repo_path)
            defaults = AnalyzerConfig.load_defaults()

            # Should be identical to defaults (fallback)
            assert config.entry_point_name_patterns == defaults.entry_point_name_patterns
            assert config.exclude_dirs == defaults.exclude_dirs


# =============================================================================
# Property Tests for Custom Entry Point Detection (Task 8.4)
# =============================================================================


@st.composite
def custom_decorator_pattern_and_function(draw) -> tuple[str, str, str]:
    """Generate a custom decorator pattern and a function that matches it.

    Returns:
        Tuple of (decorator_pattern, decorator_name, function_code)
    """
    # Generate a simple decorator name (e.g., "my_task", "custom_handler")
    base_name = draw(st.from_regex(r"[a-z]+_[a-z]+", fullmatch=True).filter(
        lambda s: len(s) >= 5 and len(s) <= 20
    ))

    # Create pattern that matches this decorator
    pattern = f"^{base_name}$"

    # Generate function name
    func_name = draw(st.from_regex(r"[a-z_]+", fullmatch=True).filter(
        lambda s: len(s) >= 3 and len(s) <= 15 and s not in {"def", "class", "return", "pass"}
    ))

    # Create function code with the decorator
    code = f'''
@{base_name}
def {func_name}():
    pass
'''

    return pattern, base_name, code, func_name


class TestCustomEntryPointDetectionProperties:
    """Property tests for custom entry point detection.

    **Feature: call-graph-refactoring, Property 4: Custom Entry Point Detection**
    **Validates: Requirements 3.5**
    """

    @given(st.from_regex(r"\^[a-z_]+\$", fullmatch=True).filter(lambda s: len(s) >= 4 and len(s) <= 15))
    @settings(max_examples=100)
    def test_custom_decorator_pattern_is_detected(self, pattern: str):
        """
        **Feature: call-graph-refactoring, Property 4: Custom Entry Point Detection**
        **Validates: Requirements 3.5**

        Property: For any decorator pattern defined in the repo config file,
        is_decorator_entry_point() SHALL return True for matching decorators.
        """
        from app.services.call_graph_analyzer import AnalyzerConfig

        # Create config with custom decorator pattern
        config = AnalyzerConfig.load_defaults()
        config.entry_point_decorator_patterns.append(pattern)
        config.compile_patterns()

        # Extract the decorator name from the pattern (remove ^ and $)
        decorator_name = pattern.strip("^$")

        # The config should detect this decorator as an entry point
        assert config.is_decorator_entry_point(decorator_name), (
            f"Decorator '{decorator_name}' should be detected as entry point.\n"
            f"Pattern: {pattern}\n"
            f"All decorator patterns: {config.entry_point_decorator_patterns}"
        )

    @given(st.from_regex(r"\^[a-z_]+\$", fullmatch=True).filter(lambda s: len(s) >= 4 and len(s) <= 15))
    @settings(max_examples=100)
    def test_custom_name_pattern_is_detected(self, pattern: str):
        """
        **Feature: call-graph-refactoring, Property 4: Custom Entry Point Detection**
        **Validates: Requirements 3.5**

        Property: For any function name pattern defined in the repo config file,
        is_entry_point_by_name() SHALL return True for matching function names.
        """
        from app.services.call_graph_analyzer import AnalyzerConfig

        # Create config with custom name pattern
        config = AnalyzerConfig.load_defaults()
        config.entry_point_name_patterns.append(pattern)
        config.compile_patterns()

        # Extract the function name from the pattern (remove ^ and $)
        func_name = pattern.strip("^$")

        # The config should detect this function name as an entry point
        assert config.is_entry_point_by_name(func_name), (
            f"Function name '{func_name}' should be detected as entry point.\n"
            f"Pattern: {pattern}\n"
            f"All name patterns: {config.entry_point_name_patterns}"
        )

    @given(st.from_regex(r"[a-z_]+/", fullmatch=True).filter(lambda s: len(s) >= 3 and len(s) <= 15))
    @settings(max_examples=100)
    def test_custom_file_pattern_is_detected(self, pattern: str):
        """
        **Feature: call-graph-refactoring, Property 4: Custom Entry Point Detection**
        **Validates: Requirements 3.5**

        Property: For any file pattern defined in the repo config file,
        is_entry_point_file() SHALL return True for matching file paths.
        """
        from app.services.call_graph_analyzer import AnalyzerConfig

        # Create config with custom file pattern
        config = AnalyzerConfig.load_defaults()
        config.entry_point_file_patterns.append(pattern)
        config.compile_patterns()

        # Create a file path that matches the pattern
        file_path = f"{pattern}module.py"

        # The config should detect this file as an entry point file
        assert config.is_entry_point_file(file_path), (
            f"File path '{file_path}' should be detected as entry point file.\n"
            f"Pattern: {pattern}\n"
            f"All file patterns: {config.entry_point_file_patterns}"
        )

    @pytest.mark.skipif(not TREE_SITTER_AVAILABLE, reason="tree-sitter not installed")
    def test_custom_decorator_in_repo_config_marks_function_as_entry_point(self):
        """
        **Feature: call-graph-refactoring, Property 4: Custom Entry Point Detection**
        **Validates: Requirements 3.5**

        Integration test: Verify that a function decorated with a custom decorator
        defined in .n9r/call_graph.yaml is marked as an entry point.

        Note: This test verifies the config loading mechanism. Full integration
        with CallGraphAnalyzer (task 9.3) will enable automatic detection.
        """
        import yaml

        from app.services.call_graph_analyzer import AnalyzerConfig

        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)

            # Create .n9r/call_graph.yaml with custom decorator pattern
            config_dir = repo_path / ".n9r"
            config_dir.mkdir(parents=True)
            config_file = config_dir / "call_graph.yaml"
            config_file.write_text(yaml.dump({
                "entry_point_decorators": ["^my_custom_task$"],
                "entry_point_names": ["^job_"],
            }))

            # Load config for repo
            config = AnalyzerConfig.load_for_repo(repo_path)

            # Verify custom decorator pattern is detected
            assert config.is_decorator_entry_point("my_custom_task"), (
                "Custom decorator 'my_custom_task' should be detected as entry point"
            )

            # Verify custom name pattern is detected
            assert config.is_entry_point_by_name("job_process_data"), (
                "Function name 'job_process_data' should be detected as entry point"
            )

            # Verify default patterns still work
            assert config.is_decorator_entry_point("pytest.fixture"), (
                "Default decorator 'pytest.fixture' should still be detected"
            )
            assert config.is_entry_point_by_name("test_something"), (
                "Default name pattern 'test_*' should still work"
            )
