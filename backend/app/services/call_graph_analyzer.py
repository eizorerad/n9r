"""Call Graph Analyzer for Dead Code Detection.

Builds a function call graph from source code using tree-sitter AST parsing.
Identifies entry points and unreachable functions (dead code candidates).

Requirements: 1.1, 1.2, 1.3, 1.4, 1.5

IMPORTANT: This analyzer uses AST-based static analysis which has inherent limitations.
It cannot detect:
- Framework-registered handlers (FastAPI routes, Celery tasks, pytest fixtures)
- Functions passed as callbacks/parameters
- Decorator-based registration patterns
- Dynamic dispatch / reflection-based calls

To minimize false positives, we detect common framework patterns and mark them as entry points.
"""

import logging
import re
import threading
from dataclasses import dataclass, field
from pathlib import Path

from app.schemas.architecture_llm import DeadCodeFinding

logger = logging.getLogger(__name__)

# Try to import tree-sitter and language bindings
try:
    from tree_sitter import Language, Node, Parser

    TREE_SITTER_AVAILABLE = True
except ImportError:
    TREE_SITTER_AVAILABLE = False
    logger.warning("tree-sitter not available for call graph analysis")

try:
    import tree_sitter_python as tspython

    PYTHON_AVAILABLE = True
except ImportError:
    PYTHON_AVAILABLE = False

try:
    import tree_sitter_javascript as tsjavascript

    JS_AVAILABLE = True
except ImportError:
    JS_AVAILABLE = False

try:
    import tree_sitter_typescript as tstypescript

    TS_AVAILABLE = True
except ImportError:
    TS_AVAILABLE = False


# Entry point patterns for detection by function NAME
# Matches: main, __init__, test_*, *_handler, *_route, *_endpoint, *_view
ENTRY_POINT_NAME_PATTERNS = [
    re.compile(r"^main$"),
    re.compile(r"^__init__$"),
    re.compile(r"^test_"),
    re.compile(r"_handler$"),
    re.compile(r"_route$"),
    re.compile(r"_endpoint$"),
    re.compile(r"_view$"),
    # Python dunder methods (called by runtime)
    re.compile(r"^__[a-z_]+__$"),
]

# Decorator patterns that mark functions as entry points (framework-registered)
# These decorators register functions to be called by frameworks at runtime
ENTRY_POINT_DECORATOR_PATTERNS = [
    # FastAPI/Starlette route decorators
    re.compile(r"^(app|router)\.(get|post|put|patch|delete|options|head|trace|websocket)$"),
    re.compile(r"^(get|post|put|patch|delete|options|head)$"),  # Direct imports
    # Celery task decorators
    re.compile(r"^(celery_app|celery|app)\.(task|shared_task)$"),
    re.compile(r"^(task|shared_task)$"),
    # Pytest decorators
    re.compile(r"^pytest\.(fixture|mark\..+)$"),
    re.compile(r"^fixture$"),
    # Pydantic validators
    re.compile(r"^(model_validator|field_validator|validator|root_validator)$"),
    re.compile(r"^(computed_field|field_serializer)$"),
    # SQLAlchemy event listeners
    re.compile(r"^(event\.listens_for|listens_for)$"),
    # Click CLI commands
    re.compile(r"^(click\.)?(command|group|option|argument)$"),
    # Flask decorators
    re.compile(r"^(app|blueprint)\.(route|before_request|after_request|errorhandler)$"),
    # Django decorators
    re.compile(r"^(login_required|permission_required|require_http_methods)$"),
    # General callback/event patterns
    re.compile(r"^(on_event|event_handler|callback|subscriber)$"),
    # Hypothesis strategies (used in @given decorators)
    re.compile(r"^(given|composite|example)$"),
    # Property decorators
    re.compile(r"^(property|staticmethod|classmethod|abstractmethod)$"),
    # Dataclass/attrs
    re.compile(r"^(dataclass|attrs|define)$"),
    # Contextlib
    re.compile(r"^(contextmanager|asynccontextmanager)$"),
    # Caching decorators
    re.compile(r"^(cache|lru_cache|cached_property)$"),
    # Async decorators
    re.compile(r"^(asyncio\.coroutine|coroutine)$"),
]

# File path patterns that indicate all functions in the file are entry points
# (e.g., test files, migration files, CLI scripts)
ENTRY_POINT_FILE_PATTERNS = [
    re.compile(r"test_[^/]+\.py$"),  # test_*.py files
    re.compile(r"[^/]+_test\.py$"),  # *_test.py files
    re.compile(r"conftest\.py$"),    # pytest conftest
    re.compile(r"alembic/versions/"),  # Alembic migrations
    re.compile(r"migrations/"),       # Django migrations
    re.compile(r"__main__\.py$"),     # Entry point modules
    re.compile(r"cli\.py$"),          # CLI modules
    re.compile(r"commands?\.py$"),    # Command modules
    re.compile(r"scripts/[^/]+\.py$"),  # Scripts directory (CLI utilities)
]

# Function names that are commonly used as callbacks (passed as arguments)
CALLBACK_NAME_PATTERNS = [
    re.compile(r"^on_[a-z_]+$"),      # on_startup, on_shutdown, on_event
    re.compile(r"^on[A-Z]"),          # onClick, onChange (React)
    re.compile(r"^handle_[a-z_]+$"),  # handle_error, handle_request
    re.compile(r"^handle[A-Z]"),      # handleMount, handleClick (React)
    re.compile(r"_callback$"),        # *_callback
    re.compile(r"_hook$"),            # *_hook
    re.compile(r"_listener$"),        # *_listener
    re.compile(r"_factory$"),         # *_factory (often passed to constructors)
    re.compile(r"_strategy$"),        # *_strategy (Hypothesis strategies)
    re.compile(r"^toggle[A-Z]"),      # toggleExpand, toggleOpen (React)
    re.compile(r"^format[A-Z]"),      # formatTime, formatDate (helpers)
    re.compile(r"^get[A-Z].*Color$"), # getFileColor, getStatusColor (helpers)
    re.compile(r"^render[A-Z]"),      # renderItem, renderRow (React)
    re.compile(r"^use[A-Z]"),         # useEffect, useState (React hooks - custom)
]

# Async generator/iterator patterns (SSE, streaming)
ASYNC_GENERATOR_PATTERNS = [
    re.compile(r"^subscribe_"),       # subscribe_analysis_events
    re.compile(r"^stream_"),          # stream_results
    re.compile(r"_stream$"),          # event_stream
    re.compile(r"_generator$"),       # data_generator
]


@dataclass
class CallGraphNode:
    """A function/method in the call graph.

    Attributes:
        id: Unique identifier (file_path:function_name)
        file_path: Path to the source file
        name: Function/method name
        line_start: Starting line number (1-indexed)
        line_end: Ending line number (1-indexed)
        calls: Set of function IDs this function calls
        called_by: Set of function IDs that call this function
        is_entry_point: Whether this is an entry point (main, handler, etc.)
    """

    id: str
    file_path: str
    name: str
    line_start: int
    line_end: int
    calls: set[str] = field(default_factory=set)
    called_by: set[str] = field(default_factory=set)
    is_entry_point: bool = False


@dataclass
class CallGraph:
    """Complete call graph for a repository.

    Attributes:
        nodes: Dictionary mapping node IDs to CallGraphNode objects
        entry_points: List of entry point node IDs
    """

    nodes: dict[str, CallGraphNode] = field(default_factory=dict)
    entry_points: list[str] = field(default_factory=list)

    def get_unreachable(self) -> list[CallGraphNode]:
        """Find functions not reachable from any entry point.

        Performs a breadth-first traversal from all entry points
        to find all reachable functions. Returns the complement.

        Returns:
            List of CallGraphNode objects that are unreachable (dead code)
        """
        if not self.nodes:
            return []

        # Start with all entry points
        reachable: set[str] = set()
        to_visit: list[str] = list(self.entry_points)

        # BFS traversal
        while to_visit:
            current_id = to_visit.pop(0)
            if current_id in reachable:
                continue
            reachable.add(current_id)

            # Add all functions called by current function
            if current_id in self.nodes:
                for called_id in self.nodes[current_id].calls:
                    if called_id not in reachable and called_id in self.nodes:
                        to_visit.append(called_id)

        # Return unreachable nodes
        unreachable = [
            node for node_id, node in self.nodes.items() if node_id not in reachable
        ]
        return unreachable


def is_entry_point_by_name(name: str) -> bool:
    """Check if a function name matches entry point patterns.

    Entry point patterns:
    - main
    - __init__, __str__, __repr__, etc. (dunder methods)
    - test_* (test functions)
    - *_handler (request handlers)
    - *_route (route handlers)
    - *_endpoint (API endpoints)
    - *_view (view functions)

    Args:
        name: Function name to check

    Returns:
        True if the name matches an entry point pattern
    """
    if not name:
        return False

    for pattern in ENTRY_POINT_NAME_PATTERNS:
        if pattern.search(name):
            return True
    return False


def is_callback_by_name(name: str) -> bool:
    """Check if a function name suggests it's used as a callback.

    Callback patterns:
    - on_* (event handlers)
    - handle_* (handlers)
    - *_callback, *_hook, *_listener
    - *_factory (factory functions)
    - *_strategy (Hypothesis strategies)

    Args:
        name: Function name to check

    Returns:
        True if the name matches a callback pattern
    """
    if not name:
        return False

    for pattern in CALLBACK_NAME_PATTERNS:
        if pattern.search(name):
            return True
    return False


def is_async_generator_name(name: str) -> bool:
    """Check if a function name suggests it's an async generator/stream.

    Async generator patterns:
    - subscribe_* (SSE subscriptions)
    - stream_* (streaming functions)
    - *_stream, *_generator

    Args:
        name: Function name to check

    Returns:
        True if the name matches an async generator pattern
    """
    if not name:
        return False

    for pattern in ASYNC_GENERATOR_PATTERNS:
        if pattern.search(name):
            return True
    return False


def is_entry_point_file(file_path: str) -> bool:
    """Check if a file path indicates all functions are entry points.

    Entry point file patterns:
    - test_*.py, *_test.py (test files)
    - conftest.py (pytest fixtures)
    - alembic/versions/* (migrations)
    - __main__.py, cli.py (entry points)

    Args:
        file_path: Relative file path

    Returns:
        True if all functions in this file should be considered entry points
    """
    if not file_path:
        return False

    for pattern in ENTRY_POINT_FILE_PATTERNS:
        if pattern.search(file_path):
            return True
    return False


def is_decorator_entry_point(decorator_name: str) -> bool:
    """Check if a decorator marks a function as an entry point.

    Framework decorators that register functions:
    - @app.get, @router.post (FastAPI)
    - @celery_app.task (Celery)
    - @pytest.fixture (pytest)
    - @model_validator (Pydantic)
    - @property, @staticmethod, @classmethod

    Args:
        decorator_name: Full decorator name (e.g., "app.get", "pytest.fixture")

    Returns:
        True if this decorator marks the function as an entry point
    """
    if not decorator_name:
        return False

    for pattern in ENTRY_POINT_DECORATOR_PATTERNS:
        if pattern.search(decorator_name):
            return True
    return False


# Backward compatibility alias
def is_entry_point(name: str) -> bool:
    """Check if a function name matches entry point patterns.

    This is a backward-compatible alias for is_entry_point_by_name.
    """
    return is_entry_point_by_name(name)


class CallGraphAnalyzer:
    """Builds call graph from source code using tree-sitter AST.

    Analyzes Python and JavaScript/TypeScript files to extract:
    - Function definitions with line ranges
    - Function calls within each function body
    - Entry point classification

    IMPORTANT: Parsers are initialized lazily on first use, not at import time.
    This is required for compatibility with Celery's prefork pool on macOS.
    """

    def __init__(self) -> None:
        self.parsers: dict[str, Parser] = {}
        self._initialized = False

    def _ensure_parsers(self) -> None:
        """Initialize Tree-sitter parsers lazily on first use."""
        if self._initialized:
            return
        self._initialized = True
        self._init_parsers()

    def _init_parsers(self) -> None:
        """Initialize Tree-sitter parsers for supported languages."""
        if not TREE_SITTER_AVAILABLE:
            return

        if PYTHON_AVAILABLE:
            try:
                py_parser = Parser(Language(tspython.language()))
                self.parsers["python"] = py_parser
                logger.debug("Python parser initialized for call graph analysis")
            except Exception as e:
                logger.error(f"Failed to init Python parser: {e}")

        if JS_AVAILABLE:
            try:
                js_parser = Parser(Language(tsjavascript.language()))
                self.parsers["javascript"] = js_parser
                logger.debug("JavaScript parser initialized for call graph analysis")
            except Exception as e:
                logger.error(f"Failed to init JavaScript parser: {e}")

        if TS_AVAILABLE:
            try:
                ts_parser = Parser(Language(tstypescript.language_typescript()))
                self.parsers["typescript"] = ts_parser
                logger.debug("TypeScript parser initialized for call graph analysis")
            except Exception as e:
                logger.error(f"Failed to init TypeScript parser: {e}")

    def _detect_language(self, file_path: str) -> str:
        """Detect language from file extension."""
        ext = Path(file_path).suffix.lower()
        mapping = {
            ".py": "python",
            ".js": "javascript",
            ".jsx": "javascript",
            ".ts": "typescript",
            ".tsx": "typescript",
        }
        return mapping.get(ext, "unknown")

    def analyze(self, repo_path: Path) -> CallGraph:
        """Build call graph for entire repository.

        Scans all Python and JavaScript/TypeScript files in the repository,
        extracts function definitions and call expressions, and builds
        a complete call graph.

        Args:
            repo_path: Path to the repository root

        Returns:
            CallGraph with all functions and their relationships
        """
        self._ensure_parsers()

        call_graph = CallGraph()

        if not TREE_SITTER_AVAILABLE:
            logger.warning("Tree-sitter not available, returning empty call graph")
            return call_graph

        # Find all source files
        source_files = self._find_source_files(repo_path)
        logger.info(f"Found {len(source_files)} source files for call graph analysis")

        # First pass: extract all function definitions
        for file_path in source_files:
            try:
                self._extract_functions(file_path, repo_path, call_graph)
            except Exception as e:
                logger.warning(f"Failed to extract functions from {file_path}: {e}")

        # Second pass: extract call expressions and link them
        for file_path in source_files:
            try:
                self._extract_calls(file_path, repo_path, call_graph)
            except Exception as e:
                logger.warning(f"Failed to extract calls from {file_path}: {e}")

        # Identify entry points
        for node_id, node in call_graph.nodes.items():
            if node.is_entry_point:
                call_graph.entry_points.append(node_id)

        logger.info(
            f"Call graph built: {len(call_graph.nodes)} functions, "
            f"{len(call_graph.entry_points)} entry points"
        )

        return call_graph

    def _find_source_files(self, repo_path: Path) -> list[Path]:
        """Find all Python and JS/TS source files in repository."""
        source_files = []
        extensions = {".py", ".js", ".jsx", ".ts", ".tsx"}

        for ext in extensions:
            source_files.extend(repo_path.rglob(f"*{ext}"))

        # Filter out common non-source directories
        filtered = []
        exclude_patterns = {
            "node_modules",
            ".venv",
            "venv",
            "__pycache__",
            ".git",
            "dist",
            "build",
            ".next",
        }

        for f in source_files:
            parts = set(f.parts)
            if not parts.intersection(exclude_patterns):
                filtered.append(f)

        return filtered

    def _extract_functions(
        self, file_path: Path, repo_path: Path, call_graph: CallGraph
    ) -> None:
        """Extract function definitions from a source file."""
        language = self._detect_language(str(file_path))
        if language not in self.parsers:
            return

        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
        except Exception as e:
            logger.warning(f"Could not read {file_path}: {e}")
            return

        parser = self.parsers[language]
        tree = parser.parse(bytes(content, "utf-8"))

        relative_path = str(file_path.relative_to(repo_path))

        if language == "python":
            self._extract_python_functions(tree.root_node, content, relative_path, call_graph)
        elif language in ("javascript", "typescript"):
            self._extract_js_functions(tree.root_node, content, relative_path, call_graph)

    def _extract_python_functions(
        self, root: "Node", code: str, file_path: str, call_graph: CallGraph
    ) -> None:
        """Extract Python function definitions from AST.

        Detects entry points via:
        1. Function name patterns (test_*, *_handler, etc.)
        2. File path patterns (test files, migrations, etc.)
        3. Decorator patterns (@app.get, @pytest.fixture, etc.)
        4. Callback name patterns (*_callback, *_strategy, etc.)
        """
        # Check if entire file is an entry point file (tests, migrations, etc.)
        file_is_entry_point = is_entry_point_file(file_path)

        def get_text(node: "Node") -> str:
            return code[node.start_byte : node.end_byte]

        def extract_decorator_name(decorator_node: "Node") -> str | None:
            """Extract the decorator name from a decorator node.

            Handles:
            - @decorator
            - @decorator()
            - @module.decorator
            - @module.decorator()
            """
            # The decorator node contains the @ and the expression
            for child in decorator_node.children:
                if child.type == "identifier":
                    return get_text(child)
                elif child.type == "attribute":
                    # module.decorator
                    return get_text(child)
                elif child.type == "call":
                    # decorator() or module.decorator()
                    func_node = child.child_by_field_name("function")
                    if func_node:
                        if func_node.type == "identifier":
                            return get_text(func_node)
                        elif func_node.type == "attribute":
                            return get_text(func_node)
            return None

        def has_entry_point_decorator(decorators: list["Node"]) -> bool:
            """Check if any decorator marks this as an entry point."""
            for dec in decorators:
                dec_name = extract_decorator_name(dec)
                if dec_name and is_decorator_entry_point(dec_name):
                    return True
            return False

        def extract_calls_from_decorators(decorators: list["Node"]) -> set[str]:
            """Extract function calls from decorator arguments.

            Handles patterns like @given(x=strategy()) where strategy is called.
            """
            called_funcs: set[str] = set()

            def find_calls(node: "Node") -> None:
                if node.type == "call":
                    func_node = node.child_by_field_name("function")
                    if func_node and func_node.type == "identifier":
                        called_funcs.add(get_text(func_node))
                for child in node.children:
                    find_calls(child)

            for dec in decorators:
                find_calls(dec)

            return called_funcs

        def visit(node: "Node", decorators: list["Node"] | None = None) -> None:
            if decorators is None:
                decorators = []

            if node.type == "decorated_definition":
                # Collect decorators
                collected_decorators = []
                func_def = None
                for child in node.children:
                    if child.type == "decorator":
                        collected_decorators.append(child)
                    elif child.type == "function_definition":
                        func_def = child

                if func_def:
                    visit(func_def, collected_decorators)
                return

            if node.type == "function_definition":
                name_node = node.child_by_field_name("name")
                if name_node:
                    name = get_text(name_node)
                    line_start = node.start_point[0] + 1
                    line_end = node.end_point[0] + 1

                    node_id = f"{file_path}:{name}"

                    # Check if this is a class method (public methods are entry points)
                    is_class_method = False
                    is_public_method = False
                    parent = node.parent
                    while parent:
                        if parent.type == "class_definition":
                            is_class_method = True
                            # Public methods don't start with _ (except dunder methods)
                            is_public_method = not name.startswith("_") or name.startswith("__")
                            break
                        if parent.type == "function_definition":
                            # Nested function, not a class method
                            break
                        parent = parent.parent

                    # Determine if this is an entry point
                    is_entry = (
                        file_is_entry_point  # All functions in test/migration files
                        or is_entry_point_by_name(name)  # Name pattern match
                        or is_callback_by_name(name)  # Callback pattern match
                        or is_async_generator_name(name)  # Async generators (SSE)
                        or has_entry_point_decorator(decorators)  # Decorator match
                        or (is_class_method and is_public_method)  # Public class methods
                    )

                    call_graph.nodes[node_id] = CallGraphNode(
                        id=node_id,
                        file_path=file_path,
                        name=name,
                        line_start=line_start,
                        line_end=line_end,
                        is_entry_point=is_entry,
                    )

                    # Track functions called in decorator arguments
                    # (e.g., @given(x=strategy()) - strategy is called)
                    if decorators:
                        decorator_calls = extract_calls_from_decorators(decorators)
                        for called_name in decorator_calls:
                            # Mark these as called (will be linked in second pass)
                            called_id = f"{file_path}:{called_name}"
                            if called_id in call_graph.nodes:
                                call_graph.nodes[node_id].calls.add(called_id)
                                call_graph.nodes[called_id].called_by.add(node_id)

            for child in node.children:
                visit(child)

        visit(root)

    def _extract_js_functions(
        self, root: "Node", code: str, file_path: str, call_graph: CallGraph
    ) -> None:
        """Extract JavaScript/TypeScript function definitions from AST.

        Detects entry points via:
        1. Function name patterns (test_*, *_handler, etc.)
        2. File path patterns (test files, etc.)
        3. Export statements (exported functions are entry points)
        4. Callback name patterns (*_callback, *_strategy, etc.)
        """
        # Check if entire file is an entry point file (tests, etc.)
        file_is_entry_point = is_entry_point_file(file_path)

        def get_text(node: "Node") -> str:
            return code[node.start_byte : node.end_byte]

        def is_exported(node: "Node") -> bool:
            """Check if a node is exported (export default, export const, etc.)."""
            parent = node.parent
            if parent:
                if parent.type in ("export_statement", "export_default_declaration"):
                    return True
                # Check grandparent for: export const foo = ...
                grandparent = parent.parent
                if grandparent and grandparent.type == "export_statement":
                    return True
            return False

        def visit(node: "Node") -> None:
            name = None
            line_start = node.start_point[0] + 1
            line_end = node.end_point[0] + 1
            exported = is_exported(node)

            if node.type == "function_declaration":
                name_node = node.child_by_field_name("name")
                if name_node:
                    name = get_text(name_node)

            elif node.type == "method_definition":
                name_node = node.child_by_field_name("name")
                if name_node:
                    name = get_text(name_node)

            elif node.type == "variable_declarator":
                # Handle: const foo = () => {} or const foo = function() {}
                name_node = node.child_by_field_name("name")
                value_node = node.child_by_field_name("value")
                if (
                    name_node
                    and value_node
                    and value_node.type in ("arrow_function", "function_expression")
                ):
                    name = get_text(name_node)
                    line_end = value_node.end_point[0] + 1

            if name:
                node_id = f"{file_path}:{name}"

                # Determine if this is an entry point
                is_entry = (
                    file_is_entry_point  # All functions in test files
                    or is_entry_point_by_name(name)  # Name pattern match
                    or is_callback_by_name(name)  # Callback pattern match
                    or exported  # Exported functions are entry points
                )

                call_graph.nodes[node_id] = CallGraphNode(
                    id=node_id,
                    file_path=file_path,
                    name=name,
                    line_start=line_start,
                    line_end=line_end,
                    is_entry_point=is_entry,
                )

            for child in node.children:
                visit(child)

        visit(root)

    def _extract_calls(
        self, file_path: Path, repo_path: Path, call_graph: CallGraph
    ) -> None:
        """Extract function calls from a source file and link to call graph."""
        language = self._detect_language(str(file_path))
        if language not in self.parsers:
            return

        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
        except Exception as e:
            logger.warning(f"Could not read {file_path}: {e}")
            return

        parser = self.parsers[language]
        tree = parser.parse(bytes(content, "utf-8"))

        relative_path = str(file_path.relative_to(repo_path))

        if language == "python":
            self._extract_python_calls(tree.root_node, content, relative_path, call_graph)
        elif language in ("javascript", "typescript"):
            self._extract_js_calls(tree.root_node, content, relative_path, call_graph)

    def _extract_python_calls(
        self, root: "Node", code: str, file_path: str, call_graph: CallGraph
    ) -> None:
        """Extract Python function calls and link them in the call graph.

        Also detects:
        1. Direct function calls: func()
        2. Method calls: obj.method()
        3. Functions passed as arguments: SomeClass(callback=my_func)
        4. Functions passed as keyword arguments: func(handler=my_handler)
        5. Functions called from if __name__ == "__main__": blocks (CLI entry points)
        6. Module-level calls (outside any function) - mark called functions as entry points
        """

        def get_text(node: "Node") -> str:
            return code[node.start_byte : node.end_byte]

        def find_containing_function(line: int) -> str | None:
            """Find which function contains the given line."""
            for node_id, node in call_graph.nodes.items():
                if node.file_path == file_path:
                    if node.line_start <= line <= node.line_end:
                        return node_id
            return None

        def is_at_module_level(node: "Node") -> bool:
            """Check if a node is at module level (not inside any function/class)."""
            parent = node.parent
            while parent:
                if parent.type in ("function_definition", "class_definition"):
                    return False
                parent = parent.parent
            return True

        def link_call(caller_id: str, called_name: str) -> None:
            """Link a caller to a called function."""
            # Try to find the called function in the same file first
            called_id = f"{file_path}:{called_name}"
            if called_id not in call_graph.nodes:
                # Try to find in other files (simplified - just by name)
                for node_id in call_graph.nodes:
                    if node_id.endswith(f":{called_name}"):
                        called_id = node_id
                        break

            if called_id in call_graph.nodes and caller_id in call_graph.nodes:
                call_graph.nodes[caller_id].calls.add(called_id)
                call_graph.nodes[called_id].called_by.add(caller_id)

        def mark_as_entry_point(func_name: str) -> None:
            """Mark a function as an entry point (used as callback or called from __main__)."""
            # Try same file first
            func_id = f"{file_path}:{func_name}"
            if func_id in call_graph.nodes:
                call_graph.nodes[func_id].is_entry_point = True
                if func_id not in call_graph.entry_points:
                    call_graph.entry_points.append(func_id)
                return

            # Try other files
            for node_id, node in call_graph.nodes.items():
                if node_id.endswith(f":{func_name}"):
                    node.is_entry_point = True
                    if node_id not in call_graph.entry_points:
                        call_graph.entry_points.append(node_id)
                    return

        def is_main_block(node: "Node") -> bool:
            """Check if this is an 'if __name__ == "__main__":' block."""
            if node.type != "if_statement":
                return False

            condition = node.child_by_field_name("condition")
            if not condition or condition.type != "comparison_operator":
                return False

            # Check for __name__ == "__main__" pattern
            condition_text = get_text(condition)
            return '__name__' in condition_text and '__main__' in condition_text

        def extract_calls_from_main_block(block_node: "Node") -> None:
            """Extract all function calls from a __main__ block and mark them as entry points.

            This handles patterns like:
            - if __name__ == "__main__": main()
            - if __name__ == "__main__": asyncio.run(init_qdrant())
            """
            def find_calls(node: "Node") -> None:
                if node.type == "call":
                    func_node = node.child_by_field_name("function")
                    if func_node:
                        called_name = None
                        if func_node.type == "identifier":
                            called_name = get_text(func_node)
                        elif func_node.type == "attribute":
                            # For asyncio.run(func()), we need to check the arguments
                            attr_node = func_node.child_by_field_name("attribute")
                            if attr_node:
                                attr_name = get_text(attr_node)
                                # If it's asyncio.run, check the argument
                                if attr_name == "run":
                                    args_node = node.child_by_field_name("arguments")
                                    if args_node:
                                        for arg in args_node.children:
                                            if arg.type == "call":
                                                inner_func = arg.child_by_field_name("function")
                                                if inner_func and inner_func.type == "identifier":
                                                    mark_as_entry_point(get_text(inner_func))

                        if called_name:
                            mark_as_entry_point(called_name)

                    # Also check arguments for nested calls
                    args_node = node.child_by_field_name("arguments")
                    if args_node:
                        for arg in args_node.children:
                            find_calls(arg)

                for child in node.children:
                    find_calls(child)

            # Find the consequence block (the body of the if statement)
            for child in block_node.children:
                if child.type == "block":
                    find_calls(child)

        def extract_depends_calls(node: "Node") -> None:
            """Extract function names from Depends() calls and mark as entry points.

            Handles patterns like:
            - Depends(get_db)
            - Annotated[Type, Depends(get_db)]
            - db: Annotated[AsyncSession, Depends(get_db)]
            """
            def find_depends_calls(n: "Node") -> None:
                if n.type == "call":
                    func_node = n.child_by_field_name("function")
                    if func_node and func_node.type == "identifier":
                        func_name = get_text(func_node)
                        if func_name == "Depends":
                            # Get the argument to Depends()
                            args_node = n.child_by_field_name("arguments")
                            if args_node:
                                for arg in args_node.children:
                                    if arg.type == "identifier":
                                        # Depends(get_db) - get_db is the dependency
                                        mark_as_entry_point(get_text(arg))
                                    elif arg.type == "call":
                                        # Depends(SomeClass()) - the class is instantiated
                                        inner_func = arg.child_by_field_name("function")
                                        if inner_func and inner_func.type == "identifier":
                                            mark_as_entry_point(get_text(inner_func))

                for child in n.children:
                    find_depends_calls(child)

            find_depends_calls(node)

        def extract_class_body_calls(class_node: "Node") -> None:
            """Extract function calls from class body (outside methods).

            Handles patterns like:
            - class Settings:
            -     env_file = _find_env_file()
            -     model_config = SettingsConfigDict(env_file=_find_env_file())
            """
            # Find the class body
            body_node = class_node.child_by_field_name("body")
            if not body_node:
                return

            def find_calls_in_assignment(n: "Node") -> None:
                """Find function calls in assignment statements."""
                if n.type == "call":
                    func_node = n.child_by_field_name("function")
                    if func_node:
                        called_name = None
                        if func_node.type == "identifier":
                            called_name = get_text(func_node)
                        elif func_node.type == "attribute":
                            # For method calls like module.func()
                            attr_node = func_node.child_by_field_name("attribute")
                            if attr_node:
                                called_name = get_text(attr_node)

                        if called_name:
                            mark_as_entry_point(called_name)

                    # Also check arguments for nested calls
                    args_node = n.child_by_field_name("arguments")
                    if args_node:
                        for arg in args_node.children:
                            find_calls_in_assignment(arg)

                for child in n.children:
                    find_calls_in_assignment(child)

            # Iterate through class body children
            for child in body_node.children:
                # Look for assignment statements (class attributes)
                if child.type in ("expression_statement", "assignment"):
                    find_calls_in_assignment(child)

        def visit(node: "Node") -> None:
            # Check for if __name__ == "__main__": blocks first
            if is_main_block(node):
                extract_calls_from_main_block(node)
                # Continue visiting to also track regular calls

            # Check for class definitions to extract class body calls
            if node.type == "class_definition":
                extract_class_body_calls(node)

            # Check for Depends() patterns (FastAPI dependency injection)
            # This handles: Annotated[Type, Depends(func)], Depends(func), etc.
            if node.type in ("subscript", "call", "assignment"):
                extract_depends_calls(node)

            if node.type == "call":
                function_node = node.child_by_field_name("function")
                arguments_node = node.child_by_field_name("arguments")

                if function_node:
                    call_line = node.start_point[0] + 1
                    caller_id = find_containing_function(call_line)

                    # Get the called function name
                    called_name = None
                    is_self_call = False
                    if function_node.type == "identifier":
                        called_name = get_text(function_node)
                    elif function_node.type == "attribute":
                        # For method calls like obj.method() or self.method()
                        obj_node = function_node.child_by_field_name("object")
                        attr_node = function_node.child_by_field_name("attribute")
                        if attr_node:
                            called_name = get_text(attr_node)
                            # Check if it's a self.method() call
                            if obj_node and get_text(obj_node) == "self":
                                is_self_call = True

                    if called_name and caller_id:
                        link_call(caller_id, called_name)
                        # For self.method() calls, also mark the method as called
                        # This ensures class methods aren't flagged as dead code
                        if is_self_call:
                            called_id = f"{file_path}:{called_name}"
                            if called_id in call_graph.nodes:
                                call_graph.nodes[caller_id].calls.add(called_id)
                                call_graph.nodes[called_id].called_by.add(caller_id)
                    elif called_name and is_at_module_level(node):
                        # Module-level calls (outside any function) mark called functions as entry points
                        # e.g., run_async = create_async_runner() at module level
                        mark_as_entry_point(called_name)

                # Check for functions passed as arguments (callbacks)
                # e.g., FastAPI(lifespan=lifespan), app.add_event_handler("startup", on_startup)
                if arguments_node:
                    for arg in arguments_node.children:
                        # Keyword argument: callback=my_func
                        if arg.type == "keyword_argument":
                            value_node = arg.child_by_field_name("value")
                            if value_node and value_node.type == "identifier":
                                func_name = get_text(value_node)
                                # If this identifier refers to a known function, mark it as entry point
                                mark_as_entry_point(func_name)

                        # Positional argument that's an identifier (could be a callback)
                        elif arg.type == "identifier":
                            func_name = get_text(arg)
                            # Check if this is a known function being passed as callback
                            func_id = f"{file_path}:{func_name}"
                            if func_id in call_graph.nodes:
                                # Heuristic: if a function is passed as an argument, it's likely a callback
                                mark_as_entry_point(func_name)

            for child in node.children:
                visit(child)

        visit(root)

    def _extract_js_calls(
        self, root: "Node", code: str, file_path: str, call_graph: CallGraph
    ) -> None:
        """Extract JavaScript/TypeScript function calls and link them."""

        def get_text(node: "Node") -> str:
            return code[node.start_byte : node.end_byte]

        def find_containing_function(line: int) -> str | None:
            """Find which function contains the given line."""
            for node_id, node in call_graph.nodes.items():
                if node.file_path == file_path:
                    if node.line_start <= line <= node.line_end:
                        return node_id
            return None

        def link_js_call(caller_id: str, called_name: str) -> None:
            """Link a JS/TS caller to a called function."""
            called_id = f"{file_path}:{called_name}"
            if called_id not in call_graph.nodes:
                for node_id in call_graph.nodes:
                    if node_id.endswith(f":{called_name}"):
                        called_id = node_id
                        break

            if called_id in call_graph.nodes and caller_id in call_graph.nodes:
                call_graph.nodes[caller_id].calls.add(called_id)
                call_graph.nodes[called_id].called_by.add(caller_id)

        def mark_js_entry_point(func_name: str) -> None:
            """Mark a JS/TS function as an entry point."""
            func_id = f"{file_path}:{func_name}"
            if func_id in call_graph.nodes:
                call_graph.nodes[func_id].is_entry_point = True
                if func_id not in call_graph.entry_points:
                    call_graph.entry_points.append(func_id)

        def visit(node: "Node") -> None:
            # Handle new ClassName() - constructor calls
            if node.type == "new_expression":
                constructor_node = node.child_by_field_name("constructor")
                if constructor_node and constructor_node.type == "identifier":
                    class_name = get_text(constructor_node)
                    # Mark the constructor as called (constructors are entry points)
                    mark_js_entry_point("constructor")
                    # Also try to find a class with this name
                    for node_id in call_graph.nodes:
                        if node_id.endswith(f":{class_name}"):
                            call_graph.nodes[node_id].is_entry_point = True

            if node.type == "call_expression":
                function_node = node.child_by_field_name("function")
                if function_node:
                    call_line = node.start_point[0] + 1
                    caller_id = find_containing_function(call_line)

                    called_name = None
                    is_this_call = False
                    if function_node.type == "identifier":
                        called_name = get_text(function_node)
                    elif function_node.type == "member_expression":
                        obj_node = function_node.child_by_field_name("object")
                        prop_node = function_node.child_by_field_name("property")
                        if prop_node:
                            called_name = get_text(prop_node)
                            # Check if it's a this.method() call
                            if obj_node and get_text(obj_node) == "this":
                                is_this_call = True

                    if called_name and caller_id:
                        link_js_call(caller_id, called_name)
                        # For this.method() calls, ensure the method is linked
                        if is_this_call:
                            called_id = f"{file_path}:{called_name}"
                            if called_id in call_graph.nodes:
                                call_graph.nodes[caller_id].calls.add(called_id)
                                call_graph.nodes[called_id].called_by.add(caller_id)

            for child in node.children:
                visit(child)

        visit(root)

    def to_dead_code_findings(self, call_graph: CallGraph) -> list[DeadCodeFinding]:
        """Convert unreachable nodes to DeadCodeFinding objects.

        Generates natural language evidence strings and suggested actions
        for each dead code finding.

        Args:
            call_graph: The analyzed call graph

        Returns:
            List of DeadCodeFinding objects for unreachable functions
        """
        unreachable = call_graph.get_unreachable()
        findings = []

        for node in unreachable:
            line_count = node.line_end - node.line_start + 1

            # Generate evidence string
            evidence = f"Function '{node.name}' is never called from any entry point in the codebase"

            # Generate suggested action
            suggested_action = f"Safe to remove - no callers found. This will reduce codebase by {line_count} lines."

            finding = DeadCodeFinding(
                file_path=node.file_path,
                function_name=node.name,
                line_start=node.line_start,
                line_end=node.line_end,
                line_count=line_count,
                confidence=1.0,  # Call-graph proven
                evidence=evidence,
                suggested_action=suggested_action,
                last_modified=None,  # Could be populated from git history
            )
            findings.append(finding)

        return findings


# Thread-local storage for analyzer instances
_thread_local = threading.local()


def get_call_graph_analyzer() -> CallGraphAnalyzer:
    """Get thread-local CallGraphAnalyzer instance.

    Each worker thread/process gets its own analyzer instance.
    This ensures tree-sitter parsers are initialized in the correct process
    after Celery fork(), avoiding SIGSEGV on macOS.
    """
    if not hasattr(_thread_local, "call_graph_analyzer"):
        _thread_local.call_graph_analyzer = CallGraphAnalyzer()
    return _thread_local.call_graph_analyzer
