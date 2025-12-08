"""Cluster Analyzer Service for Semantic Architecture Analysis.

Uses HDBSCAN clustering on code embeddings to:
- Detect natural module boundaries
- Find outliers (dead/misplaced code)
- Identify coupling hotspots (god files)
- Calculate cohesion metrics
"""

import logging
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
from qdrant_client import QdrantClient
from sklearn.cluster import HDBSCAN
from sklearn.metrics.pairwise import cosine_distances

from app.core.config import settings
from app.schemas.architecture_llm import (
    ArchitectureSummary,
    DeadCodeFinding,
    HotSpotFinding,
    LLMReadyArchitectureData,
)
from app.services.call_graph_analyzer import get_call_graph_analyzer
from app.services.coverage_analyzer import CoverageAnalyzer
from app.services.git_analyzer import GitAnalyzer

logger = logging.getLogger(__name__)

COLLECTION_NAME = "code_embeddings"

# Regex patterns for import extraction
# Python: from X import Y, import X
PYTHON_FROM_IMPORT_PATTERN = re.compile(r"^\s*from\s+([\w.]+)\s+import", re.MULTILINE)
PYTHON_IMPORT_PATTERN = re.compile(r"^\s*import\s+([\w.]+)", re.MULTILINE)

# JavaScript/TypeScript: import X from 'Y', require('Y')
JS_IMPORT_FROM_PATTERN = re.compile(r"""import\s+.*?\s+from\s+['"]([^'"]+)['"]""", re.MULTILINE)
JS_REQUIRE_PATTERN = re.compile(r"""require\s*\(\s*['"]([^'"]+)['"]\s*\)""", re.MULTILINE)


@dataclass
class ImportAnalysis:
    """Structured import relationship analysis between two files."""
    a_imports_b: bool
    b_imports_a: bool
    shared_imports_count: int
    is_circular: bool


@dataclass
class ArchContext:
    """Simple architectural context for a file.

    Attributes:
        directory: Parent directory path
        filename: File name
        layer: Detected architectural layer (models, services, api, tests, utils, workers, unknown)
        is_test: Whether file is a test file
    """
    directory: str
    filename: str
    layer: str
    is_test: bool


# =============================================================================
# Boilerplate Detection Constants
# =============================================================================

# Framework convention methods that are typically boilerplate
FRAMEWORK_CONVENTIONS = frozenset({
    "constructor",
    "render",
    "componentdidmount",
    "componentdidupdate",
    "componentwillunmount",
    "equals",
    "hashcode",
    "initialize",
    "tostring",
    "valueof",
    "setup",
    "teardown",
    "dispose",
    "destroy",
    "init",
    "configure",
    "getstate",
    "setstate",
    "shouldcomponentupdate",
    "getderivedstatefromprops",
    "getsnapshotbeforeupdate",
    "componentdidcatch",
    "clone",
    "copy",
    "compareto",
    "finalize",
})

# Common utility function names that are typically boilerplate
COMMON_UTILITY_NAMES = frozenset({
    "get",
    "set",
    "run",
    "add",
    "put",
    "pop",
    "map",
    "log",
})

# Utility directory patterns
UTILITY_DIR_PATTERNS = ("/utils/", "/helpers/", "/lib/", "/common/")

# Architectural pattern suffixes
ARCHITECTURAL_SUFFIXES = (
    "Factory",
    "Adapter",
    "Middleware",
    "Provider",
    "Interceptor",
)


# =============================================================================
# Architectural Context Constants
# =============================================================================

# Layer keywords for architectural layer detection
LAYER_KEYWORDS = {
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

# Test file patterns for detection
TEST_FILE_PATTERNS = (
    "test_",       # Python: test_foo.py
    "_test.",      # Python: foo_test.py
    ".test.",      # JS/TS: foo.test.js
    ".spec.",      # JS/TS: foo.spec.ts
    "/tests/",     # Directory: /path/tests/foo.py
    "/__tests__/", # JS convention: __tests__/foo.js
    "tests/",      # Directory at start: tests/foo.py
    "__tests__/",  # JS convention at start: __tests__/foo.js
)


def get_arch_context(file_path: str) -> ArchContext:
    """Get architectural context for a file.

    Detects:
    - Architectural layer from path keywords (models, services, api, tests, utils, workers)
    - Test file status from patterns (test_, _test., .test., .spec., /tests/, /__tests__/)

    Args:
        file_path: The file path to analyze

    Returns:
        ArchContext with directory, filename, layer, and is_test fields
    """
    if not file_path:
        return ArchContext(
            directory="",
            filename="",
            layer="unknown",
            is_test=False,
        )

    # Normalize path separators
    normalized_path = file_path.replace("\\", "/")

    # Extract directory and filename
    if "/" in normalized_path:
        directory = normalized_path.rsplit("/", 1)[0]
        filename = normalized_path.rsplit("/", 1)[1]
    else:
        directory = ""
        filename = normalized_path

    # Detect if it's a test file
    path_lower = normalized_path.lower()
    filename_lower = filename.lower()
    is_test = any(
        pattern in path_lower or pattern in filename_lower
        for pattern in TEST_FILE_PATTERNS
    )

    # Detect architectural layer from path keywords
    layer = "unknown"
    path_parts = normalized_path.lower().split("/")

    # Check each path part for layer keywords
    for part in path_parts:
        if part in LAYER_KEYWORDS:
            layer = LAYER_KEYWORDS[part]
            break

    return ArchContext(
        directory=directory,
        filename=filename,
        layer=layer,
        is_test=is_test,
    )


def same_layer(file_a: str, file_b: str) -> bool:
    """Check if two files are in the same architectural layer.

    Compares:
    - Directory paths for exact match
    - Detected layer types if both are known

    Args:
        file_a: Path to the first file
        file_b: Path to the second file

    Returns:
        True if files are in the same layer, False otherwise
    """
    if not file_a or not file_b:
        return False

    ctx_a = get_arch_context(file_a)
    ctx_b = get_arch_context(file_b)

    # Same file is always in the same layer (reflexivity)
    if file_a == file_b:
        return True

    # Check for exact directory match
    if ctx_a.directory and ctx_a.directory == ctx_b.directory:
        return True

    # Check for same known layer type
    if ctx_a.layer != "unknown" and ctx_b.layer != "unknown":
        return ctx_a.layer == ctx_b.layer

    return False


# =============================================================================
# Test File Evaluation Constants
# =============================================================================

# Test prefixes to remove
TEST_PREFIXES = ("test_", "Test")

# Test suffixes to remove (before extension)
TEST_SUFFIXES = ("_test", ".test", "_spec", ".spec", "Test", "Spec")


def get_test_base_name(file_path: str) -> str:
    """Extract base name from test file path by removing test markers.

    Removes:
    - Test prefixes: test_, Test
    - Test suffixes: _test, .test, _spec, .spec, Test, Spec
    - File extensions before processing

    Args:
        file_path: The test file path to process

    Returns:
        The base name with all test markers removed

    Examples:
        >>> get_test_base_name("tests/test_user.py")
        'user'
        >>> get_test_base_name("src/UserTest.ts")
        'User'
        >>> get_test_base_name("components/Button.spec.tsx")
        'Button'
    """
    if not file_path:
        return ""

    # Normalize path separators and get filename
    normalized_path = file_path.replace("\\", "/")
    if "/" in normalized_path:
        filename = normalized_path.rsplit("/", 1)[1]
    else:
        filename = normalized_path

    # Remove file extension
    # Handle double extensions like .spec.ts, .test.js
    base = filename
    for ext in (".tsx", ".jsx", ".ts", ".js", ".py", ".mjs", ".cjs"):
        if base.endswith(ext):
            base = base[:-len(ext)]
            break

    # Remove test suffixes (check longer ones first to avoid partial matches)
    # Sort by length descending to match longer suffixes first
    for suffix in sorted(TEST_SUFFIXES, key=len, reverse=True):
        if base.endswith(suffix):
            base = base[:-len(suffix)]
            break

    # Remove test prefixes
    for prefix in TEST_PREFIXES:
        if base.startswith(prefix):
            base = base[len(prefix):]
            break

    return base


def evaluate_test_relationship(
    outlier_path: str,
    nearest_path: str,
    similarity: float,
) -> tuple[float, str]:
    """Evaluate test file relationships and return confidence adjustment.

    Evaluates:
    - Colocated tests: base names match -> -0.4 adjustment
    - Tests similar to unrelated code: similarity > 0.7 -> +0.1 adjustment
    - Orphaned tests: similarity < 0.4 -> +0.2 adjustment

    Args:
        outlier_path: Path to the outlier (test) file
        nearest_path: Path to the nearest neighbor file
        similarity: Similarity score between outlier and nearest neighbor

    Returns:
        A tuple of (confidence_adjustment, reason)
    """
    if not outlier_path:
        return 0.0, ""

    # Check if outlier is a test file
    outlier_ctx = get_arch_context(outlier_path)
    if not outlier_ctx.is_test:
        return 0.0, ""

    # Get base names for comparison
    outlier_base = get_test_base_name(outlier_path)

    # Get nearest file's base name (without test markers if it's also a test)
    if nearest_path:
        nearest_ctx = get_arch_context(nearest_path)
        if nearest_ctx.is_test:
            nearest_base = get_test_base_name(nearest_path)
        else:
            # For non-test files, just get the filename without extension
            normalized = nearest_path.replace("\\", "/")
            if "/" in normalized:
                nearest_base = normalized.rsplit("/", 1)[1]
            else:
                nearest_base = normalized
            # Remove extension
            for ext in (".tsx", ".jsx", ".ts", ".js", ".py", ".mjs", ".cjs"):
                if nearest_base.endswith(ext):
                    nearest_base = nearest_base[:-len(ext)]
                    break
    else:
        nearest_base = ""

    # Check for colocated test (base names match)
    if outlier_base and nearest_base and outlier_base.lower() == nearest_base.lower():
        return -0.4, "Test file correctly colocated with subject"

    # Check for orphaned test (very low similarity)
    if similarity < 0.4:
        return 0.2, "Test file may be orphaned"

    # Check for test similar to unrelated code (high similarity but not colocated)
    if similarity > 0.7:
        return 0.1, "Test file similar to unrelated code"

    return 0.0, ""


def calculate_balanced_confidence(
    outlier_payload: dict,
    nearest_payload: dict | None,
    similarity: float,
    import_analysis: ImportAnalysis,
) -> tuple[float, list[str]]:
    """Calculate confidence score with reasons for an outlier.

    Starts with a neutral score of 0.5 and applies adjustments based on:
    - Boilerplate detection (-0.35)
    - Import relationship (-0.30)
    - Cross-layer penalty (-0.15)
    - Test relationship adjustments (varies)
    - Isolation boost (+0.30 for similarity < 0.25)
    - High similarity same layer boost (+0.25)
    - Circular import boost (+0.20)
    - Shared imports boost (+0.10 for 3+ shared)

    Final score is clamped to [0.1, 0.9].

    Args:
        outlier_payload: Metadata for the outlier chunk
        nearest_payload: Metadata for the nearest neighbor chunk (may be None)
        similarity: Similarity score between outlier and nearest neighbor
        import_analysis: Import relationship analysis between the files

    Returns:
        A tuple of (confidence score 0.1-0.9, list of reasons)
    """
    # Start with neutral confidence
    confidence = 0.5
    reasons: list[str] = []

    # Extract file paths and chunk info
    outlier_path = outlier_payload.get("file_path", "")
    outlier_name = outlier_payload.get("name", "")
    nearest_path = nearest_payload.get("file_path", "") if nearest_payload else ""

    # ==========================================================================
    # PENALTIES (reduce confidence - less likely to be actionable)
    # ==========================================================================

    # 1. Boilerplate penalty (-0.35)
    is_boilerplate, boilerplate_reason = is_likely_boilerplate(outlier_name, outlier_path)
    if is_boilerplate:
        confidence -= 0.35
        reasons.append(f"Boilerplate: {boilerplate_reason}")

    # 2. Import relationship penalty (-0.30)
    # If outlier already imports its nearest neighbor, it's likely intentional
    if import_analysis.a_imports_b:
        confidence -= 0.30
        reasons.append("Already imports nearest neighbor")

    # 3. Cross-layer penalty (-0.15)
    # Different architectural layers may naturally have different code patterns
    if outlier_path and nearest_path and not same_layer(outlier_path, nearest_path):
        confidence -= 0.15
        reasons.append("Different architectural layer than nearest neighbor")

    # 4. Test relationship adjustments (varies)
    test_adjustment, test_reason = evaluate_test_relationship(
        outlier_path, nearest_path, similarity
    )
    if test_adjustment != 0.0:
        confidence += test_adjustment
        reasons.append(test_reason)

    # ==========================================================================
    # BOOSTS (increase confidence - more likely to be actionable)
    # ==========================================================================

    # 5. Isolation boost (+0.30 for similarity < 0.25)
    # Very isolated code is likely orphaned/dead
    if similarity < 0.25:
        confidence += 0.30
        reasons.append("Very isolated - likely orphaned/dead code")

    # 6. High similarity same layer boost (+0.25)
    # High similarity in same layer without import = possible duplicate
    if (
        similarity > 0.8
        and not import_analysis.a_imports_b
        and outlier_path
        and nearest_path
        and same_layer(outlier_path, nearest_path)
    ):
        confidence += 0.25
        reasons.append("High similarity in same layer - possible duplicate")

    # 7. Circular import boost (+0.20)
    # Circular imports indicate architectural issues
    if import_analysis.is_circular:
        confidence += 0.20
        reasons.append("Circular import detected - architectural issue")

    # 8. Shared imports boost (+0.10 for 3+ shared)
    # Many shared imports suggest related code that should be reviewed
    if import_analysis.shared_imports_count >= 3:
        confidence += 0.10
        reasons.append(f"Shares {import_analysis.shared_imports_count} imports with nearest neighbor")

    # ==========================================================================
    # CLAMP to valid range [0.1, 0.9]
    # ==========================================================================
    confidence = max(0.1, min(0.9, confidence))

    return confidence, reasons


def is_likely_boilerplate(name: str, file_path: str) -> tuple[bool, str]:
    """Check if a function/method is likely boilerplate.

    Detects:
    - Python dunder methods (__X__ pattern)
    - Framework conventions (constructor, render, componentDidMount, etc.)
    - Short names (<=3 chars) in utility directories
    - Common utility names (get, set, run, add, put, pop, map, log)
    - Architectural pattern suffixes (Factory, Adapter, Middleware, Provider, Interceptor)

    Args:
        name: The function/method name to check
        file_path: The file path where the function is located

    Returns:
        A tuple of (is_boilerplate, reason) where reason explains the classification
    """
    if not name:
        return False, ""

    # 1. Check for Python dunder methods (__X__ pattern)
    if name.startswith("__") and name.endswith("__") and len(name) > 4:
        return True, f"Python dunder method: {name}"

    # 2. Check for framework convention methods (case-insensitive)
    name_lower = name.lower()
    if name_lower in FRAMEWORK_CONVENTIONS:
        return True, f"Framework convention method: {name}"

    # 3. Check for common utility names (regardless of directory)
    if name_lower in COMMON_UTILITY_NAMES:
        return True, f"Common utility name: {name}"

    # 4. Check for short names (<=3 chars) in utility directories
    if len(name) <= 3:
        file_path_lower = file_path.lower() if file_path else ""
        for pattern in UTILITY_DIR_PATTERNS:
            if pattern in file_path_lower:
                return True, f"Short name in utility directory: {name} in {pattern}"

    # 5. Check for architectural pattern suffixes
    for suffix in ARCHITECTURAL_SUFFIXES:
        if name.endswith(suffix):
            return True, f"Architectural pattern: {name} (ends with {suffix})"

    return False, ""


def extract_imports(content: str, language: str) -> set[str]:
    """Extract import statements from code content.

    Args:
        content: The source code content to analyze
        language: The programming language ('python', 'javascript', 'typescript')

    Returns:
        A set of module paths extracted from import statements
    """
    if not content:
        return set()

    imports: set[str] = set()
    language_lower = language.lower() if language else ""

    if language_lower == "python":
        # Extract from 'from X import Y' statements
        for match in PYTHON_FROM_IMPORT_PATTERN.finditer(content):
            imports.add(match.group(1))

        # Extract from 'import X' statements
        for match in PYTHON_IMPORT_PATTERN.finditer(content):
            imports.add(match.group(1))

    elif language_lower in ("javascript", "typescript", "js", "ts"):
        # Extract from 'import X from "Y"' statements
        for match in JS_IMPORT_FROM_PATTERN.finditer(content):
            imports.add(match.group(1))

        # Extract from 'require("Y")' statements
        for match in JS_REQUIRE_PATTERN.finditer(content):
            imports.add(match.group(1))

    return imports


def to_module_path(file_path: str) -> str:
    """Convert a file path to a module path for import matching.

    Args:
        file_path: The file path to convert (e.g., 'app/services/cluster_analyzer.py')

    Returns:
        The module path (e.g., 'app.services.cluster_analyzer')
    """
    if not file_path:
        return ""

    # Remove file extension
    path = file_path
    for ext in (".py", ".js", ".ts", ".jsx", ".tsx", ".mjs", ".cjs"):
        if path.endswith(ext):
            path = path[:-len(ext)]
            break

    # Remove index suffix (common in JS/TS)
    if path.endswith("/index") or path.endswith("\\index"):
        path = path[:-6]

    # Convert path separators to dots
    module_path = path.replace("/", ".").replace("\\", ".")

    # Remove leading dots
    module_path = module_path.lstrip(".")

    return module_path


def analyze_import_relationship(
    file_a: str,
    file_b: str,
    import_graph: dict[str, set[str]],
) -> ImportAnalysis:
    """Analyze import relationship between two files.

    Args:
        file_a: Path to the first file
        file_b: Path to the second file
        import_graph: Mapping of file paths to their import statements

    Returns:
        ImportAnalysis with relationship details
    """
    # Get imports for each file
    imports_a = import_graph.get(file_a, set())
    imports_b = import_graph.get(file_b, set())

    # Convert file paths to module paths for comparison
    module_b = to_module_path(file_b)
    module_a = to_module_path(file_a)

    # Also get the filename without extension for partial matching
    filename_b = file_b.rsplit("/", 1)[-1].rsplit(".", 1)[0] if file_b else ""
    filename_a = file_a.rsplit("/", 1)[-1].rsplit(".", 1)[0] if file_a else ""

    # Check if file A imports file B
    a_imports_b = False
    if imports_a:
        for imp in imports_a:
            # Check for exact module path match
            if module_b and (imp == module_b or imp.endswith("." + module_b) or module_b.endswith("." + imp)):
                a_imports_b = True
                break
            # Check for filename match (common in relative imports)
            if filename_b and (imp == filename_b or imp.endswith("/" + filename_b) or imp.endswith("." + filename_b)):
                a_imports_b = True
                break

    # Check if file B imports file A
    b_imports_a = False
    if imports_b:
        for imp in imports_b:
            # Check for exact module path match
            if module_a and (imp == module_a or imp.endswith("." + module_a) or module_a.endswith("." + imp)):
                b_imports_a = True
                break
            # Check for filename match (common in relative imports)
            if filename_a and (imp == filename_a or imp.endswith("/" + filename_a) or imp.endswith("." + filename_a)):
                b_imports_a = True
                break

    # Calculate shared imports
    shared_imports_count = len(imports_a & imports_b) if imports_a and imports_b else 0

    # Detect circular imports
    is_circular = a_imports_b and b_imports_a

    return ImportAnalysis(
        a_imports_b=a_imports_b,
        b_imports_a=b_imports_a,
        shared_imports_count=shared_imports_count,
        is_circular=is_circular,
    )


@dataclass
class ClusterInfo:
    """Information about a detected cluster."""
    id: int
    name: str  # Auto-generated from file paths
    file_count: int
    chunk_count: int
    cohesion: float  # 0-1, higher = more related
    top_files: list[str] = field(default_factory=list)
    dominant_language: str | None = None
    status: str = "healthy"  # healthy, moderate, scattered


@dataclass
class OutlierInfo:
    """Information about an outlier (potential dead/misplaced code).

    Attributes:
        file_path: Path to the outlier file
        chunk_name: Name of the code chunk (function, class, etc.)
        chunk_type: Type of the chunk (function, class, method)
        nearest_similarity: Similarity score to nearest neighbor (0-1)
        nearest_file: Path to the nearest neighbor file
        suggestion: Human-readable suggestion for action
        confidence: Confidence score (0.1-0.9) indicating how actionable the outlier is
        confidence_factors: List of reasons explaining the confidence score
        tier: Classification tier (critical, recommended, informational)
    """
    file_path: str
    chunk_name: str | None
    chunk_type: str | None
    nearest_similarity: float
    nearest_file: str | None
    suggestion: str
    confidence: float = 0.5
    confidence_factors: list[str] = field(default_factory=list)
    tier: str = "recommended"


@dataclass
class CouplingHotspot:
    """A file that bridges multiple clusters."""
    file_path: str
    clusters_connected: int
    cluster_names: list[str]
    suggestion: str


@dataclass
class SimilarCodeGroup:
    """A group of similar code chunks."""
    similarity: float
    suggestion: str
    chunks: list[dict]  # [{file, name, lines, chunk_type}, ...]


@dataclass
class SimilarCodeResult:
    """Result of similar code detection."""
    groups: list[SimilarCodeGroup]
    total_groups: int
    potential_loc_reduction: int


@dataclass
class ArchitectureHealth:
    """Complete architecture health analysis."""
    overall_score: int  # 0-100
    clusters: list[ClusterInfo]
    outliers: list[OutlierInfo]
    coupling_hotspots: list[CouplingHotspot]
    similar_code: SimilarCodeResult | None  # Similar code groups
    total_chunks: int
    total_files: int
    metrics: dict = field(default_factory=dict)

    def to_cacheable_dict(self) -> dict:
        """Convert to JSON-serializable dict for PostgreSQL storage.

        Ensures all values are JSON-serializable:
        - Converts dataclasses to dicts
        - Converts numpy types to Python native types
        - Adds computed_at timestamp in ISO format

        Returns:
            JSON-serializable dict suitable for JSONB storage
        """
        def convert_value(val):
            """Recursively convert values to JSON-serializable types."""
            if isinstance(val, np.integer):
                return int(val)
            elif isinstance(val, np.floating):
                return float(val)
            elif isinstance(val, np.ndarray):
                return val.tolist()
            elif isinstance(val, dict):
                return {k: convert_value(v) for k, v in val.items()}
            elif isinstance(val, list):
                return [convert_value(item) for item in val]
            return val

        # Convert similar code to cacheable format
        similar_code_data = None
        if self.similar_code:
            similar_code_data = {
                "groups": [
                    {
                        "similarity": float(g.similarity),
                        "suggestion": g.suggestion,
                        "chunks": g.chunks,
                    }
                    for g in self.similar_code.groups
                ],
                "total_groups": int(self.similar_code.total_groups),
                "potential_loc_reduction": int(self.similar_code.potential_loc_reduction),
            }

        return {
            "architecture_health": {
                "overall_score": int(self.overall_score),
                "score": int(self.overall_score),  # Keep for backward compatibility
                "total_chunks": int(self.total_chunks),
                "total_files": int(self.total_files),
                "clusters": [
                    {
                        "id": int(c.id),
                        "name": c.name,
                        "file_count": int(c.file_count),
                        "chunk_count": int(c.chunk_count),
                        "cohesion": float(c.cohesion),
                        "top_files": c.top_files,
                        "dominant_language": c.dominant_language,
                        "status": c.status,
                    }
                    for c in self.clusters
                ],
                "outliers": [
                    {
                        "file_path": o.file_path,
                        "chunk_name": o.chunk_name,
                        "chunk_type": o.chunk_type,
                        "nearest_similarity": float(o.nearest_similarity),
                        "nearest_file": o.nearest_file,
                        "suggestion": o.suggestion,
                        "confidence": float(o.confidence),
                        "confidence_factors": o.confidence_factors,
                        "tier": o.tier,
                    }
                    for o in self.outliers
                ],
                "coupling_hotspots": [
                    {
                        "file_path": h.file_path,
                        "clusters_connected": int(h.clusters_connected),
                        "cluster_names": h.cluster_names,
                        "suggestion": h.suggestion,
                    }
                    for h in self.coupling_hotspots
                ],
                "metrics": convert_value(self.metrics),
            },
            "similar_code": similar_code_data,
            "tech_debt_hotspots": [],  # Placeholder for future tech debt analysis
            "computed_at": datetime.now(UTC).isoformat(),
        }


class ClusterAnalyzer:
    """Analyzes code architecture using vector clustering."""

    def __init__(self, qdrant_client: QdrantClient | None = None):
        self.qdrant = qdrant_client or QdrantClient(
            host=settings.qdrant_host,
            port=settings.qdrant_port,
            timeout=settings.qdrant_timeout,
        )

    async def analyze(self, repo_id: str, include_similar_code: bool = True) -> ArchitectureHealth:
        """Run full architecture analysis on a repository.

        Args:
            repo_id: Repository ID to analyze
            include_similar_code: Whether to compute similar code detection (default True)
        """
        logger.info(f"Starting cluster analysis for repo {repo_id}")

        # Fetch all vectors
        vectors, payloads = self._fetch_vectors(repo_id)

        if len(vectors) < 5:
            logger.warning(f"Not enough vectors for clustering: {len(vectors)}")
            return self._empty_health(len(vectors))

        # Run clustering
        labels = self._run_clustering(vectors)

        # Count actual outliers BEFORE truncation (for accurate scoring)
        actual_outlier_count = int(np.sum(labels == -1))

        # Analyze results
        clusters = self._analyze_clusters(vectors, labels, payloads)
        outliers = self._find_outliers(vectors, labels, payloads)  # Returns truncated list for display

        # Build cluster ID to name mapping for hotspot display
        cluster_id_to_name = {c.id: c.name for c in clusters}
        hotspots = self._find_coupling_hotspots(labels, payloads, cluster_id_to_name)

        # Find similar code (potential duplicates)
        similar_code = None
        if include_similar_code:
            similar_code = self._find_similar_code(vectors, payloads, threshold=0.85, limit=20)

        # Count unique files
        unique_files = {p.get("file_path") for p in payloads if p.get("file_path")}

        # Calculate overall score with accurate counts
        overall_score = self._calculate_overall_score(
            clusters=clusters,
            actual_outlier_count=actual_outlier_count,
            total_chunks=len(vectors),
            hotspot_count=len(hotspots),
            total_files=len(unique_files),
        )

        # Calculate weighted cohesion (larger clusters matter more)
        if clusters:
            total_in_clusters = sum(c.chunk_count for c in clusters)
            weighted_cohesion = (
                sum(c.cohesion * c.chunk_count for c in clusters) / total_in_clusters
                if total_in_clusters > 0 else 0
            )
        else:
            weighted_cohesion = 0

        return ArchitectureHealth(
            overall_score=overall_score,
            clusters=clusters,
            outliers=outliers,
            coupling_hotspots=hotspots,
            similar_code=similar_code,
            total_chunks=len(vectors),
            total_files=len(unique_files),
            metrics={
                "avg_cohesion": round(weighted_cohesion, 3),
                "outlier_percentage": round(actual_outlier_count / len(vectors) * 100, 1) if len(vectors) > 0 else 0,
                "cluster_count": len(clusters),
                "actual_outlier_count": actual_outlier_count,
                "hotspot_count": len(hotspots),
            }
        )

    def _fetch_vectors(self, repo_id: str) -> tuple[np.ndarray, list[dict]]:
        """Fetch all vectors and payloads for a repository."""
        vectors = []
        payloads = []

        # Scroll through all points
        offset = None
        while True:
            results, offset = self.qdrant.scroll(
                collection_name=COLLECTION_NAME,
                scroll_filter={
                    "must": [
                        {"key": "repository_id", "match": {"value": repo_id}}
                    ]
                },
                limit=100,
                offset=offset,
                with_vectors=True,
            )

            for point in results:
                if point.vector:
                    vectors.append(point.vector)
                    payloads.append(point.payload or {})

            if offset is None:
                break

        logger.info(f"Fetched {len(vectors)} vectors for repo {repo_id}")
        return np.array(vectors) if vectors else np.array([]), payloads

    def _run_clustering(self, vectors: np.ndarray) -> np.ndarray:
        """Run HDBSCAN clustering on vectors."""
        if len(vectors) < 5:
            return np.array([-1] * len(vectors))

        # HDBSCAN with cosine metric
        clusterer = HDBSCAN(
            min_cluster_size=max(3, len(vectors) // 20),  # At least 5% of points
            min_samples=2,
            metric="euclidean",  # Use euclidean on normalized vectors
            cluster_selection_epsilon=0.0,
        )

        # Normalize vectors for better clustering
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        normalized = vectors / np.maximum(norms, 1e-10)

        labels = clusterer.fit_predict(normalized)

        n_clusters = len(set(labels)) - (1 if -1 in labels else 0)
        n_outliers = np.sum(labels == -1)
        logger.info(f"Clustering: {n_clusters} clusters, {n_outliers} outliers")

        return labels

    def _analyze_clusters(
        self,
        vectors: np.ndarray,
        labels: np.ndarray,
        payloads: list[dict]
    ) -> list[ClusterInfo]:
        """Analyze each cluster for cohesion and naming."""
        clusters = []
        unique_labels = set(labels) - {-1}  # Exclude outliers

        for cluster_id in sorted(unique_labels):
            mask = labels == cluster_id
            cluster_vectors = vectors[mask]
            cluster_payloads = [p for p, m in zip(payloads, mask, strict=False) if m]

            # Calculate cohesion (1 - avg pairwise distance)
            if len(cluster_vectors) > 1:
                distances = cosine_distances(cluster_vectors)
                avg_distance = np.mean(distances[np.triu_indices(len(distances), k=1)])
                cohesion = 1 - avg_distance
            else:
                cohesion = 1.0

            # Get file paths and count
            file_paths = [p.get("file_path", "") for p in cluster_payloads]
            unique_files = list(set(file_paths))

            # Auto-generate cluster name from common path prefix
            name = self._generate_cluster_name(unique_files, cluster_id)

            # Get dominant language
            languages = [p.get("language") for p in cluster_payloads if p.get("language")]
            dominant_lang = max(set(languages), key=languages.count) if languages else None

            # Determine status
            if cohesion >= 0.7:
                status = "healthy"
            elif cohesion >= 0.5:
                status = "moderate"
            else:
                status = "scattered"

            clusters.append(ClusterInfo(
                id=int(cluster_id),
                name=name,
                file_count=len(unique_files),
                chunk_count=len(cluster_payloads),
                cohesion=round(cohesion, 3),
                top_files=unique_files[:5],
                dominant_language=dominant_lang,
                status=status,
            ))

        # Sort by chunk count descending
        clusters.sort(key=lambda c: c.chunk_count, reverse=True)
        return clusters

    def _generate_cluster_name(self, file_paths: list[str], cluster_id: int) -> str:
        """Generate a human-readable name for a cluster."""
        if not file_paths:
            return f"cluster_{cluster_id}"

        # Find common directory prefix
        parts_list = [p.split("/") for p in file_paths if p]
        if not parts_list:
            return f"cluster_{cluster_id}"

        # Find common prefix
        common_parts = []
        for parts in zip(*parts_list, strict=False):
            if len(set(parts)) == 1:
                common_parts.append(parts[0])
            else:
                break

        if common_parts:
            # Use the last meaningful directory
            name = common_parts[-1] if common_parts[-1] else common_parts[-2] if len(common_parts) > 1 else f"cluster_{cluster_id}"
            return name.replace("_", " ").replace("-", " ").title().replace(" ", "_").lower()

        # Fallback: use most common directory
        dirs = [p.split("/")[0] for p in file_paths if "/" in p]
        if dirs:
            return max(set(dirs), key=dirs.count)

        return f"cluster_{cluster_id}"

    def _find_outliers(
        self,
        vectors: np.ndarray,
        labels: np.ndarray,
        payloads: list[dict]
    ) -> list[OutlierInfo]:
        """Find outliers with balanced confidence scoring and filtering.

        Uses the balanced architecture filter to:
        - Build import graph from payloads
        - Analyze import relationships for each outlier
        - Calculate balanced confidence scores
        - Filter outliers with confidence < 0.4
        - Assign tiers based on confidence
        - Sort by confidence descending
        - Limit to 15 results
        """
        outliers = []
        outlier_mask = labels == -1

        if not np.any(outlier_mask):
            return outliers

        # Build import graph from payloads
        import_graph = self._build_import_graph(payloads)

        # For each outlier, find nearest non-outlier
        non_outlier_mask = labels != -1
        non_outlier_vectors = vectors[non_outlier_mask]
        non_outlier_payloads = [p for p, m in zip(payloads, non_outlier_mask, strict=False) if m]

        for _i, (is_outlier, vector, payload) in enumerate(zip(outlier_mask, vectors, payloads, strict=False)):
            if not is_outlier:
                continue

            # Find nearest neighbor
            nearest_payload = None
            if len(non_outlier_vectors) > 0:
                distances = cosine_distances([vector], non_outlier_vectors)[0]
                nearest_idx = np.argmin(distances)
                nearest_similarity = 1 - distances[nearest_idx]
                nearest_payload = non_outlier_payloads[nearest_idx]
                nearest_file = nearest_payload.get("file_path")
            else:
                nearest_similarity = 0
                nearest_file = None

            # Analyze import relationship
            outlier_file = payload.get("file_path", "")
            import_analysis = analyze_import_relationship(
                outlier_file,
                nearest_file or "",
                import_graph,
            )

            # Calculate balanced confidence score
            confidence, confidence_factors = calculate_balanced_confidence(
                outlier_payload=payload,
                nearest_payload=nearest_payload,
                similarity=nearest_similarity,
                import_analysis=import_analysis,
            )

            # Filter out low confidence outliers (< 0.4)
            if confidence < 0.4:
                continue

            # Assign tier based on confidence
            tier = self._assign_tier(confidence)

            # Generate suggestion based on confidence factors
            suggestion = self._generate_suggestion(
                confidence_factors=confidence_factors,
                nearest_file=nearest_file,
                similarity=nearest_similarity,
            )

            outliers.append(OutlierInfo(
                file_path=payload.get("file_path", "unknown"),
                chunk_name=payload.get("name"),
                chunk_type=payload.get("chunk_type"),
                nearest_similarity=round(nearest_similarity, 3),
                nearest_file=nearest_file,
                suggestion=suggestion,
                confidence=round(confidence, 3),
                confidence_factors=confidence_factors,
                tier=tier,
            ))

        # Sort by confidence descending (most actionable first)
        outliers.sort(key=lambda o: o.confidence, reverse=True)
        return outliers[:15]  # Limit to top 15

    def _build_import_graph(self, payloads: list[dict]) -> dict[str, set[str]]:
        """Build import graph from payloads.

        Extracts imports from each unique file's content and builds a mapping
        of file paths to their import statements.

        Args:
            payloads: List of chunk payloads with file_path, content, and language

        Returns:
            Dictionary mapping file paths to sets of imported module paths
        """
        import_graph: dict[str, set[str]] = {}

        # Group payloads by file to avoid duplicate processing
        seen_files: set[str] = set()

        for payload in payloads:
            file_path = payload.get("file_path", "")
            if not file_path or file_path in seen_files:
                continue

            seen_files.add(file_path)

            # Get content and language
            content = payload.get("content", "")
            language = payload.get("language", "")

            # Infer language from file extension if not provided
            if not language:
                if file_path.endswith(".py"):
                    language = "python"
                elif file_path.endswith((".js", ".jsx", ".mjs", ".cjs")):
                    language = "javascript"
                elif file_path.endswith((".ts", ".tsx")):
                    language = "typescript"

            # Extract imports
            if content and language:
                imports = extract_imports(content, language)
                if imports:
                    import_graph[file_path] = imports

        return import_graph

    def _assign_tier(self, confidence: float) -> str:
        """Assign tier based on confidence score.

        Args:
            confidence: Confidence score (0.1-0.9)

        Returns:
            Tier classification: "critical", "recommended", or "informational"
        """
        if confidence >= 0.7:
            return "critical"
        elif confidence >= 0.5:
            return "recommended"
        else:
            return "informational"

    def _generate_suggestion(
        self,
        confidence_factors: list[str],
        nearest_file: str | None,
        similarity: float,
    ) -> str:
        """Generate human-readable suggestion based on confidence factors.

        Args:
            confidence_factors: List of reasons explaining the confidence score
            nearest_file: Path to the nearest neighbor file
            similarity: Similarity score to nearest neighbor

        Returns:
            Human-readable suggestion string
        """
        # Check for specific patterns in confidence factors
        factors_lower = [f.lower() for f in confidence_factors]

        # Check for orphaned test FIRST (before general orphaned check)
        # This ensures test files get the specific test-related suggestion
        if any("test" in f and "orphaned" in f for f in factors_lower):
            return "Test file may be orphaned — no matching subject found"

        # Check for orphaned/dead code (general case)
        if any("orphaned" in f or "dead code" in f or "isolated" in f for f in factors_lower):
            return "Review for deletion — appears unused"

        # Check for possible duplicate
        if any("duplicate" in f for f in factors_lower):
            if nearest_file:
                return f"Possible duplicate of {nearest_file}"
            return "Possible duplicate — review for consolidation"

        # Check for circular dependency
        if any("circular" in f for f in factors_lower):
            if nearest_file:
                return f"Circular dependency with {nearest_file}"
            return "Circular dependency detected — architectural issue"

        # Check for high similarity
        if similarity > 0.7 and nearest_file:
            return f"High similarity to {nearest_file} — review relationship"

        # Default suggestion based on similarity
        if similarity < 0.3:
            return "Review for deletion — appears unused or orphaned"
        elif similarity < 0.5:
            if nearest_file:
                return f"Consider moving closer to {nearest_file}"
            return "Review placement"
        else:
            return "Minor outlier — may be a utility or edge case"

    def _find_coupling_hotspots(
        self,
        labels: np.ndarray,
        payloads: list[dict],
        cluster_id_to_name: dict[int, str] | None = None,
    ) -> list[CouplingHotspot]:
        """Find files that bridge multiple clusters (god files).

        Args:
            labels: Cluster labels for each chunk
            payloads: Metadata for each chunk
            cluster_id_to_name: Mapping from cluster ID to human-readable name
        """
        # Group chunks by file
        file_clusters: dict[str, set[int]] = defaultdict(set)

        for label, payload in zip(labels, payloads, strict=False):
            if label == -1:  # Skip outliers
                continue
            file_path = payload.get("file_path", "")
            if file_path:
                file_clusters[file_path].add(int(label))

        # Find files in multiple clusters
        hotspots = []
        for file_path, clusters in file_clusters.items():
            if len(clusters) >= 3:  # Bridges 3+ clusters
                # Use real cluster names if available, fallback to generic IDs
                if cluster_id_to_name:
                    names = [cluster_id_to_name.get(c, f"cluster_{c}") for c in sorted(clusters)]
                else:
                    names = [f"cluster_{c}" for c in sorted(clusters)]

                hotspots.append(CouplingHotspot(
                    file_path=file_path,
                    clusters_connected=len(clusters),
                    cluster_names=names,
                    suggestion="Consider splitting — this file has too many responsibilities",
                ))

        # Sort by clusters connected
        hotspots.sort(key=lambda h: h.clusters_connected, reverse=True)
        return hotspots[:10]  # Limit to top 10

    def _calculate_overall_score(
        self,
        clusters: list[ClusterInfo],
        actual_outlier_count: int,
        total_chunks: int,
        hotspot_count: int = 0,
        total_files: int = 0,
    ) -> int:
        """Calculate overall architecture health score (0-100).

        Components:
        - Cohesion (35%): Weighted average of cluster cohesion by size
        - Outliers (30%): Penalty for code not fitting any cluster
        - Balance (25%): Gini coefficient of cluster sizes
        - Coupling (10%): Penalty for god files bridging many clusters
        """
        if total_chunks == 0:
            return 0

        # Cohesion component (35%) - weighted by cluster size
        if clusters:
            total_in_clusters = sum(c.chunk_count for c in clusters)
            if total_in_clusters > 0:
                weighted_cohesion = sum(c.cohesion * c.chunk_count for c in clusters) / total_in_clusters
            else:
                weighted_cohesion = 0
            cohesion_score = weighted_cohesion * 35
        else:
            cohesion_score = 17.5  # Neutral if no clusters

        # Outlier component (30%) - uses ACTUAL count, not truncated list
        outlier_ratio = actual_outlier_count / total_chunks
        # 0% outliers = 30 points, 50%+ outliers = 0 points (linear scale)
        outlier_score = max(0, 30 * (1 - outlier_ratio * 2))

        # Cluster balance component (25%)
        if len(clusters) >= 2:
            sizes = np.array([c.chunk_count for c in clusters], dtype=float)
            sorted_sizes = np.sort(sizes)
            n = len(sorted_sizes)
            # Standard Gini coefficient formula
            index = np.arange(1, n + 1)
            gini = (2 * np.sum(index * sorted_sizes)) / (n * np.sum(sorted_sizes)) - (n + 1) / n
            # Clamp to valid range [0, 1] for safety
            gini = max(0.0, min(1.0, gini))
            balance_score = (1 - gini) * 25
        else:
            balance_score = 12.5  # Neutral

        # Coupling component (10%) - penalty for god files
        if total_files > 0 and hotspot_count > 0:
            hotspot_ratio = hotspot_count / total_files
            # 0% hotspots = 10 points, 20%+ hotspots = 0 points
            coupling_score = max(0, 10 * (1 - hotspot_ratio * 5))
        else:
            coupling_score = 10  # Full score if no hotspots

        total_score = cohesion_score + outlier_score + balance_score + coupling_score
        return int(min(100, max(0, total_score)))

    def _find_similar_code(
        self,
        vectors: np.ndarray,
        payloads: list[dict],
        threshold: float = 0.85,
        limit: int = 20,
    ) -> SimilarCodeResult:
        """Find groups of similar code (potential duplicates).

        Uses cosine similarity to find code chunks that are semantically similar,
        even if the syntax differs.

        Args:
            vectors: Array of embedding vectors
            payloads: Metadata for each chunk
            threshold: Minimum similarity to consider as duplicate (default 0.85)
            limit: Maximum number of groups to return (default 20)

        Returns:
            SimilarCodeResult with groups of similar code
        """
        from sklearn.metrics.pairwise import cosine_similarity

        if len(vectors) < 2:
            return SimilarCodeResult(groups=[], total_groups=0, potential_loc_reduction=0)

        logger.info(f"Finding similar code with threshold {threshold}")

        # Compute pairwise similarities
        similarities = cosine_similarity(vectors)

        # Find groups above threshold
        groups: list[SimilarCodeGroup] = []
        used: set[int] = set()

        for i in range(len(vectors)):
            if i in used:
                continue

            # Find all similar chunks
            similar_indices = np.where(similarities[i] >= threshold)[0]
            similar_indices = [j for j in similar_indices if j != i and j not in used]

            if similar_indices:
                group_indices = [i] + similar_indices
                avg_similarity = float(np.mean([similarities[i][j] for j in similar_indices]))

                # Mark as used
                used.update(group_indices)

                # Build group
                chunks = []
                total_lines = 0
                for idx in group_indices:
                    p = payloads[idx]
                    line_start = p.get("line_start", 0) or 0
                    line_end = p.get("line_end", 0) or 0
                    line_count = p.get("line_count", 0) or (line_end - line_start)

                    chunks.append({
                        "file": p.get("file_path", ""),
                        "name": p.get("name", ""),
                        "lines": [line_start, line_end],
                        "chunk_type": p.get("chunk_type", ""),
                    })
                    total_lines += line_count

                suggestion = "Extract to shared utility" if len(chunks) > 2 else "Consider consolidating"

                groups.append(SimilarCodeGroup(
                    similarity=round(avg_similarity, 3),
                    suggestion=suggestion,
                    chunks=chunks,
                ))

        # Sort by similarity and limit
        groups.sort(key=lambda g: g.similarity, reverse=True)
        groups = groups[:limit]

        # Estimate LOC reduction (sum of lines in all but first chunk of each group)
        potential_loc = sum(
            sum(c.get("lines", [0, 0])[1] - c.get("lines", [0, 0])[0] for c in g.chunks[1:])
            for g in groups
        )

        logger.info(f"Found {len(groups)} similar code groups")

        return SimilarCodeResult(
            groups=groups,
            total_groups=len(groups),
            potential_loc_reduction=potential_loc,
        )

    def _empty_health(self, chunk_count: int) -> ArchitectureHealth:
        """Return empty health result for repos with insufficient data."""
        return ArchitectureHealth(
            overall_score=0,
            clusters=[],
            outliers=[],
            coupling_hotspots=[],
            similar_code=None,
            total_chunks=chunk_count,
            total_files=0,
            metrics={
                "avg_cohesion": 0,
                "outlier_percentage": 0,
                "cluster_count": 0,
                "warning": "Insufficient data for clustering (need at least 5 chunks)",
            }
        )


    def analyze_for_llm(
        self,
        repo_id: str,
        repo_path: Path,
    ) -> LLMReadyArchitectureData:
        """Analyze repository and produce LLM-ready data.

        Integrates CallGraphAnalyzer, GitAnalyzer, and CoverageAnalyzer
        to produce comprehensive architecture findings optimized for
        AI/LLM consumption.

        Args:
            repo_id: Repository ID for vector lookups
            repo_path: Path to the cloned repository

        Returns:
            LLMReadyArchitectureData with all findings

        Requirements: 4.1, 5.1
        """
        logger.info(f"Starting LLM-ready analysis for repo {repo_id} at {repo_path}")

        # Initialize analyzers
        call_graph_analyzer = get_call_graph_analyzer()
        git_analyzer = GitAnalyzer()
        coverage_analyzer = CoverageAnalyzer()

        # Build call graph and find dead code
        call_graph = call_graph_analyzer.analyze(repo_path)
        dead_code = call_graph_analyzer.to_dead_code_findings(call_graph)
        logger.info(f"Found {len(dead_code)} dead code findings")

        # Analyze git churn
        churn_data = git_analyzer.analyze(repo_path)
        logger.info(f"Analyzed churn for {len(churn_data)} files")

        # Parse coverage if available
        coverage_data = coverage_analyzer.parse_if_exists(repo_path)
        if coverage_data:
            logger.info(f"Found coverage data for {len(coverage_data)} files")
        else:
            logger.info("No coverage data available")

        # Generate hot spot findings
        hot_spots = git_analyzer.to_hot_spot_findings(
            churn_data, coverage_data, threshold=10
        )
        logger.info(f"Found {len(hot_spots)} hot spot findings")

        # Calculate total files and functions
        total_files = len(churn_data) if churn_data else 0
        total_functions = len(call_graph.nodes) if call_graph.nodes else 0

        # Build summary with health score and main concerns
        summary = self._generate_architecture_summary(
            dead_code=dead_code,
            hot_spots=hot_spots,
            total_files=total_files,
            total_functions=total_functions,
        )

        return LLMReadyArchitectureData(
            summary=summary,
            dead_code=dead_code,
            hot_spots=hot_spots,
            issues=[],  # Future: coupling, complexity issues
        )

    def _generate_architecture_summary(
        self,
        dead_code: list[DeadCodeFinding],
        hot_spots: list[HotSpotFinding],
        total_files: int,
        total_functions: int,
    ) -> ArchitectureSummary:
        """Generate architecture summary with health score and main concerns.

        Calculates health_score based on:
        - Dead code ratio (40% weight)
        - Hot spot ratio (40% weight)
        - Coverage availability (20% weight)

        Generates natural language main_concerns list.

        Args:
            dead_code: List of dead code findings
            hot_spots: List of hot spot findings
            total_files: Total number of files in repository
            total_functions: Total number of functions in repository

        Returns:
            ArchitectureSummary with health_score and main_concerns

        Requirements: 4.1
        """
        # Calculate health score
        health_score = self._calculate_llm_health_score(
            dead_code_count=len(dead_code),
            hot_spot_count=len(hot_spots),
            total_files=total_files,
            total_functions=total_functions,
        )

        # Generate main concerns
        main_concerns = self._generate_main_concerns(dead_code, hot_spots)

        return ArchitectureSummary(
            health_score=health_score,
            main_concerns=main_concerns,
            total_files=total_files,
            total_functions=total_functions,
            dead_code_count=len(dead_code),
            hot_spot_count=len(hot_spots),
        )

    def _calculate_llm_health_score(
        self,
        dead_code_count: int,
        hot_spot_count: int,
        total_files: int,
        total_functions: int,
    ) -> int:
        """Calculate health score for LLM-ready data.

        Score components:
        - Dead code penalty (40%): More dead code = lower score
        - Hot spot penalty (40%): More hot spots = lower score
        - Base score (20%): Minimum score for having analyzable code

        Args:
            dead_code_count: Number of dead code findings
            hot_spot_count: Number of hot spot findings
            total_files: Total number of files
            total_functions: Total number of functions

        Returns:
            Health score 0-100
        """
        if total_functions == 0 and total_files == 0:
            return 0

        # Start with base score
        score = 100.0

        # Dead code penalty (40% weight)
        # 0 dead code = 0 penalty, 50%+ dead code = 40 point penalty
        if total_functions > 0:
            dead_code_ratio = dead_code_count / total_functions
            dead_code_penalty = min(40, dead_code_ratio * 80)
            score -= dead_code_penalty

        # Hot spot penalty (40% weight)
        # 0 hot spots = 0 penalty, 50%+ hot spots = 40 point penalty
        if total_files > 0:
            hot_spot_ratio = hot_spot_count / total_files
            hot_spot_penalty = min(40, hot_spot_ratio * 80)
            score -= hot_spot_penalty

        # Ensure minimum score of 0
        return max(0, min(100, int(score)))

    def _generate_main_concerns(
        self,
        dead_code: list[DeadCodeFinding],
        hot_spots: list[HotSpotFinding],
    ) -> list[str]:
        """Generate natural language concerns for LLM context.

        Creates human-readable concern strings based on findings.

        Args:
            dead_code: List of dead code findings
            hot_spots: List of hot spot findings

        Returns:
            List of natural language concern strings

        Requirements: 4.1
        """
        concerns: list[str] = []

        # Dead code concern
        if dead_code:
            total_lines = sum(d.line_count for d in dead_code)
            concerns.append(
                f"{len(dead_code)} unreachable functions ({total_lines} lines of dead code)"
            )

        # Hot spot concerns
        if hot_spots:
            # Find the worst hot spot
            worst = max(hot_spots, key=lambda h: h.churn_count)
            concerns.append(
                f"{worst.file_path} changed {worst.churn_count} times in 90 days"
            )

            # Count files with low coverage
            low_coverage_count = sum(
                1 for h in hot_spots
                if h.coverage_rate is not None and h.coverage_rate < 0.5
            )
            if low_coverage_count > 0:
                concerns.append(
                    f"{low_coverage_count} high-churn files have less than 50% test coverage"
                )

        # No concerns message
        if not concerns:
            concerns.append("No significant architecture concerns detected")

        return concerns


def get_cluster_analyzer() -> ClusterAnalyzer:
    """Get cluster analyzer instance."""
    return ClusterAnalyzer()
