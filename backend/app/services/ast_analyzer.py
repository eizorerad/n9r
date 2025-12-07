"""AST-based code analyzer using Tree-sitter.

Replaces regex-based heuristics with proper AST analysis to reduce false positives.
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

# Try to import tree-sitter and language bindings
try:
    from tree_sitter import Language, Node, Parser
    TREE_SITTER_AVAILABLE = True
except ImportError:
    TREE_SITTER_AVAILABLE = False
    logger.warning("tree-sitter not available, falling back to regex analysis")

try:
    import tree_sitter_python as tspython
    PYTHON_AVAILABLE = True
except ImportError:
    PYTHON_AVAILABLE = False
    logger.warning("tree-sitter-python not available")

try:
    import tree_sitter_javascript as tsjavascript
    JS_AVAILABLE = True
except ImportError:
    JS_AVAILABLE = False
    logger.warning("tree-sitter-javascript not available")

try:
    import tree_sitter_typescript as tstypescript
    TS_AVAILABLE = True
except ImportError:
    TS_AVAILABLE = False
    logger.warning("tree-sitter-typescript not available")


# Generic names that are problematic ONLY in certain contexts
GENERIC_NAMES = {
    'data', 'info', 'temp', 'tmp', 'result', 'res',
    'val', 'value', 'obj', 'item', 'ret', 'response',
}

# Single-letter names (except common loop vars in appropriate contexts)
SINGLE_LETTER_BAD = {'a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'k', 'l', 'm',
                     'n', 'o', 'p', 'q', 'r', 's', 't', 'u', 'v', 'w', 'z'}

# Acceptable single-letter names in specific contexts
LOOP_VARS_OK = {'i', 'j', 'k', 'n', 'x', 'y', 'z'}  # OK in for loops
MATH_VARS_OK = {'x', 'y', 'z', 'a', 'b', 'c'}  # OK in math-heavy code


@dataclass
class NamingIssue:
    """A naming issue found in code."""
    name: str
    line: int
    column: int
    context: str  # 'assignment', 'variable', 'function_local'
    severity: str  # 'low', 'medium', 'high'
    confidence: float  # 0.0 - 1.0
    suggestion: str | None = None


@dataclass
class MagicNumberIssue:
    """A magic number found in code."""
    value: str
    line: int
    column: int
    context: str  # 'assignment', 'comparison', 'argument'
    confidence: float


@dataclass
class ASTAnalysisResult:
    """Result of AST-based analysis."""
    generic_names: list[NamingIssue] = field(default_factory=list)
    magic_numbers: list[MagicNumberIssue] = field(default_factory=list)
    single_letter_vars: list[NamingIssue] = field(default_factory=list)

    # Counts for metrics
    generic_names_count: int = 0
    magic_numbers_count: int = 0

    # Analysis metadata
    files_analyzed: int = 0
    parse_errors: int = 0


class ASTAnalyzer:
    """AST-based code analyzer using Tree-sitter.

    IMPORTANT: Parsers are initialized lazily on first use, not at import time.
    This is required for compatibility with Celery's prefork pool on macOS,
    where tree-sitter C-extensions cause SIGSEGV after fork().
    """

    def __init__(self) -> None:
        self.parsers: dict[str, Parser] = {}
        self._initialized = False  # Lazy initialization flag

    def _ensure_parsers(self) -> None:
        """Initialize Tree-sitter parsers lazily on first use.

        This must be called inside worker processes, not at module import time,
        to avoid SIGSEGV issues with Celery prefork pool.
        """
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
                self.parsers['python'] = py_parser
                logger.info("Python parser initialized")
            except Exception as e:
                logger.error(f"Failed to init Python parser: {e}")

        if JS_AVAILABLE:
            try:
                js_parser = Parser(Language(tsjavascript.language()))
                self.parsers['javascript'] = js_parser
                logger.info("JavaScript parser initialized")
            except Exception as e:
                logger.error(f"Failed to init JavaScript parser: {e}")

        if TS_AVAILABLE:
            try:
                # TypeScript has separate tsx language
                ts_parser = Parser(Language(tstypescript.language_typescript()))
                self.parsers['typescript'] = ts_parser
                logger.info("TypeScript parser initialized")
            except Exception as e:
                logger.error(f"Failed to init TypeScript parser: {e}")

    def analyze_file(self, filepath: str, content: str) -> ASTAnalysisResult:
        """Analyze a single file using AST."""
        # Lazy initialization of parsers (required for Celery prefork compatibility)
        self._ensure_parsers()

        result = ASTAnalysisResult()
        result.files_analyzed = 1

        ext = Path(filepath).suffix.lower()
        language = self._detect_language(ext)

        if language not in self.parsers:
            # Fallback to regex for unsupported languages
            return self._analyze_with_regex(filepath, content, result)

        try:
            parser = self.parsers[language]
            tree = parser.parse(bytes(content, 'utf-8'))

            if tree.root_node.has_error:
                result.parse_errors += 1
                logger.debug(f"Parse errors in {filepath}, using partial AST")

            if language == 'python':
                self._analyze_python_ast(tree.root_node, content, result)
            elif language in ('javascript', 'typescript'):
                self._analyze_js_ast(tree.root_node, content, result)

        except Exception as e:
            logger.error(f"AST analysis failed for {filepath}: {e}")
            result.parse_errors += 1
            return self._analyze_with_regex(filepath, content, result)

        # Update counts
        result.generic_names_count = len(result.generic_names)
        result.magic_numbers_count = len(result.magic_numbers)

        return result

    def _detect_language(self, ext: str) -> str:
        """Detect language from file extension."""
        mapping = {
            '.py': 'python',
            '.js': 'javascript',
            '.jsx': 'javascript',
            '.ts': 'typescript',
            '.tsx': 'typescript',
        }
        return mapping.get(ext, 'unknown')

    def _analyze_python_ast(self, root: "Node", code: str, result: ASTAnalysisResult) -> None:
        """Analyze Python AST for naming issues."""
        # Track context: function params, loop vars, class attrs
        function_params: set[str] = set()
        loop_vars: set[str] = set()
        comprehension_vars: set[str] = set()

        def get_text(node: "Node") -> str:
            return code[node.start_byte:node.end_byte]

        def visit(node: "Node", in_function: bool = False, in_loop: bool = False):
            nonlocal function_params, loop_vars, comprehension_vars

            # Track function parameters (these are OK to be generic)
            if node.type == 'function_definition':
                params_node = node.child_by_field_name('parameters')
                if params_node:
                    for param in params_node.children:
                        if param.type == 'identifier':
                            function_params.add(get_text(param))
                        elif param.type in ('default_parameter', 'typed_parameter', 'typed_default_parameter'):
                            name_node = param.child_by_field_name('name')
                            if name_node:
                                function_params.add(get_text(name_node))

                # Analyze function body
                body = node.child_by_field_name('body')
                if body:
                    for child in body.children:
                        visit(child, in_function=True, in_loop=in_loop)
                return

            # Track for loop variables (i, j, k are OK here)
            if node.type == 'for_statement':
                left = node.child_by_field_name('left')
                if left:
                    if left.type == 'identifier':
                        loop_vars.add(get_text(left))
                    elif left.type == 'tuple_pattern':
                        for child in left.children:
                            if child.type == 'identifier':
                                loop_vars.add(get_text(child))

                # Analyze loop body
                body = node.child_by_field_name('body')
                if body:
                    for child in body.children:
                        visit(child, in_function=in_function, in_loop=True)
                return

            # Track comprehension variables
            if node.type in ('list_comprehension', 'set_comprehension', 'dictionary_comprehension', 'generator_expression'):
                for child in node.children:
                    if child.type == 'for_in_clause':
                        left = child.child_by_field_name('left')
                        if left and left.type == 'identifier':
                            comprehension_vars.add(get_text(left))

            # Check assignments for generic names
            if node.type == 'assignment':
                left = node.child_by_field_name('left')
                if left and left.type == 'identifier':
                    name = get_text(left)
                    line = left.start_point[0] + 1
                    col = left.start_point[1]

                    # Skip if it's a function parameter being reassigned
                    if name in function_params:
                        pass  # OK - reassigning param
                    # Skip loop variables
                    elif name in loop_vars or name in comprehension_vars:
                        pass  # OK - loop var
                    # Check for generic names
                    elif name.lower() in GENERIC_NAMES:
                        result.generic_names.append(NamingIssue(
                            name=name,
                            line=line,
                            column=col,
                            context='assignment',
                            severity='low',
                            confidence=0.85,
                            suggestion=f"Consider a more descriptive name than '{name}'"
                        ))
                    # Check single-letter vars (not in loops)
                    elif len(name) == 1 and name in SINGLE_LETTER_BAD and not in_loop:
                        result.single_letter_vars.append(NamingIssue(
                            name=name,
                            line=line,
                            column=col,
                            context='assignment',
                            severity='low',
                            confidence=0.7,
                            suggestion=f"Single-letter variable '{name}' outside loop context"
                        ))

            # Check for magic numbers
            if node.type == 'integer' or node.type == 'float':
                value = get_text(node)
                # Skip common acceptable values
                if value not in ('0', '1', '2', '-1', '0.0', '1.0', '0.5', '100', '1000'):
                    try:
                        num = float(value)
                        # Flag numbers that look like magic numbers
                        if abs(num) > 2 and num not in (10, 60, 24, 365, 100, 1000, 200, 201, 204, 400, 401, 403, 404, 500):
                            parent = node.parent
                            # Skip if it's in a constant assignment (UPPER_CASE)
                            if parent and parent.type == 'assignment':
                                left = parent.child_by_field_name('left')
                                if left and get_text(left).isupper():
                                    return  # It's a constant, OK

                            result.magic_numbers.append(MagicNumberIssue(
                                value=value,
                                line=node.start_point[0] + 1,
                                column=node.start_point[1],
                                context='expression',
                                confidence=0.7
                            ))
                    except ValueError:
                        pass

            # Recurse into children
            for child in node.children:
                visit(child, in_function=in_function, in_loop=in_loop)

        visit(root)

    def _analyze_js_ast(self, root: "Node", code: str, result: ASTAnalysisResult) -> None:
        """Analyze JavaScript/TypeScript AST for naming issues."""
        function_params: set[str] = set()
        loop_vars: set[str] = set()

        def get_text(node: "Node") -> str:
            return code[node.start_byte:node.end_byte]

        def visit(node: "Node", in_function: bool = False, in_loop: bool = False):
            nonlocal function_params, loop_vars

            # Track function parameters
            if node.type in ('function_declaration', 'function_expression', 'arrow_function', 'method_definition'):
                params = node.child_by_field_name('parameters')
                if params:
                    for param in params.children:
                        if param.type == 'identifier':
                            function_params.add(get_text(param))
                        elif param.type in ('assignment_pattern', 'rest_pattern'):
                            left = param.child_by_field_name('left') or param.child_by_field_name('name')
                            if left and left.type == 'identifier':
                                function_params.add(get_text(left))

                body = node.child_by_field_name('body')
                if body:
                    for child in body.children:
                        visit(child, in_function=True, in_loop=in_loop)
                return

            # Track for loop variables
            if node.type in ('for_statement', 'for_in_statement', 'for_of_statement'):
                # Handle different for loop types
                left = node.child_by_field_name('left')
                init = node.child_by_field_name('initializer')

                target = left or init
                if target:
                    if target.type == 'identifier':
                        loop_vars.add(get_text(target))
                    elif target.type == 'lexical_declaration':
                        for child in target.children:
                            if child.type == 'variable_declarator':
                                decl_name_node = child.child_by_field_name('name')
                                if decl_name_node and decl_name_node.type == 'identifier':
                                    loop_vars.add(get_text(decl_name_node))

                body = node.child_by_field_name('body')
                if body:
                    visit(body, in_function=in_function, in_loop=True)
                return

            # Check variable declarations
            if node.type == 'variable_declarator':
                name_node = node.child_by_field_name('name')
                if name_node and name_node.type == 'identifier':
                    name = get_text(name_node)
                    line = name_node.start_point[0] + 1
                    col = name_node.start_point[1]

                    if name in function_params or name in loop_vars:
                        pass  # OK
                    elif name.lower() in GENERIC_NAMES:
                        result.generic_names.append(NamingIssue(
                            name=name,
                            line=line,
                            column=col,
                            context='variable_declaration',
                            severity='low',
                            confidence=0.85,
                            suggestion=f"Consider a more descriptive name than '{name}'"
                        ))
                    elif len(name) == 1 and name in SINGLE_LETTER_BAD and not in_loop:
                        result.single_letter_vars.append(NamingIssue(
                            name=name,
                            line=line,
                            column=col,
                            context='variable_declaration',
                            severity='low',
                            confidence=0.7,
                        ))

            # Check for magic numbers
            if node.type == 'number':
                value = get_text(node)
                if value not in ('0', '1', '2', '-1', '0.0', '1.0', '100', '1000'):
                    try:
                        num = float(value)
                        if abs(num) > 2 and num not in (10, 60, 24, 365, 100, 1000, 200, 201, 204, 400, 401, 403, 404, 500):
                            # Check if it's a const assignment
                            parent = node.parent
                            grandparent = parent.parent if parent else None
                            if grandparent and grandparent.type == 'variable_declarator':
                                const_name_node = grandparent.child_by_field_name('name')
                                if const_name_node and get_text(const_name_node).isupper():
                                    return  # It's a constant

                            result.magic_numbers.append(MagicNumberIssue(
                                value=value,
                                line=node.start_point[0] + 1,
                                column=node.start_point[1],
                                context='expression',
                                confidence=0.7
                            ))
                    except ValueError:
                        pass

            for child in node.children:
                visit(child, in_function=in_function, in_loop=in_loop)

        visit(root)

    def _analyze_with_regex(self, filepath: str, content: str, result: ASTAnalysisResult) -> ASTAnalysisResult:
        """Fallback regex analysis with improved heuristics."""
        import re

        lines = content.split('\n')

        # Improved regex patterns with context awareness
        for i, line in enumerate(lines):
            stripped = line.strip()

            # Skip comments
            if stripped.startswith('#') or stripped.startswith('//') or stripped.startswith('/*'):
                continue

            # Skip function definitions (params are OK)
            if re.match(r'^\s*(async\s+)?def\s+\w+\s*\(', line):
                continue
            if re.match(r'^\s*(export\s+)?(async\s+)?function\s+', line):
                continue

            # Skip for loops (loop vars are OK)
            if re.match(r'^\s*for\s+\w+\s+in\s+', line):
                continue
            if re.match(r'^\s*for\s*\(', line):
                continue

            # Check for generic names in assignments only
            for name in GENERIC_NAMES:
                # Match: name = something (but not name == or name !=)
                pattern = rf'\b({name})\s*=\s*[^=]'
                match = re.search(pattern, line, re.IGNORECASE)
                if match:
                    result.generic_names.append(NamingIssue(
                        name=match.group(1),
                        line=i + 1,
                        column=match.start(),
                        context='assignment',
                        severity='low',
                        confidence=0.6,  # Lower confidence for regex
                    ))

        result.generic_names_count = len(result.generic_names)
        return result


# Thread-local storage for analyzer instances
# Using thread-local instead of global singleton to be safe with Celery workers
import threading

_thread_local = threading.local()


def get_ast_analyzer() -> ASTAnalyzer:
    """Get thread-local AST analyzer instance.

    Each worker thread/process gets its own analyzer instance.
    This ensures tree-sitter parsers are initialized in the correct process
    after Celery fork(), avoiding SIGSEGV on macOS.
    """
    if not hasattr(_thread_local, 'analyzer'):
        _thread_local.analyzer = ASTAnalyzer()
    return _thread_local.analyzer
