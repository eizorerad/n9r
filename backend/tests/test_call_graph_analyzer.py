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
