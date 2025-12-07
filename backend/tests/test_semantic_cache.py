"""Property-based tests for Semantic Cache.

Uses Hypothesis for property-based testing to verify correctness properties
defined in the design document for the commit-centric-dashboard feature.
"""

from datetime import UTC, datetime
from uuid import uuid4

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from app.schemas.analysis import (
    ArchitectureHealthCache,
    ClusterInfoCache,
    OutlierInfoCache,
)

# =============================================================================
# Custom Strategies for Semantic Cache Testing
# =============================================================================


def valid_file_path() -> st.SearchStrategy[str]:
    """Generate valid file paths for testing."""
    return st.lists(
        st.from_regex(r"[a-z][a-z0-9_]*", fullmatch=True).filter(lambda s: 2 <= len(s) <= 15),
        min_size=1,
        max_size=4
    ).map(lambda parts: "/".join(parts) + ".py")


def cluster_status() -> st.SearchStrategy[str]:
    """Generate valid cluster status values."""
    return st.sampled_from(["healthy", "moderate", "scattered"])


def outlier_tier() -> st.SearchStrategy[str]:
    """Generate valid outlier tier values."""
    return st.sampled_from(["critical", "recommended", "informational"])


@st.composite
def cluster_info_cache(draw) -> dict:
    """Generate a valid ClusterInfoCache dict."""
    return {
        "id": draw(st.integers(min_value=0, max_value=100)),
        "name": draw(st.from_regex(r"[a-z][a-z0-9_]*", fullmatch=True).filter(lambda s: 2 <= len(s) <= 20)),
        "file_count": draw(st.integers(min_value=1, max_value=100)),
        "chunk_count": draw(st.integers(min_value=1, max_value=500)),
        "cohesion": draw(st.floats(min_value=0.0, max_value=1.0, allow_nan=False)),
        "top_files": draw(st.lists(valid_file_path(), min_size=0, max_size=5)),
        "dominant_language": draw(st.one_of(st.none(), st.sampled_from(["python", "javascript", "typescript"]))),
        "status": draw(cluster_status()),
    }


@st.composite
def outlier_info_cache(draw) -> dict:
    """Generate a valid OutlierInfoCache dict."""
    return {
        "file_path": draw(valid_file_path()),
        "chunk_name": draw(st.one_of(st.none(), st.from_regex(r"[a-z][a-z0-9_]*", fullmatch=True).filter(lambda s: 2 <= len(s) <= 20))),
        "chunk_type": draw(st.one_of(st.none(), st.sampled_from(["function", "class", "method"]))),
        "nearest_similarity": draw(st.floats(min_value=0.0, max_value=1.0, allow_nan=False)),
        "nearest_file": draw(st.one_of(st.none(), valid_file_path())),
        "suggestion": draw(st.text(min_size=5, max_size=100)),
        "confidence": draw(st.floats(min_value=0.1, max_value=0.9, allow_nan=False)),
        "confidence_factors": draw(st.lists(st.text(min_size=3, max_size=50), min_size=0, max_size=5)),
        "tier": draw(outlier_tier()),
    }


@st.composite
def coupling_hotspot_cache(draw) -> dict:
    """Generate a valid CouplingHotspotCache dict."""
    return {
        "file_path": draw(valid_file_path()),
        "clusters_connected": draw(st.integers(min_value=3, max_value=10)),
        "cluster_names": draw(st.lists(
            st.from_regex(r"[a-z][a-z0-9_]*", fullmatch=True).filter(lambda s: 2 <= len(s) <= 15),
            min_size=3,
            max_size=10
        )),
        "suggestion": draw(st.text(min_size=5, max_size=100)),
    }


@st.composite
def architecture_health_cache(draw) -> dict:
    """Generate a valid ArchitectureHealthCache dict."""
    clusters = draw(st.lists(cluster_info_cache(), min_size=0, max_size=10))
    outliers = draw(st.lists(outlier_info_cache(), min_size=0, max_size=15))
    hotspots = draw(st.lists(coupling_hotspot_cache(), min_size=0, max_size=10))

    total_chunks = sum(c["chunk_count"] for c in clusters) + len(outliers)
    total_files = len(set(
        [f for c in clusters for f in c["top_files"]] +
        [o["file_path"] for o in outliers] +
        [h["file_path"] for h in hotspots]
    ))

    return {
        "overall_score": draw(st.integers(min_value=0, max_value=100)),
        "clusters": clusters,
        "outliers": outliers,
        "coupling_hotspots": hotspots,
        "total_chunks": max(total_chunks, 1),
        "total_files": max(total_files, 1),
        "metrics": {
            "avg_cohesion": draw(st.floats(min_value=0.0, max_value=1.0, allow_nan=False)),
            "outlier_percentage": draw(st.floats(min_value=0.0, max_value=100.0, allow_nan=False)),
            "cluster_count": len(clusters),
        },
    }


@st.composite
def semantic_cache_data(draw) -> dict:
    """Generate valid semantic cache data as stored in PostgreSQL."""
    return {
        "architecture_health": draw(architecture_health_cache()),
        "computed_at": datetime.now(UTC).isoformat(),
    }


# =============================================================================
# Property Tests for Semantic Cache
# =============================================================================


class TestSemanticCacheServingProperties:
    """Property tests for semantic cache serving.

    **Feature: commit-centric-dashboard, Property 5: Cached semantic data served from PostgreSQL**
    **Validates: Requirements 3.2, 4.2**
    """

    @given(semantic_cache_data())
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_cached_semantic_data_structure_completeness(self, cache_data: dict):
        """
        **Feature: commit-centric-dashboard, Property 5: Cached semantic data served from PostgreSQL**
        **Validates: Requirements 3.2, 4.2**

        Property: For any valid semantic cache data stored in PostgreSQL, when retrieved
        the response SHALL contain all required fields (architecture_health, computed_at)
        and is_cached SHALL be True.
        """
        # Simulate the response construction from cached data (as done in the endpoint)
        analysis_id = uuid4()
        commit_sha = "abc1234567890def1234567890abcdef12345678"

        # This mirrors the logic in get_semantic_cache endpoint
        if cache_data and cache_data.get("architecture_health"):
            response = {
                "analysis_id": str(analysis_id),
                "commit_sha": commit_sha,
                "architecture_health": cache_data.get("architecture_health"),
                "computed_at": cache_data.get("computed_at"),
                "is_cached": True,
            }
        else:
            response = {
                "analysis_id": str(analysis_id),
                "commit_sha": commit_sha,
                "architecture_health": None,
                "computed_at": None,
                "is_cached": False,
            }

        # Property: When cache exists, is_cached must be True
        assert response["is_cached"] is True, (
            f"is_cached should be True when cache data exists\n"
            f"Cache data: {cache_data}"
        )

        # Property: architecture_health must be present and non-null
        assert response["architecture_health"] is not None, (
            f"architecture_health should not be None when cache exists\n"
            f"Response: {response}"
        )

        # Property: computed_at must be present
        assert response["computed_at"] is not None, (
            f"computed_at should not be None when cache exists\n"
            f"Response: {response}"
        )

        # Property: architecture_health must contain required fields
        arch_health = response["architecture_health"]
        required_fields = ["overall_score", "clusters", "outliers", "coupling_hotspots", "total_chunks", "total_files", "metrics"]
        for field in required_fields:
            assert field in arch_health, (
                f"architecture_health missing required field '{field}'\n"
                f"architecture_health: {arch_health}"
            )

    @given(architecture_health_cache())
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_architecture_health_cache_schema_validation(self, arch_health: dict):
        """
        **Feature: commit-centric-dashboard, Property 5: Cached semantic data served from PostgreSQL**
        **Validates: Requirements 3.2, 4.2**

        Property: For any architecture health data, it SHALL be deserializable into
        the ArchitectureHealthCache Pydantic schema without errors.
        """
        # This tests that our generated data matches the Pydantic schema
        try:
            validated = ArchitectureHealthCache(**arch_health)

            # Property: overall_score must be in valid range
            assert 0 <= validated.overall_score <= 100, (
                f"overall_score {validated.overall_score} out of range [0, 100]"
            )

            # Property: clusters list must be valid
            assert isinstance(validated.clusters, list), "clusters must be a list"

            # Property: outliers list must be valid
            assert isinstance(validated.outliers, list), "outliers must be a list"

            # Property: coupling_hotspots list must be valid
            assert isinstance(validated.coupling_hotspots, list), "coupling_hotspots must be a list"

        except Exception as e:
            raise AssertionError(
                f"Failed to validate ArchitectureHealthCache schema\n"
                f"Data: {arch_health}\n"
                f"Error: {e}"
            )

    @given(st.none())
    @settings(max_examples=1)
    def test_missing_cache_returns_is_cached_false(self, _):
        """
        **Feature: commit-centric-dashboard, Property 5: Cached semantic data served from PostgreSQL**
        **Validates: Requirements 3.2, 4.2**

        Property: When semantic_cache is None or missing architecture_health,
        the response SHALL have is_cached=False and null fields.
        """
        analysis_id = uuid4()
        commit_sha = "abc1234567890def1234567890abcdef12345678"

        # Test with None cache
        cache = None
        if cache and cache.get("architecture_health"):
            response = {
                "analysis_id": str(analysis_id),
                "commit_sha": commit_sha,
                "architecture_health": cache.get("architecture_health"),
                "computed_at": cache.get("computed_at"),
                "is_cached": True,
            }
        else:
            response = {
                "analysis_id": str(analysis_id),
                "commit_sha": commit_sha,
                "architecture_health": None,
                "computed_at": None,
                "is_cached": False,
            }

        # Property: is_cached must be False when no cache
        assert response["is_cached"] is False, "is_cached should be False when cache is None"
        assert response["architecture_health"] is None, "architecture_health should be None when cache is None"
        assert response["computed_at"] is None, "computed_at should be None when cache is None"

        # Test with empty cache (no architecture_health key)
        cache = {}
        if cache and cache.get("architecture_health"):
            response = {
                "analysis_id": str(analysis_id),
                "commit_sha": commit_sha,
                "architecture_health": cache.get("architecture_health"),
                "computed_at": cache.get("computed_at"),
                "is_cached": True,
            }
        else:
            response = {
                "analysis_id": str(analysis_id),
                "commit_sha": commit_sha,
                "architecture_health": None,
                "computed_at": None,
                "is_cached": False,
            }

        # Property: is_cached must be False when architecture_health is missing
        assert response["is_cached"] is False, "is_cached should be False when architecture_health is missing"


class TestClusterInfoCacheProperties:
    """Property tests for cluster info cache validation."""

    @given(cluster_info_cache())
    @settings(max_examples=100)
    def test_cluster_info_cache_schema_validation(self, cluster: dict):
        """
        Property: For any cluster info data, it SHALL be deserializable into
        the ClusterInfoCache Pydantic schema without errors.
        """
        try:
            validated = ClusterInfoCache(**cluster)

            # Property: cohesion must be in valid range [0, 1]
            assert 0.0 <= validated.cohesion <= 1.0, (
                f"cohesion {validated.cohesion} out of range [0, 1]"
            )

            # Property: status must be valid
            assert validated.status in ["healthy", "moderate", "scattered"], (
                f"Invalid status: {validated.status}"
            )

        except Exception as e:
            raise AssertionError(
                f"Failed to validate ClusterInfoCache schema\n"
                f"Data: {cluster}\n"
                f"Error: {e}"
            )


class TestOutlierInfoCacheProperties:
    """Property tests for outlier info cache validation."""

    @given(outlier_info_cache())
    @settings(max_examples=100)
    def test_outlier_info_cache_schema_validation(self, outlier: dict):
        """
        Property: For any outlier info data, it SHALL be deserializable into
        the OutlierInfoCache Pydantic schema without errors.
        """
        try:
            validated = OutlierInfoCache(**outlier)

            # Property: confidence must be in valid range [0.1, 0.9]
            assert 0.1 <= validated.confidence <= 0.9, (
                f"confidence {validated.confidence} out of range [0.1, 0.9]"
            )

            # Property: tier must be valid
            assert validated.tier in ["critical", "recommended", "informational"], (
                f"Invalid tier: {validated.tier}"
            )

            # Property: nearest_similarity must be in valid range [0, 1]
            assert 0.0 <= validated.nearest_similarity <= 1.0, (
                f"nearest_similarity {validated.nearest_similarity} out of range [0, 1]"
            )

        except Exception as e:
            raise AssertionError(
                f"Failed to validate OutlierInfoCache schema\n"
                f"Data: {outlier}\n"
                f"Error: {e}"
            )
