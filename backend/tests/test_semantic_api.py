"""Integration tests for Semantic API endpoints.

Tests all vector-based code understanding features:
- Semantic search
- Related code detection
- Cluster analysis
- Outlier detection
- Similar code detection
- Refactoring suggestions
- Technical debt heatmap
- Code style consistency
"""


import pytest


class TestSemanticAPIRoutes:
    """Test that all semantic API routes are properly registered."""

    def test_all_routes_registered(self):
        """Verify all 10 semantic endpoints are registered."""
        from app.api.v1 import semantic

        routes = list(semantic.router.routes)
        route_paths = [r.path for r in routes]

        expected_paths = [
            "/repositories/{repository_id}/semantic-search",
            "/repositories/{repository_id}/related-code",
            "/repositories/{repository_id}/architecture-health",
            "/repositories/{repository_id}/outliers",
            "/repositories/{repository_id}/suggest-placement",
            "/repositories/{repository_id}/similar-code",
            "/repositories/{repository_id}/refactoring-suggestions",
            "/repositories/{repository_id}/tech-debt-heatmap",
            "/repositories/{repository_id}/style-consistency",
            "/repositories/{repository_id}/embedding-status",
        ]

        for expected in expected_paths:
            assert expected in route_paths, f"Missing route: {expected}"

        assert len(routes) == 10, f"Expected 10 routes, got {len(routes)}"

    def test_routes_are_get_methods(self):
        """Verify all routes use GET method."""
        from app.api.v1 import semantic

        for route in semantic.router.routes:
            methods = list(route.methods)
            assert "GET" in methods, f"Route {route.path} should be GET"


class TestCodeChunker:
    """Test code chunker functionality."""

    def test_chunk_python_file(self):
        """Test chunking a Python file."""
        from app.services.code_chunker import get_code_chunker

        code = '''
class UserService:
    def create_user(self, name):
        if name:
            return {"name": name}
        return None

    def delete_user(self, user_id):
        return True

def standalone_function():
    pass
'''

        chunker = get_code_chunker()
        chunks = chunker.chunk_file("services/user.py", code)

        assert len(chunks) >= 2, "Should create multiple chunks"

        # Check method chunks
        method_chunks = [c for c in chunks if c.chunk_type == "method"]
        assert len(method_chunks) >= 2, "Should have method chunks"

        # Check qualified names
        for chunk in method_chunks:
            assert chunk.qualified_name is not None
            assert "UserService" in chunk.qualified_name

    def test_chunk_with_complexity(self):
        """Test that complexity is calculated for functions."""
        from app.services.code_chunker import get_code_chunker

        code = '''
def complex_function(x, y):
    if x > 0:
        for i in range(y):
            if i % 2 == 0:
                print(i)
            elif i % 3 == 0:
                print("three")
    while x > 0:
        x -= 1
    return x and y
'''

        chunker = get_code_chunker()
        chunks = chunker.chunk_file("test.py", code)

        assert len(chunks) >= 1
        func_chunk = chunks[0]
        assert func_chunk.cyclomatic_complexity is not None
        assert func_chunk.cyclomatic_complexity >= 5, "Complex function should have CC >= 5"

    def test_chunk_javascript_file(self):
        """Test chunking a JavaScript file."""
        from app.services.code_chunker import get_code_chunker

        code = '''
function createUser(name) {
    if (name) {
        return { name };
    }
    return null;
}

const deleteUser = async (userId) => {
    return true;
};
'''

        chunker = get_code_chunker()
        chunks = chunker.chunk_file("services/user.js", code)

        assert len(chunks) >= 1, "Should create at least one chunk"

    def test_hierarchical_levels(self):
        """Test that hierarchical levels are assigned correctly."""
        from app.services.code_chunker import get_code_chunker

        code = '''
class MyClass:
    def my_method(self):
        pass

def standalone():
    pass
'''

        chunker = get_code_chunker()
        chunks = chunker.chunk_file("test.py", code)

        for chunk in chunks:
            if chunk.chunk_type == "method" and chunk.parent_name:
                assert chunk.level == 2, "Methods should be level 2"
            elif chunk.chunk_type == "function":
                assert chunk.level == 1, "Standalone functions should be level 1"


class TestCyclomaticComplexity:
    """Test cyclomatic complexity calculation."""

    def test_simple_function(self):
        """Test CC for simple function."""
        from app.services.code_chunker import calculate_cyclomatic_complexity

        code = "def simple(): return 1"
        cc = calculate_cyclomatic_complexity(code, "python")
        assert cc == 1, "Simple function should have CC=1"

    def test_function_with_if(self):
        """Test CC for function with if statement."""
        from app.services.code_chunker import calculate_cyclomatic_complexity

        code = '''
def func(x):
    if x > 0:
        return x
    return 0
'''
        cc = calculate_cyclomatic_complexity(code, "python")
        assert cc >= 2, "Function with if should have CC >= 2"

    def test_function_with_loops(self):
        """Test CC for function with loops."""
        from app.services.code_chunker import calculate_cyclomatic_complexity

        code = '''
def func(items):
    for item in items:
        while item > 0:
            item -= 1
'''
        cc = calculate_cyclomatic_complexity(code, "python")
        assert cc >= 3, "Function with for and while should have CC >= 3"

    def test_javascript_complexity(self):
        """Test CC for JavaScript code."""
        from app.services.code_chunker import calculate_cyclomatic_complexity

        code = '''
function test(x) {
    if (x > 0) {
        return x && y;
    }
    return x || z;
}
'''
        cc = calculate_cyclomatic_complexity(code, "javascript")
        assert cc >= 4, "JS function with if and logical ops should have CC >= 4"


class TestClusterAnalyzer:
    """Test cluster analyzer functionality."""

    def test_cluster_analyzer_import(self):
        """Test that cluster analyzer can be imported."""
        from app.services.cluster_analyzer import (
            get_cluster_analyzer,
        )

        analyzer = get_cluster_analyzer()
        assert analyzer is not None

    def test_architecture_health_dataclass(self):
        """Test ArchitectureHealth dataclass."""
        from app.services.cluster_analyzer import (
            ArchitectureHealth,
            ClusterInfo,
        )

        health = ArchitectureHealth(
            overall_score=75,
            clusters=[
                ClusterInfo(
                    id=0,
                    name="services",
                    file_count=5,
                    chunk_count=20,
                    cohesion=0.85,
                    top_files=["a.py", "b.py"],
                    dominant_language="python",
                    status="healthy",
                )
            ],
            outliers=[],
            coupling_hotspots=[],
            similar_code=None,
            total_chunks=100,
            total_files=25,
            metrics={"avg_cohesion": 0.75},
        )

        assert health.overall_score == 75
        assert len(health.clusters) == 1
        assert health.clusters[0].name == "services"


class TestResponseModels:
    """Test API response models."""

    def test_semantic_search_response(self):
        """Test SemanticSearchResponse model."""
        from app.api.v1.semantic import SemanticSearchResponse, SemanticSearchResult

        response = SemanticSearchResponse(
            query="test query",
            results=[
                SemanticSearchResult(
                    file_path="test.py",
                    name="test_func",
                    chunk_type="function",
                    line_start=1,
                    line_end=10,
                    content="def test_func(): pass",
                    similarity=0.95,
                    qualified_name="test_func",
                    language="python",
                )
            ],
            total=1,
        )

        assert response.query == "test query"
        assert len(response.results) == 1
        assert response.results[0].similarity == 0.95

    def test_architecture_health_response(self):
        """Test ArchitectureHealthResponse model."""
        from app.api.v1.semantic import (
            ArchitectureHealthResponse,
            ClusterInfoResponse,
        )

        response = ArchitectureHealthResponse(
            overall_score=80,
            clusters=[
                ClusterInfoResponse(
                    id=0,
                    name="test",
                    file_count=5,
                    chunk_count=10,
                    cohesion=0.8,
                    top_files=["a.py"],
                    dominant_language="python",
                    status="healthy",
                )
            ],
            outliers=[],
            coupling_hotspots=[],
            total_chunks=50,
            total_files=10,
            metrics={"avg_cohesion": 0.8},
        )

        assert response.overall_score == 80
        assert len(response.clusters) == 1


class TestEmbeddingsWorker:
    """Test embeddings worker functionality."""

    def test_enhanced_payload_fields(self):
        """Test that embeddings worker stores enhanced payload fields."""
        import inspect

        from app.workers.embeddings import generate_embeddings

        source = inspect.getsource(generate_embeddings)

        # Check for enhanced fields
        required_fields = [
            "level",
            "qualified_name",
            "cyclomatic_complexity",
            "line_count",
            "cluster_id",
        ]

        for field in required_fields:
            assert field in source, f"Missing field in payload: {field}"


class TestQdrantMigration:
    """Test Qdrant schema migration."""

    def test_migration_script_exists(self):
        """Test that migration script exists and is importable."""
        from pathlib import Path

        script_path = Path("scripts/migrate_qdrant_v2.py")
        assert script_path.exists(), "Migration script should exist"

    def test_migration_indexes(self):
        """Test that migration adds required indexes."""
        # Read the migration script
        with open("scripts/migrate_qdrant_v2.py") as f:
            content = f.read()

        required_indexes = ["level", "cyclomatic_complexity", "cluster_id", "qualified_name"]

        for index in required_indexes:
            assert index in content, f"Migration should add index for: {index}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
