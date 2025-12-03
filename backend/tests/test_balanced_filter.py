"""Property-based tests for Balanced Architecture Filter.

Uses Hypothesis for property-based testing to verify correctness properties
defined in the design document.
"""

import re
import numpy as np
from hypothesis import given, strategies as st, settings, HealthCheck

from app.services.cluster_analyzer import (
    extract_imports,
    is_likely_boilerplate,
    FRAMEWORK_CONVENTIONS,
    COMMON_UTILITY_NAMES,
    UTILITY_DIR_PATTERNS,
    ARCHITECTURAL_SUFFIXES,
)


# =============================================================================
# Custom Strategies for Python Import Generation
# =============================================================================

def valid_python_identifier() -> st.SearchStrategy[str]:
    """Generate valid Python identifiers (module names)."""
    # Start with letter or underscore, followed by letters, digits, or underscores
    return st.from_regex(r"[a-zA-Z_][a-zA-Z0-9_]*", fullmatch=True).filter(
        lambda s: len(s) >= 1 and len(s) <= 50
    )


def valid_module_path() -> st.SearchStrategy[str]:
    """Generate valid Python module paths like 'os.path' or 'app.services.cluster'."""
    return st.lists(
        valid_python_identifier(),
        min_size=1,
        max_size=4
    ).map(lambda parts: ".".join(parts))


def python_from_import_statement(module: str) -> str:
    """Generate a 'from X import Y' statement."""
    return f"from {module} import something"


def python_import_statement(module: str) -> str:
    """Generate an 'import X' statement."""
    return f"import {module}"


@st.composite
def python_code_with_imports(draw) -> tuple[str, set[str]]:
    """Generate Python code with known import statements.
    
    Returns:
        A tuple of (code_string, expected_imports_set)
    """
    # Generate a list of module paths to import
    num_imports = draw(st.integers(min_value=0, max_value=10))
    modules = draw(st.lists(valid_module_path(), min_size=num_imports, max_size=num_imports))
    
    # Decide import style for each module
    import_lines = []
    expected_imports = set()
    
    for module in modules:
        use_from_import = draw(st.booleans())
        if use_from_import:
            import_lines.append(python_from_import_statement(module))
        else:
            import_lines.append(python_import_statement(module))
        expected_imports.add(module)
    
    # Add some non-import code to make it realistic
    non_import_lines = draw(st.lists(
        st.sampled_from([
            "# This is a comment",
            "",
            "def foo():",
            "    pass",
            "x = 1",
            "class Bar:",
            "    pass",
        ]),
        min_size=0,
        max_size=5
    ))
    
    # Combine imports and code
    all_lines = import_lines + non_import_lines
    draw(st.randoms()).shuffle(all_lines)
    
    code = "\n".join(all_lines)
    return code, expected_imports


# =============================================================================
# Property Tests for Import Analysis
# =============================================================================

class TestPythonImportExtractionProperties:
    """Property tests for Python import extraction.
    
    **Feature: balanced-architecture-filter, Property 1: Python Import Extraction Completeness**
    **Validates: Requirements 1.1**
    """
    
    @given(python_code_with_imports())
    @settings(max_examples=100)
    def test_python_import_extraction_completeness(self, code_and_imports: tuple[str, set[str]]):
        """
        **Feature: balanced-architecture-filter, Property 1: Python Import Extraction Completeness**
        **Validates: Requirements 1.1**
        
        Property: For any Python code string containing `from X import Y` or `import X` 
        statements, the `extract_imports` function SHALL return a set containing all 
        module paths X.
        """
        code, expected_imports = code_and_imports
        
        # Extract imports using the function under test
        actual_imports = extract_imports(code, "python")
        
        # Property: All expected imports should be found
        # The extracted set should be a superset of (or equal to) expected imports
        assert expected_imports.issubset(actual_imports), (
            f"Missing imports!\n"
            f"Expected: {expected_imports}\n"
            f"Actual: {actual_imports}\n"
            f"Missing: {expected_imports - actual_imports}\n"
            f"Code:\n{code}"
        )


# =============================================================================
# Custom Strategies for JavaScript/TypeScript Import Generation
# =============================================================================

def valid_js_module_path() -> st.SearchStrategy[str]:
    """Generate valid JS/TS module paths like './utils', '@scope/package', 'lodash'."""
    # Generate different types of module paths
    return st.one_of(
        # Relative paths: ./foo, ../bar/baz
        st.lists(
            st.from_regex(r"[a-zA-Z][a-zA-Z0-9_-]*", fullmatch=True).filter(
                lambda s: len(s) >= 1 and len(s) <= 20
            ),
            min_size=1,
            max_size=3
        ).map(lambda parts: "./" + "/".join(parts)),
        # Package names: lodash, react-dom
        st.from_regex(r"[a-z][a-z0-9-]*", fullmatch=True).filter(
            lambda s: len(s) >= 2 and len(s) <= 30
        ),
        # Scoped packages: @scope/package
        st.tuples(
            st.from_regex(r"[a-z][a-z0-9-]*", fullmatch=True).filter(lambda s: 2 <= len(s) <= 15),
            st.from_regex(r"[a-z][a-z0-9-]*", fullmatch=True).filter(lambda s: 2 <= len(s) <= 15),
        ).map(lambda t: f"@{t[0]}/{t[1]}"),
    )


def js_import_from_statement(module: str) -> str:
    """Generate an 'import X from "Y"' statement."""
    return f'import something from "{module}"'


def js_require_statement(module: str) -> str:
    """Generate a 'require("Y")' statement."""
    return f'const x = require("{module}")'


@st.composite
def js_code_with_imports(draw) -> tuple[str, set[str]]:
    """Generate JavaScript/TypeScript code with known import statements.
    
    Returns:
        A tuple of (code_string, expected_imports_set)
    """
    # Generate a list of module paths to import
    num_imports = draw(st.integers(min_value=0, max_value=10))
    modules = draw(st.lists(valid_js_module_path(), min_size=num_imports, max_size=num_imports))
    
    # Decide import style for each module
    import_lines = []
    expected_imports = set()
    
    for module in modules:
        use_import_from = draw(st.booleans())
        if use_import_from:
            import_lines.append(js_import_from_statement(module))
        else:
            import_lines.append(js_require_statement(module))
        expected_imports.add(module)
    
    # Add some non-import code to make it realistic
    non_import_lines = draw(st.lists(
        st.sampled_from([
            "// This is a comment",
            "",
            "function foo() {",
            "  return 42;",
            "}",
            "const x = 1;",
            "class Bar {",
            "  constructor() {}",
            "}",
        ]),
        min_size=0,
        max_size=5
    ))
    
    # Combine imports and code
    all_lines = import_lines + non_import_lines
    draw(st.randoms()).shuffle(all_lines)
    
    code = "\n".join(all_lines)
    return code, expected_imports


class TestJavaScriptImportExtractionProperties:
    """Property tests for JavaScript/TypeScript import extraction.
    
    **Feature: balanced-architecture-filter, Property 2: JavaScript/TypeScript Import Extraction Completeness**
    **Validates: Requirements 1.2**
    """
    
    @given(js_code_with_imports())
    @settings(max_examples=100)
    def test_js_import_extraction_completeness(self, code_and_imports: tuple[str, set[str]]):
        """
        **Feature: balanced-architecture-filter, Property 2: JavaScript/TypeScript Import Extraction Completeness**
        **Validates: Requirements 1.2**
        
        Property: For any JavaScript or TypeScript code string containing `import X from 'Y'` 
        or `require('Y')` statements, the `extract_imports` function SHALL return a set 
        containing all module paths Y.
        """
        code, expected_imports = code_and_imports
        
        # Test with both 'javascript' and 'typescript' language identifiers
        for lang in ["javascript", "typescript", "js", "ts"]:
            actual_imports = extract_imports(code, lang)
            
            # Property: All expected imports should be found
            assert expected_imports.issubset(actual_imports), (
                f"Missing imports for language '{lang}'!\n"
                f"Expected: {expected_imports}\n"
                f"Actual: {actual_imports}\n"
                f"Missing: {expected_imports - actual_imports}\n"
                f"Code:\n{code}"
            )



# =============================================================================
# Custom Strategies for Import Relationship Testing
# =============================================================================

def valid_file_path() -> st.SearchStrategy[str]:
    """Generate valid file paths for testing."""
    return st.one_of(
        # Python file paths
        st.lists(
            st.from_regex(r"[a-z][a-z0-9_]*", fullmatch=True).filter(lambda s: 2 <= len(s) <= 15),
            min_size=1,
            max_size=4
        ).map(lambda parts: "/".join(parts) + ".py"),
        # JavaScript file paths
        st.lists(
            st.from_regex(r"[a-z][a-z0-9-]*", fullmatch=True).filter(lambda s: 2 <= len(s) <= 15),
            min_size=1,
            max_size=4
        ).map(lambda parts: "/".join(parts) + ".js"),
    )


@st.composite
def import_graph_with_circular(draw) -> tuple[str, str, dict[str, set[str]]]:
    """Generate an import graph where two files import each other (circular).
    
    Returns:
        A tuple of (file_a, file_b, import_graph) where file_a and file_b have circular imports
    """
    # Generate two distinct file paths
    file_a = draw(valid_file_path())
    file_b = draw(valid_file_path().filter(lambda p: p != file_a))
    
    # Convert to module paths for imports
    from app.services.cluster_analyzer import to_module_path
    module_a = to_module_path(file_a)
    module_b = to_module_path(file_b)
    
    # Create import graph where both files import each other
    import_graph = {
        file_a: {module_b},  # file_a imports file_b
        file_b: {module_a},  # file_b imports file_a
    }
    
    return file_a, file_b, import_graph


class TestImportRelationshipProperties:
    """Property tests for import relationship analysis.
    
    **Feature: balanced-architecture-filter, Property 3: Import Relationship Symmetry**
    **Validates: Requirements 1.4**
    """
    
    @given(import_graph_with_circular())
    @settings(max_examples=100)
    def test_import_relationship_symmetry(self, graph_data: tuple[str, str, dict[str, set[str]]]):
        """
        **Feature: balanced-architecture-filter, Property 3: Import Relationship Symmetry**
        **Validates: Requirements 1.4**
        
        Property: For any two files A and B with an import graph, if 
        `analyze_import_relationship(A, B)` returns `is_circular=True`, 
        then both `a_imports_b` and `b_imports_a` SHALL be True.
        """
        from app.services.cluster_analyzer import analyze_import_relationship
        
        file_a, file_b, import_graph = graph_data
        
        # Analyze the import relationship
        result = analyze_import_relationship(file_a, file_b, import_graph)
        
        # Property: If is_circular is True, both directions must be True
        if result.is_circular:
            assert result.a_imports_b, (
                f"is_circular=True but a_imports_b=False\n"
                f"file_a: {file_a}\n"
                f"file_b: {file_b}\n"
                f"import_graph: {import_graph}"
            )
            assert result.b_imports_a, (
                f"is_circular=True but b_imports_a=False\n"
                f"file_a: {file_a}\n"
                f"file_b: {file_b}\n"
                f"import_graph: {import_graph}"
            )
        
        # Additional property: is_circular should be True when both directions are True
        # (This is the converse - if both import each other, it should be circular)
        if result.a_imports_b and result.b_imports_a:
            assert result.is_circular, (
                f"Both a_imports_b and b_imports_a are True but is_circular=False\n"
                f"file_a: {file_a}\n"
                f"file_b: {file_b}\n"
                f"import_graph: {import_graph}"
            )


# =============================================================================
# Custom Strategies for Boilerplate Detection Testing
# =============================================================================

def dunder_method_name() -> st.SearchStrategy[str]:
    """Generate valid Python dunder method names (__X__ pattern)."""
    # Generate the inner part (at least 1 character)
    inner = st.from_regex(r"[a-z][a-z0-9_]*", fullmatch=True).filter(
        lambda s: 1 <= len(s) <= 20
    )
    return inner.map(lambda s: f"__{s}__")


def framework_convention_name() -> st.SearchStrategy[str]:
    """Generate framework convention method names."""
    return st.sampled_from(list(FRAMEWORK_CONVENTIONS))


def common_utility_name() -> st.SearchStrategy[str]:
    """Generate common utility function names."""
    return st.sampled_from(list(COMMON_UTILITY_NAMES))


def short_name() -> st.SearchStrategy[str]:
    """Generate short function names (1-3 characters)."""
    return st.from_regex(r"[a-zA-Z][a-zA-Z0-9]{0,2}", fullmatch=True).filter(
        lambda s: 1 <= len(s) <= 3
    )


def utility_directory_path() -> st.SearchStrategy[str]:
    """Generate file paths containing utility directory patterns."""
    # Generate a path with one of the utility directory patterns
    prefix = st.from_regex(r"[a-z][a-z0-9_/]*", fullmatch=True).filter(
        lambda s: 1 <= len(s) <= 30
    )
    suffix = st.from_regex(r"[a-z][a-z0-9_]*\.py", fullmatch=True).filter(
        lambda s: 4 <= len(s) <= 20
    )
    pattern = st.sampled_from(["/utils/", "/helpers/", "/lib/", "/common/"])
    
    return st.tuples(prefix, pattern, suffix).map(
        lambda t: f"{t[0]}{t[1]}{t[2]}"
    )


def non_utility_directory_path() -> st.SearchStrategy[str]:
    """Generate file paths NOT containing utility directory patterns."""
    return st.from_regex(r"[a-z][a-z0-9_/]*\.py", fullmatch=True).filter(
        lambda s: (
            5 <= len(s) <= 50 and
            "/utils/" not in s.lower() and
            "/helpers/" not in s.lower() and
            "/lib/" not in s.lower() and
            "/common/" not in s.lower()
        )
    )


# =============================================================================
# Property Tests for Boilerplate Detection
# =============================================================================

class TestDunderMethodClassificationProperties:
    """Property tests for Python dunder method classification.
    
    **Feature: balanced-architecture-filter, Property 4: Dunder Method Classification**
    **Validates: Requirements 2.1**
    """
    
    @given(dunder_method_name(), st.text(max_size=100))
    @settings(max_examples=100)
    def test_dunder_method_classification(self, name: str, file_path: str):
        """
        **Feature: balanced-architecture-filter, Property 4: Dunder Method Classification**
        **Validates: Requirements 2.1**
        
        Property: For any function name matching the pattern `__X__` (starting and 
        ending with double underscores), `is_likely_boilerplate` SHALL return 
        `(True, reason)` where reason contains "dunder".
        """
        is_boilerplate, reason = is_likely_boilerplate(name, file_path)
        
        assert is_boilerplate, (
            f"Dunder method '{name}' should be classified as boilerplate\n"
            f"Got: is_boilerplate={is_boilerplate}, reason='{reason}'"
        )
        assert "dunder" in reason.lower(), (
            f"Reason should mention 'dunder' for dunder method '{name}'\n"
            f"Got reason: '{reason}'"
        )


class TestFrameworkConventionClassificationProperties:
    """Property tests for framework convention method classification.
    
    **Feature: balanced-architecture-filter, Property 5: Framework Convention Classification**
    **Validates: Requirements 2.2**
    """
    
    @given(framework_convention_name(), st.text(max_size=100))
    @settings(max_examples=100)
    def test_framework_convention_classification(self, name: str, file_path: str):
        """
        **Feature: balanced-architecture-filter, Property 5: Framework Convention Classification**
        **Validates: Requirements 2.2**
        
        Property: For any function name in the set {constructor, render, componentDidMount, 
        componentDidUpdate, componentWillUnmount, equals, hashCode, initialize, toString, 
        valueOf}, `is_likely_boilerplate` SHALL return `(True, reason)`.
        """
        is_boilerplate, reason = is_likely_boilerplate(name, file_path)
        
        assert is_boilerplate, (
            f"Framework convention method '{name}' should be classified as boilerplate\n"
            f"Got: is_boilerplate={is_boilerplate}, reason='{reason}'"
        )


class TestShortNameInUtilityDirectoryProperties:
    """Property tests for short name in utility directory classification.
    
    **Feature: balanced-architecture-filter, Property 6: Short Name in Utility Directory Classification**
    **Validates: Requirements 2.3**
    """
    
    @given(short_name(), utility_directory_path())
    @settings(max_examples=100)
    def test_short_name_in_utility_directory_classification(self, name: str, file_path: str):
        """
        **Feature: balanced-architecture-filter, Property 6: Short Name in Utility Directory Classification**
        **Validates: Requirements 2.3**
        
        Property: For any function name of 3 characters or fewer AND file path containing 
        `/utils/`, `/helpers/`, `/lib/`, or `/common/`, `is_likely_boilerplate` SHALL 
        return `(True, reason)`.
        """
        # Skip if name happens to be a common utility name (tested separately)
        if name.lower() in COMMON_UTILITY_NAMES:
            return
        
        is_boilerplate, reason = is_likely_boilerplate(name, file_path)
        
        assert is_boilerplate, (
            f"Short name '{name}' in utility directory '{file_path}' should be classified as boilerplate\n"
            f"Got: is_boilerplate={is_boilerplate}, reason='{reason}'"
        )


class TestCommonUtilityNameClassificationProperties:
    """Property tests for common utility name classification.
    
    **Feature: balanced-architecture-filter, Property 7: Common Utility Name Classification**
    **Validates: Requirements 2.4**
    """
    
    @given(common_utility_name(), st.text(max_size=100))
    @settings(max_examples=100)
    def test_common_utility_name_classification(self, name: str, file_path: str):
        """
        **Feature: balanced-architecture-filter, Property 7: Common Utility Name Classification**
        **Validates: Requirements 2.4**
        
        Property: For any function name in the set {get, set, run, add, put, pop, map, log}, 
        `is_likely_boilerplate` SHALL return `(True, reason)` regardless of file path.
        """
        is_boilerplate, reason = is_likely_boilerplate(name, file_path)
        
        assert is_boilerplate, (
            f"Common utility name '{name}' should be classified as boilerplate regardless of path\n"
            f"File path: '{file_path}'\n"
            f"Got: is_boilerplate={is_boilerplate}, reason='{reason}'"
        )


# =============================================================================
# Custom Strategies for Architectural Context Testing
# =============================================================================

# Layer keywords mapping for test generation
LAYER_KEYWORDS_FOR_TESTS = {
    "models": "models",
    "model": "models",
    "services": "services",
    "service": "services",
    "api": "api",
    "apis": "api",
    "endpoints": "api",
    "routes": "api",
    "tests": "tests",
    "test": "tests",
    "__tests__": "tests",
    "utils": "utils",
    "util": "utils",
    "utilities": "utils",
    "helpers": "utils",
    "helper": "utils",
    "lib": "utils",
    "common": "utils",
    "workers": "workers",
    "worker": "workers",
    "tasks": "workers",
    "jobs": "workers",
}


def layer_keyword() -> st.SearchStrategy[tuple[str, str]]:
    """Generate a layer keyword and its expected layer value."""
    return st.sampled_from(list(LAYER_KEYWORDS_FOR_TESTS.items()))


@st.composite
def file_path_with_layer_keyword(draw) -> tuple[str, str]:
    """Generate a file path containing a layer keyword.
    
    Returns:
        A tuple of (file_path, expected_layer)
    """
    # Get a layer keyword and its expected layer
    keyword, expected_layer = draw(layer_keyword())
    
    # Generate prefix (optional)
    prefix_parts = draw(st.lists(
        st.from_regex(r"[a-z][a-z0-9_]*", fullmatch=True).filter(lambda s: 2 <= len(s) <= 10),
        min_size=0,
        max_size=2
    ))
    
    # Generate suffix (filename)
    filename = draw(st.from_regex(r"[a-z][a-z0-9_]*", fullmatch=True).filter(lambda s: 2 <= len(s) <= 15))
    extension = draw(st.sampled_from([".py", ".js", ".ts", ".tsx", ".jsx"]))
    
    # Build the path with the keyword as a directory
    parts = prefix_parts + [keyword, filename + extension]
    file_path = "/".join(parts)
    
    return file_path, expected_layer


# Test file patterns for generation
TEST_PATTERNS_FOR_GENERATION = [
    ("test_", "prefix"),      # test_foo.py
    ("_test", "suffix"),      # foo_test.py
    (".test", "suffix"),      # foo.test.js
    (".spec", "suffix"),      # foo.spec.ts
    ("/tests/", "directory"), # tests/foo.py
    ("/__tests__/", "directory"), # __tests__/foo.js
]


@st.composite
def generate_test_file_path(draw) -> str:
    """Generate a file path that matches test file patterns.
    
    Returns:
        A file path that should be detected as a test file
    """
    # Choose a test pattern
    pattern, pattern_type = draw(st.sampled_from(TEST_PATTERNS_FOR_GENERATION))
    
    # Generate base filename
    base_name = draw(st.from_regex(r"[a-z][a-z0-9_]*", fullmatch=True).filter(lambda s: 2 <= len(s) <= 15))
    extension = draw(st.sampled_from([".py", ".js", ".ts", ".tsx", ".jsx"]))
    
    if pattern_type == "prefix":
        # test_foo.py
        filename = pattern + base_name + extension
        # Optional directory prefix
        prefix = draw(st.one_of(
            st.just(""),
            st.from_regex(r"[a-z][a-z0-9_/]*", fullmatch=True).filter(lambda s: 2 <= len(s) <= 20).map(lambda s: s + "/")
        ))
        return prefix + filename
    
    elif pattern_type == "suffix":
        # foo_test.py or foo.test.js
        if pattern.startswith("."):
            # foo.test.js - insert before extension
            filename = base_name + pattern + extension
        else:
            # foo_test.py - insert before extension
            filename = base_name + pattern + extension
        # Optional directory prefix
        prefix = draw(st.one_of(
            st.just(""),
            st.from_regex(r"[a-z][a-z0-9_/]*", fullmatch=True).filter(lambda s: 2 <= len(s) <= 20).map(lambda s: s + "/")
        ))
        return prefix + filename
    
    else:  # directory
        # /tests/foo.py or /__tests__/foo.js
        filename = base_name + extension
        # Optional prefix before the test directory
        prefix = draw(st.one_of(
            st.just(""),
            st.from_regex(r"[a-z][a-z0-9_/]*", fullmatch=True).filter(lambda s: 2 <= len(s) <= 20)
        ))
        # Build path with test directory
        if prefix:
            return prefix + pattern + filename
        else:
            return pattern.strip("/") + "/" + filename


# =============================================================================
# Property Tests for Architectural Context
# =============================================================================

class TestArchitecturalLayerDetectionProperties:
    """Property tests for architectural layer detection.
    
    **Feature: balanced-architecture-filter, Property 8: Architectural Layer Detection Consistency**
    **Validates: Requirements 3.1**
    """
    
    @given(file_path_with_layer_keyword())
    @settings(max_examples=100)
    def test_architectural_layer_detection_consistency(self, path_and_layer: tuple[str, str]):
        """
        **Feature: balanced-architecture-filter, Property 8: Architectural Layer Detection Consistency**
        **Validates: Requirements 3.1**
        
        Property: For any file path containing a layer keyword (models, services, api, 
        tests, utils, workers), `get_arch_context` SHALL return an ArchContext with 
        the corresponding layer value.
        """
        from app.services.cluster_analyzer import get_arch_context
        
        file_path, expected_layer = path_and_layer
        
        # Get architectural context
        context = get_arch_context(file_path)
        
        # Property: The detected layer should match the expected layer
        assert context.layer == expected_layer, (
            f"Layer detection mismatch for path '{file_path}'\n"
            f"Expected layer: '{expected_layer}'\n"
            f"Actual layer: '{context.layer}'"
        )


class TestTestFileDetectionProperties:
    """Property tests for test file detection.
    
    **Feature: balanced-architecture-filter, Property 9: Test File Detection**
    **Validates: Requirements 3.2**
    """
    
    @given(generate_test_file_path())
    @settings(max_examples=100)
    def test_test_file_detection(self, file_path: str):
        """
        **Feature: balanced-architecture-filter, Property 9: Test File Detection**
        **Validates: Requirements 3.2**
        
        Property: For any file path matching test patterns (test_, _test., .test., 
        .spec., /tests/, /__tests__/), `get_arch_context` SHALL return an ArchContext 
        with `is_test=True`.
        """
        from app.services.cluster_analyzer import get_arch_context
        
        # Get architectural context
        context = get_arch_context(file_path)
        
        # Property: The file should be detected as a test file
        assert context.is_test, (
            f"Test file not detected for path '{file_path}'\n"
            f"Expected is_test=True, got is_test={context.is_test}"
        )


class TestSameLayerReflexivityProperties:
    """Property tests for same layer reflexivity.
    
    **Feature: balanced-architecture-filter, Property 10: Same Layer Reflexivity**
    **Validates: Requirements 3.3**
    """
    
    @given(valid_file_path())
    @settings(max_examples=100)
    def test_same_layer_reflexivity(self, file_path: str):
        """
        **Feature: balanced-architecture-filter, Property 10: Same Layer Reflexivity**
        **Validates: Requirements 3.3**
        
        Property: For any file path P, `same_layer(P, P)` SHALL return True.
        """
        from app.services.cluster_analyzer import same_layer
        
        # Property: A file is always in the same layer as itself
        result = same_layer(file_path, file_path)
        
        assert result, (
            f"same_layer reflexivity violated for path '{file_path}'\n"
            f"Expected same_layer(P, P) = True, got {result}"
        )


# =============================================================================
# Custom Strategies for Test File Evaluation Testing
# =============================================================================

def base_name_for_test() -> st.SearchStrategy[str]:
    """Generate valid base names for test files."""
    return st.from_regex(r"[A-Za-z][A-Za-z0-9_]*", fullmatch=True).filter(
        lambda s: 2 <= len(s) <= 20
    )


@st.composite
def generate_test_file_path_with_base_name(draw) -> tuple[str, str]:
    """Generate a test file path with known base name.
    
    Returns:
        A tuple of (test_file_path, expected_base_name)
    """
    # Generate a base name
    base_name = draw(base_name_for_test())
    
    # Choose a test pattern to apply
    pattern_type = draw(st.sampled_from([
        "prefix_test_",      # test_foo.py
        "prefix_Test",       # Testfoo.py (less common but valid)
        "suffix__test",      # foo_test.py
        "suffix_.test",      # foo.test.js
        "suffix__spec",      # foo_spec.py
        "suffix_.spec",      # foo.spec.ts
        "suffix_Test",       # fooTest.py
        "suffix_Spec",       # fooSpec.ts
    ]))
    
    # Choose an extension
    extension = draw(st.sampled_from([".py", ".js", ".ts", ".tsx", ".jsx"]))
    
    # Build the filename based on pattern
    if pattern_type == "prefix_test_":
        filename = f"test_{base_name}{extension}"
    elif pattern_type == "prefix_Test":
        filename = f"Test{base_name}{extension}"
    elif pattern_type == "suffix__test":
        filename = f"{base_name}_test{extension}"
    elif pattern_type == "suffix_.test":
        filename = f"{base_name}.test{extension}"
    elif pattern_type == "suffix__spec":
        filename = f"{base_name}_spec{extension}"
    elif pattern_type == "suffix_.spec":
        filename = f"{base_name}.spec{extension}"
    elif pattern_type == "suffix_Test":
        filename = f"{base_name}Test{extension}"
    elif pattern_type == "suffix_Spec":
        filename = f"{base_name}Spec{extension}"
    else:
        filename = f"test_{base_name}{extension}"
    
    # Optionally add a directory prefix
    prefix = draw(st.one_of(
        st.just(""),
        st.from_regex(r"[a-z][a-z0-9_/]*", fullmatch=True).filter(
            lambda s: 2 <= len(s) <= 30
        ).map(lambda s: s + "/")
    ))
    
    file_path = prefix + filename
    return file_path, base_name


# =============================================================================
# Property Tests for Test File Evaluation
# =============================================================================

class TestTestBaseNameExtractionProperties:
    """Property tests for test base name extraction.
    
    **Feature: balanced-architecture-filter, Property 11: Test Base Name Extraction**
    **Validates: Requirements 4.1**
    """
    
    @given(generate_test_file_path_with_base_name())
    @settings(max_examples=100)
    def test_test_base_name_extraction(self, path_and_base: tuple[str, str]):
        """
        **Feature: balanced-architecture-filter, Property 11: Test Base Name Extraction**
        **Validates: Requirements 4.1**
        
        Property: For any test file path with prefixes (test_, Test) or suffixes 
        (_test, .test, _spec, .spec), `get_test_base_name` SHALL return the base 
        name with all test markers removed.
        """
        from app.services.cluster_analyzer import get_test_base_name
        
        file_path, expected_base = path_and_base
        
        # Extract the base name
        actual_base = get_test_base_name(file_path)
        
        # Property: The extracted base name should match the expected base name
        assert actual_base == expected_base, (
            f"Base name extraction mismatch for path '{file_path}'\n"
            f"Expected base: '{expected_base}'\n"
            f"Actual base: '{actual_base}'"
        )


# =============================================================================
# Custom Strategies for Confidence Scoring Testing
# =============================================================================

@st.composite
def outlier_payload(draw) -> dict:
    """Generate a valid outlier payload for testing."""
    file_path = draw(valid_file_path())
    name = draw(st.one_of(
        # Regular function names
        st.from_regex(r"[a-z][a-z0-9_]*", fullmatch=True).filter(lambda s: 2 <= len(s) <= 30),
        # Dunder methods
        dunder_method_name(),
        # Framework conventions
        framework_convention_name(),
        # Common utility names
        common_utility_name(),
    ))
    chunk_type = draw(st.sampled_from(["function", "class", "method"]))
    
    return {
        "file_path": file_path,
        "name": name,
        "chunk_type": chunk_type,
    }


@st.composite
def nearest_payload_or_none(draw) -> dict | None:
    """Generate a nearest neighbor payload or None."""
    if draw(st.booleans()):
        return None
    
    file_path = draw(valid_file_path())
    name = draw(st.from_regex(r"[a-z][a-z0-9_]*", fullmatch=True).filter(lambda s: 2 <= len(s) <= 30))
    chunk_type = draw(st.sampled_from(["function", "class", "method"]))
    
    return {
        "file_path": file_path,
        "name": name,
        "chunk_type": chunk_type,
    }


@st.composite
def import_analysis_data(draw) -> "ImportAnalysis":
    """Generate an ImportAnalysis object for testing."""
    from app.services.cluster_analyzer import ImportAnalysis
    
    a_imports_b = draw(st.booleans())
    b_imports_a = draw(st.booleans())
    shared_imports_count = draw(st.integers(min_value=0, max_value=20))
    # is_circular must be True only if both directions are True
    is_circular = a_imports_b and b_imports_a
    
    return ImportAnalysis(
        a_imports_b=a_imports_b,
        b_imports_a=b_imports_a,
        shared_imports_count=shared_imports_count,
        is_circular=is_circular,
    )


@st.composite
def confidence_test_scenario(draw) -> tuple[dict, dict | None, float, "ImportAnalysis"]:
    """Generate a complete scenario for confidence scoring testing.
    
    Returns:
        A tuple of (outlier_payload, nearest_payload, similarity, import_analysis)
    """
    outlier = draw(outlier_payload())
    nearest = draw(nearest_payload_or_none())
    similarity = draw(st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False))
    import_analysis = draw(import_analysis_data())
    
    return outlier, nearest, similarity, import_analysis


# =============================================================================
# Property Tests for Confidence Scoring
# =============================================================================

class TestConfidenceScoreBoundsProperties:
    """Property tests for confidence score bounds.
    
    **Feature: balanced-architecture-filter, Property 12: Confidence Score Bounds**
    **Validates: Requirements 5.6**
    """
    
    @given(confidence_test_scenario())
    @settings(max_examples=100)
    def test_confidence_score_bounds(
        self, 
        scenario: tuple[dict, dict | None, float, "ImportAnalysis"]
    ):
        """
        **Feature: balanced-architecture-filter, Property 12: Confidence Score Bounds**
        **Validates: Requirements 5.6**
        
        Property: For any outlier with any combination of factors, 
        `calculate_balanced_confidence` SHALL return a confidence value 
        in the range [0.1, 0.9].
        """
        from app.services.cluster_analyzer import calculate_balanced_confidence
        
        outlier, nearest, similarity, import_analysis = scenario
        
        # Calculate confidence
        confidence, reasons = calculate_balanced_confidence(
            outlier_payload=outlier,
            nearest_payload=nearest,
            similarity=similarity,
            import_analysis=import_analysis,
        )
        
        # Property: Confidence must be in range [0.1, 0.9]
        assert 0.1 <= confidence <= 0.9, (
            f"Confidence score {confidence} is out of bounds [0.1, 0.9]\n"
            f"Outlier: {outlier}\n"
            f"Nearest: {nearest}\n"
            f"Similarity: {similarity}\n"
            f"Import analysis: {import_analysis}\n"
            f"Reasons: {reasons}"
        )
        
        # Additional property: reasons should be a list
        assert isinstance(reasons, list), (
            f"Reasons should be a list, got {type(reasons)}"
        )
        
        # Additional property: all reasons should be strings
        for reason in reasons:
            assert isinstance(reason, str), (
                f"Each reason should be a string, got {type(reason)}: {reason}"
            )


# =============================================================================
# Custom Strategies for _find_outliers Testing
# =============================================================================

@st.composite
def generate_outlier_scenario(draw) -> tuple[np.ndarray, np.ndarray, list[dict]]:
    """Generate a scenario for _find_outliers testing.
    
    Creates vectors, labels, and payloads that simulate a clustering result
    with some outliers (label=-1) and some clustered points.
    
    Returns:
        A tuple of (vectors, labels, payloads)
    """
    # Generate between 10 and 30 points (smaller for faster tests)
    num_points = draw(st.integers(min_value=10, max_value=30))
    
    # Generate random vectors using numpy directly (much faster than hypothesis lists)
    # Use a smaller dimension (32) for testing purposes
    rng = np.random.default_rng(draw(st.integers(min_value=0, max_value=2**31)))
    vectors = rng.standard_normal((num_points, 32))
    # Normalize vectors
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms = np.maximum(norms, 1e-10)  # Avoid division by zero
    vectors = vectors / norms
    
    # Generate labels with some outliers (-1) and some clusters (0, 1, 2, ...)
    # Ensure at least some outliers and some non-outliers
    num_outliers = draw(st.integers(min_value=1, max_value=max(1, num_points // 3)))
    num_clustered = num_points - num_outliers
    
    # Create labels: -1 for outliers, 0-2 for clusters
    outlier_labels = [-1] * num_outliers
    cluster_labels = [rng.integers(0, 3) for _ in range(num_clustered)]
    labels = outlier_labels + cluster_labels
    rng.shuffle(labels)
    labels = np.array(labels)
    
    # Pre-defined file paths and names for faster generation
    file_paths = [
        "app/services/user.py", "app/models/user.py", "app/api/routes.py",
        "src/utils/helpers.js", "src/components/Button.tsx", "lib/common/utils.ts",
        "tests/test_user.py", "app/workers/tasks.py", "app/core/config.py",
        "src/hooks/useAuth.ts", "app/schemas/user.py", "src/pages/Home.tsx",
    ]
    names = [
        "process_data", "validate_input", "calculate_score", "render_component",
        "fetch_user", "update_record", "handle_request", "parse_response",
        "__init__", "__repr__", "constructor", "render", "toString",
        "get", "set", "run", "add", "UserFactory", "DataAdapter",
    ]
    chunk_types = ["function", "class", "method"]
    
    # Generate payloads for each point
    payloads = []
    for i in range(num_points):
        file_path = file_paths[rng.integers(0, len(file_paths))]
        name = names[rng.integers(0, len(names))]
        chunk_type = chunk_types[rng.integers(0, len(chunk_types))]
        language = "python" if file_path.endswith(".py") else "javascript"
        
        payloads.append({
            "file_path": file_path,
            "name": name,
            "chunk_type": chunk_type,
            "language": language,
            "content": "",  # Empty content for simplicity
        })
    
    return vectors, labels, payloads


# =============================================================================
# Property Tests for _find_outliers Method
# =============================================================================

class TestLowConfidenceFilteringProperties:
    """Property tests for low confidence filtering.
    
    **Feature: balanced-architecture-filter, Property 13: Low Confidence Filtering**
    **Validates: Requirements 5.7**
    """
    
    @given(generate_outlier_scenario())
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.large_base_example])
    def test_low_confidence_filtering(
        self, 
        scenario: tuple[np.ndarray, np.ndarray, list[dict]]
    ):
        """
        **Feature: balanced-architecture-filter, Property 13: Low Confidence Filtering**
        **Validates: Requirements 5.7**
        
        Property: For any outlier where `calculate_balanced_confidence` returns 
        confidence < 0.4, the outlier SHALL NOT appear in the final `_find_outliers` 
        result list.
        """
        from app.services.cluster_analyzer import ClusterAnalyzer
        
        vectors, labels, payloads = scenario
        
        # Create analyzer and find outliers
        analyzer = ClusterAnalyzer(qdrant_client=None)
        outliers = analyzer._find_outliers(vectors, labels, payloads)
        
        # Property: All returned outliers must have confidence >= 0.4
        for outlier in outliers:
            assert outlier.confidence >= 0.4, (
                f"Outlier with confidence {outlier.confidence} should have been filtered\n"
                f"File: {outlier.file_path}\n"
                f"Chunk: {outlier.chunk_name}\n"
                f"Factors: {outlier.confidence_factors}"
            )


class TestTierAssignmentConsistencyProperties:
    """Property tests for tier assignment consistency.
    
    **Feature: balanced-architecture-filter, Property 14: Tier Assignment Consistency**
    **Validates: Requirements 6.1, 6.2, 6.3**
    """
    
    @given(generate_outlier_scenario())
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.large_base_example])
    def test_tier_assignment_consistency(
        self, 
        scenario: tuple[np.ndarray, np.ndarray, list[dict]]
    ):
        """
        **Feature: balanced-architecture-filter, Property 14: Tier Assignment Consistency**
        **Validates: Requirements 6.1, 6.2, 6.3**
        
        Property: For any outlier in the result list:
        - If confidence >= 0.7, tier SHALL be "critical"
        - If 0.5 <= confidence < 0.7, tier SHALL be "recommended"
        - If 0.4 <= confidence < 0.5, tier SHALL be "informational"
        """
        from app.services.cluster_analyzer import ClusterAnalyzer
        
        vectors, labels, payloads = scenario
        
        # Create analyzer and find outliers
        analyzer = ClusterAnalyzer(qdrant_client=None)
        outliers = analyzer._find_outliers(vectors, labels, payloads)
        
        # Property: Tier must match confidence thresholds
        for outlier in outliers:
            confidence = outlier.confidence
            tier = outlier.tier
            
            if confidence >= 0.7:
                expected_tier = "critical"
            elif confidence >= 0.5:
                expected_tier = "recommended"
            else:
                expected_tier = "informational"
            
            assert tier == expected_tier, (
                f"Tier mismatch for confidence {confidence}\n"
                f"Expected tier: '{expected_tier}'\n"
                f"Actual tier: '{tier}'\n"
                f"File: {outlier.file_path}\n"
                f"Chunk: {outlier.chunk_name}"
            )


class TestResultOrderingProperties:
    """Property tests for result ordering.
    
    **Feature: balanced-architecture-filter, Property 15: Result Ordering**
    **Validates: Requirements 6.4**
    """
    
    @given(generate_outlier_scenario())
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.large_base_example])
    def test_result_ordering(
        self, 
        scenario: tuple[np.ndarray, np.ndarray, list[dict]]
    ):
        """
        **Feature: balanced-architecture-filter, Property 15: Result Ordering**
        **Validates: Requirements 6.4**
        
        Property: For any result list from `_find_outliers`, for all consecutive 
        pairs (outlier[i], outlier[i+1]), outlier[i].confidence >= outlier[i+1].confidence.
        """
        from app.services.cluster_analyzer import ClusterAnalyzer
        
        vectors, labels, payloads = scenario
        
        # Create analyzer and find outliers
        analyzer = ClusterAnalyzer(qdrant_client=None)
        outliers = analyzer._find_outliers(vectors, labels, payloads)
        
        # Property: Results must be sorted by confidence descending
        for i in range(len(outliers) - 1):
            current = outliers[i]
            next_outlier = outliers[i + 1]
            
            assert current.confidence >= next_outlier.confidence, (
                f"Results not sorted by confidence descending\n"
                f"outliers[{i}].confidence = {current.confidence}\n"
                f"outliers[{i+1}].confidence = {next_outlier.confidence}\n"
                f"outliers[{i}]: {current.file_path} - {current.chunk_name}\n"
                f"outliers[{i+1}]: {next_outlier.file_path} - {next_outlier.chunk_name}"
            )


class TestResultSizeLimitProperties:
    """Property tests for result size limit.
    
    **Feature: balanced-architecture-filter, Property 16: Result Size Limit**
    **Validates: Requirements 6.5**
    """
    
    @given(generate_outlier_scenario())
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.large_base_example])
    def test_result_size_limit(
        self, 
        scenario: tuple[np.ndarray, np.ndarray, list[dict]]
    ):
        """
        **Feature: balanced-architecture-filter, Property 16: Result Size Limit**
        **Validates: Requirements 6.5**
        
        Property: For any result list from `_find_outliers`, len(result) <= 15.
        """
        from app.services.cluster_analyzer import ClusterAnalyzer
        
        vectors, labels, payloads = scenario
        
        # Create analyzer and find outliers
        analyzer = ClusterAnalyzer(qdrant_client=None)
        outliers = analyzer._find_outliers(vectors, labels, payloads)
        
        # Property: Result size must be <= 15
        assert len(outliers) <= 15, (
            f"Result size {len(outliers)} exceeds limit of 15"
        )


# =============================================================================
# Property Tests for API Response Completeness
# =============================================================================

class TestAPIResponseCompletenessProperties:
    """Property tests for API response completeness.
    
    **Feature: balanced-architecture-filter, Property 17: API Response Completeness**
    **Validates: Requirements 8.1, 8.2, 8.3**
    """
    
    def test_outlier_info_response_has_confidence_field(self):
        """
        **Feature: balanced-architecture-filter, Property 17: API Response Completeness**
        **Validates: Requirements 8.1**
        
        Property: OutlierInfoResponse SHALL have a `confidence` field of type float.
        """
        from app.api.v1.semantic import OutlierInfoResponse
        
        # Check that the model has the confidence field
        assert "confidence" in OutlierInfoResponse.model_fields, (
            "OutlierInfoResponse must have a 'confidence' field"
        )
        
        # Create an instance and verify the field works
        response = OutlierInfoResponse(
            file_path="test.py",
            chunk_name="test_func",
            chunk_type="function",
            nearest_similarity=0.5,
            nearest_file="other.py",
            suggestion="Test suggestion",
            confidence=0.75,
            confidence_factors=["factor1"],
            tier="recommended",
        )
        
        assert response.confidence == 0.75, (
            f"Confidence field should be 0.75, got {response.confidence}"
        )
        assert isinstance(response.confidence, float), (
            f"Confidence should be float, got {type(response.confidence)}"
        )
    
    def test_outlier_info_response_has_confidence_factors_field(self):
        """
        **Feature: balanced-architecture-filter, Property 17: API Response Completeness**
        **Validates: Requirements 8.2**
        
        Property: OutlierInfoResponse SHALL have a `confidence_factors` field of type list[str].
        """
        from app.api.v1.semantic import OutlierInfoResponse
        
        # Check that the model has the confidence_factors field
        assert "confidence_factors" in OutlierInfoResponse.model_fields, (
            "OutlierInfoResponse must have a 'confidence_factors' field"
        )
        
        # Create an instance and verify the field works
        factors = ["Boilerplate: Python dunder method", "Different architectural layer"]
        response = OutlierInfoResponse(
            file_path="test.py",
            chunk_name="test_func",
            chunk_type="function",
            nearest_similarity=0.5,
            nearest_file="other.py",
            suggestion="Test suggestion",
            confidence=0.75,
            confidence_factors=factors,
            tier="recommended",
        )
        
        assert response.confidence_factors == factors, (
            f"Confidence factors should be {factors}, got {response.confidence_factors}"
        )
        assert isinstance(response.confidence_factors, list), (
            f"Confidence factors should be list, got {type(response.confidence_factors)}"
        )
    
    def test_outlier_info_response_has_tier_field(self):
        """
        **Feature: balanced-architecture-filter, Property 17: API Response Completeness**
        **Validates: Requirements 8.3**
        
        Property: OutlierInfoResponse SHALL have a `tier` field of type str.
        """
        from app.api.v1.semantic import OutlierInfoResponse
        
        # Check that the model has the tier field
        assert "tier" in OutlierInfoResponse.model_fields, (
            "OutlierInfoResponse must have a 'tier' field"
        )
        
        # Test all valid tier values
        for tier_value in ["critical", "recommended", "informational"]:
            response = OutlierInfoResponse(
                file_path="test.py",
                chunk_name="test_func",
                chunk_type="function",
                nearest_similarity=0.5,
                nearest_file="other.py",
                suggestion="Test suggestion",
                confidence=0.75,
                confidence_factors=[],
                tier=tier_value,
            )
            
            assert response.tier == tier_value, (
                f"Tier should be '{tier_value}', got '{response.tier}'"
            )
            assert isinstance(response.tier, str), (
                f"Tier should be str, got {type(response.tier)}"
            )
    
    def test_outlier_info_response_default_values(self):
        """
        **Feature: balanced-architecture-filter, Property 17: API Response Completeness**
        **Validates: Requirements 8.1, 8.2, 8.3**
        
        Property: OutlierInfoResponse SHALL have sensible default values for new fields.
        """
        from app.api.v1.semantic import OutlierInfoResponse
        
        # Create an instance with only required fields (testing defaults)
        response = OutlierInfoResponse(
            file_path="test.py",
            chunk_name="test_func",
            chunk_type="function",
            nearest_similarity=0.5,
            nearest_file="other.py",
            suggestion="Test suggestion",
        )
        
        # Check default values
        assert response.confidence == 0.5, (
            f"Default confidence should be 0.5, got {response.confidence}"
        )
        assert response.confidence_factors == [], (
            f"Default confidence_factors should be [], got {response.confidence_factors}"
        )
        assert response.tier == "recommended", (
            f"Default tier should be 'recommended', got {response.tier}"
        )
