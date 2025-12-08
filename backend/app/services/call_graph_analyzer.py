"""Call Graph Analyzer for Dead Code Detection.

Builds a function call graph from source code using tree-sitter AST parsing.
Identifies entry points and unreachable functions (dead code candidates).

Requirements: 1.1, 1.2, 1.3, 1.4, 1.5
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


# Entry point patterns for detection
# Matches: main, __init__, test_*, *_handler, *_route, *_endpoint, *_view
ENTRY_POINT_PATTERNS = [
    re.compile(r"^main$"),
    re.compile(r"^__init__$"),
    re.compile(r"^test_"),
    re.compile(r"_handler$"),
    re.compile(r"_route$"),
    re.compile(r"_endpoint$"),
    re.compile(r"_view$"),
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


def is_entry_point(name: str) -> bool:
    """Check if a function name matches entry point patterns.

    Entry point patterns:
    - main
    - __init__
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

    for pattern in ENTRY_POINT_PATTERNS:
        if pattern.search(name):
            return True
    return False


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
        """Extract Python function definitions from AST."""

        def get_text(node: "Node") -> str:
            return code[node.start_byte : node.end_byte]

        def visit(node: "Node") -> None:
            if node.type == "function_definition":
                name_node = node.child_by_field_name("name")
                if name_node:
                    name = get_text(name_node)
                    line_start = node.start_point[0] + 1
                    line_end = node.end_point[0] + 1

                    node_id = f"{file_path}:{name}"
                    is_entry = is_entry_point(name)

                    call_graph.nodes[node_id] = CallGraphNode(
                        id=node_id,
                        file_path=file_path,
                        name=name,
                        line_start=line_start,
                        line_end=line_end,
                        is_entry_point=is_entry,
                    )

            # Also handle async functions
            if node.type == "decorated_definition":
                for child in node.children:
                    if child.type == "function_definition":
                        visit(child)
                        return

            for child in node.children:
                visit(child)

        visit(root)

    def _extract_js_functions(
        self, root: "Node", code: str, file_path: str, call_graph: CallGraph
    ) -> None:
        """Extract JavaScript/TypeScript function definitions from AST."""

        def get_text(node: "Node") -> str:
            return code[node.start_byte : node.end_byte]

        def visit(node: "Node") -> None:
            name = None
            line_start = node.start_point[0] + 1
            line_end = node.end_point[0] + 1

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
                is_entry = is_entry_point(name)

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
        """Extract Python function calls and link them in the call graph."""

        def get_text(node: "Node") -> str:
            return code[node.start_byte : node.end_byte]

        def find_containing_function(line: int) -> str | None:
            """Find which function contains the given line."""
            for node_id, node in call_graph.nodes.items():
                if node.file_path == file_path:
                    if node.line_start <= line <= node.line_end:
                        return node_id
            return None

        def visit(node: "Node") -> None:
            if node.type == "call":
                function_node = node.child_by_field_name("function")
                if function_node:
                    call_line = node.start_point[0] + 1
                    caller_id = find_containing_function(call_line)

                    # Get the called function name
                    called_name = None
                    if function_node.type == "identifier":
                        called_name = get_text(function_node)
                    elif function_node.type == "attribute":
                        # For method calls like obj.method(), get just the method name
                        attr_node = function_node.child_by_field_name("attribute")
                        if attr_node:
                            called_name = get_text(attr_node)

                    if called_name and caller_id:
                        # Try to find the called function in the same file first
                        called_id = f"{file_path}:{called_name}"
                        if called_id not in call_graph.nodes:
                            # Try to find in other files (simplified - just by name)
                            for node_id in call_graph.nodes:
                                if node_id.endswith(f":{called_name}"):
                                    called_id = node_id
                                    break

                        if called_id in call_graph.nodes:
                            call_graph.nodes[caller_id].calls.add(called_id)
                            call_graph.nodes[called_id].called_by.add(caller_id)

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

        def visit(node: "Node") -> None:
            if node.type == "call_expression":
                function_node = node.child_by_field_name("function")
                if function_node:
                    call_line = node.start_point[0] + 1
                    caller_id = find_containing_function(call_line)

                    called_name = None
                    if function_node.type == "identifier":
                        called_name = get_text(function_node)
                    elif function_node.type == "member_expression":
                        prop_node = function_node.child_by_field_name("property")
                        if prop_node:
                            called_name = get_text(prop_node)

                    if called_name and caller_id:
                        called_id = f"{file_path}:{called_name}"
                        if called_id not in call_graph.nodes:
                            for node_id in call_graph.nodes:
                                if node_id.endswith(f":{called_name}"):
                                    called_id = node_id
                                    break

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
