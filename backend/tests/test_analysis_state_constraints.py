"""Property-based tests for Analysis state constraints.

Uses Hypothesis for property-based testing to verify correctness properties
defined in the design document for the progress-tracking-refactor feature.

**Feature: progress-tracking-refactor, Property 8: Database Constraint Enforcement**
**Validates: Requirements 6.1, 6.2, 6.3**
"""

from hypothesis import given, settings, assume
from hypothesis import strategies as st

# =============================================================================
# Valid Status Values (from design document)
# =============================================================================

VALID_EMBEDDINGS_STATUS = ["none", "pending", "running", "completed", "failed"]
VALID_SEMANTIC_CACHE_STATUS = ["none", "pending", "computing", "completed", "failed"]
VALID_PROGRESS_RANGE = (0, 100)


# =============================================================================
# Custom Strategies
# =============================================================================


def valid_embeddings_status() -> st.SearchStrategy[str]:
    """Generate valid embeddings_status values."""
    return st.sampled_from(VALID_EMBEDDINGS_STATUS)


def valid_semantic_cache_status() -> st.SearchStrategy[str]:
    """Generate valid semantic_cache_status values."""
    return st.sampled_from(VALID_SEMANTIC_CACHE_STATUS)


def valid_progress() -> st.SearchStrategy[int]:
    """Generate valid progress values (0-100)."""
    return st.integers(min_value=0, max_value=100)


def invalid_embeddings_status() -> st.SearchStrategy[str]:
    """Generate invalid embeddings_status values."""
    return st.text(min_size=1, max_size=20).filter(
        lambda s: s not in VALID_EMBEDDINGS_STATUS
    )


def invalid_semantic_cache_status() -> st.SearchStrategy[str]:
    """Generate invalid semantic_cache_status values."""
    return st.text(min_size=1, max_size=20).filter(
        lambda s: s not in VALID_SEMANTIC_CACHE_STATUS
    )


def invalid_progress_below() -> st.SearchStrategy[int]:
    """Generate invalid progress values below 0."""
    return st.integers(max_value=-1)


def invalid_progress_above() -> st.SearchStrategy[int]:
    """Generate invalid progress values above 100."""
    return st.integers(min_value=101)


# =============================================================================
# Constraint Validation Functions (mirrors database CHECK constraints)
# =============================================================================


def validate_embeddings_status(status: str) -> bool:
    """
    Validate embeddings_status against CHECK constraint.
    
    Mirrors: CHECK (embeddings_status IN ('none', 'pending', 'running', 'completed', 'failed'))
    """
    return status in VALID_EMBEDDINGS_STATUS


def validate_semantic_cache_status(status: str) -> bool:
    """
    Validate semantic_cache_status against CHECK constraint.
    
    Mirrors: CHECK (semantic_cache_status IN ('none', 'pending', 'computing', 'completed', 'failed'))
    """
    return status in VALID_SEMANTIC_CACHE_STATUS


def validate_embeddings_progress(progress: int) -> bool:
    """
    Validate embeddings_progress against CHECK constraint.
    
    Mirrors: CHECK (embeddings_progress >= 0 AND embeddings_progress <= 100)
    """
    return 0 <= progress <= 100


# =============================================================================
# Property Tests for Database Constraint Enforcement
# =============================================================================


class TestEmbeddingsStatusConstraint:
    """
    Property tests for embeddings_status CHECK constraint.
    
    **Feature: progress-tracking-refactor, Property 8: Database Constraint Enforcement**
    **Validates: Requirements 6.1**
    """

    @given(valid_embeddings_status())
    @settings(max_examples=100)
    def test_valid_embeddings_status_accepted(self, status: str):
        """
        **Feature: progress-tracking-refactor, Property 8: Database Constraint Enforcement**
        **Validates: Requirements 6.1**
        
        Property: For any valid embeddings_status value ('none', 'pending', 'running', 
        'completed', 'failed'), the validation SHALL accept the value.
        """
        assert validate_embeddings_status(status), (
            f"Valid embeddings_status '{status}' should be accepted\n"
            f"Valid values: {VALID_EMBEDDINGS_STATUS}"
        )

    @given(invalid_embeddings_status())
    @settings(max_examples=100)
    def test_invalid_embeddings_status_rejected(self, status: str):
        """
        **Feature: progress-tracking-refactor, Property 8: Database Constraint Enforcement**
        **Validates: Requirements 6.1**
        
        Property: For any invalid embeddings_status value (not in the valid set),
        the validation SHALL reject the value.
        """
        # Ensure we're testing truly invalid values
        assume(status not in VALID_EMBEDDINGS_STATUS)
        
        assert not validate_embeddings_status(status), (
            f"Invalid embeddings_status '{status}' should be rejected\n"
            f"Valid values: {VALID_EMBEDDINGS_STATUS}"
        )


class TestSemanticCacheStatusConstraint:
    """
    Property tests for semantic_cache_status CHECK constraint.
    
    **Feature: progress-tracking-refactor, Property 8: Database Constraint Enforcement**
    **Validates: Requirements 6.2**
    """

    @given(valid_semantic_cache_status())
    @settings(max_examples=100)
    def test_valid_semantic_cache_status_accepted(self, status: str):
        """
        **Feature: progress-tracking-refactor, Property 8: Database Constraint Enforcement**
        **Validates: Requirements 6.2**
        
        Property: For any valid semantic_cache_status value ('none', 'pending', 'computing',
        'completed', 'failed'), the validation SHALL accept the value.
        """
        assert validate_semantic_cache_status(status), (
            f"Valid semantic_cache_status '{status}' should be accepted\n"
            f"Valid values: {VALID_SEMANTIC_CACHE_STATUS}"
        )

    @given(invalid_semantic_cache_status())
    @settings(max_examples=100)
    def test_invalid_semantic_cache_status_rejected(self, status: str):
        """
        **Feature: progress-tracking-refactor, Property 8: Database Constraint Enforcement**
        **Validates: Requirements 6.2**
        
        Property: For any invalid semantic_cache_status value (not in the valid set),
        the validation SHALL reject the value.
        """
        # Ensure we're testing truly invalid values
        assume(status not in VALID_SEMANTIC_CACHE_STATUS)
        
        assert not validate_semantic_cache_status(status), (
            f"Invalid semantic_cache_status '{status}' should be rejected\n"
            f"Valid values: {VALID_SEMANTIC_CACHE_STATUS}"
        )


class TestEmbeddingsProgressConstraint:
    """
    Property tests for embeddings_progress CHECK constraint.
    
    **Feature: progress-tracking-refactor, Property 8: Database Constraint Enforcement**
    **Validates: Requirements 6.3**
    """

    @given(valid_progress())
    @settings(max_examples=100)
    def test_valid_progress_accepted(self, progress: int):
        """
        **Feature: progress-tracking-refactor, Property 8: Database Constraint Enforcement**
        **Validates: Requirements 6.3**
        
        Property: For any progress value between 0 and 100 inclusive,
        the validation SHALL accept the value.
        """
        assert validate_embeddings_progress(progress), (
            f"Valid progress {progress} should be accepted\n"
            f"Valid range: [0, 100]"
        )

    @given(invalid_progress_below())
    @settings(max_examples=100)
    def test_progress_below_zero_rejected(self, progress: int):
        """
        **Feature: progress-tracking-refactor, Property 8: Database Constraint Enforcement**
        **Validates: Requirements 6.3**
        
        Property: For any progress value below 0,
        the validation SHALL reject the value.
        """
        assert not validate_embeddings_progress(progress), (
            f"Progress {progress} below 0 should be rejected\n"
            f"Valid range: [0, 100]"
        )

    @given(invalid_progress_above())
    @settings(max_examples=100)
    def test_progress_above_hundred_rejected(self, progress: int):
        """
        **Feature: progress-tracking-refactor, Property 8: Database Constraint Enforcement**
        **Validates: Requirements 6.3**
        
        Property: For any progress value above 100,
        the validation SHALL reject the value.
        """
        assert not validate_embeddings_progress(progress), (
            f"Progress {progress} above 100 should be rejected\n"
            f"Valid range: [0, 100]"
        )


class TestCombinedConstraints:
    """
    Property tests for combined constraint validation.
    
    **Feature: progress-tracking-refactor, Property 8: Database Constraint Enforcement**
    **Validates: Requirements 6.1, 6.2, 6.3**
    """

    @given(
        embeddings_status=valid_embeddings_status(),
        semantic_cache_status=valid_semantic_cache_status(),
        progress=valid_progress(),
    )
    @settings(max_examples=100)
    def test_all_valid_values_accepted(
        self,
        embeddings_status: str,
        semantic_cache_status: str,
        progress: int,
    ):
        """
        **Feature: progress-tracking-refactor, Property 8: Database Constraint Enforcement**
        **Validates: Requirements 6.1, 6.2, 6.3**
        
        Property: For any combination of valid embeddings_status, semantic_cache_status,
        and progress values, all validations SHALL pass.
        """
        assert validate_embeddings_status(embeddings_status), (
            f"Valid embeddings_status '{embeddings_status}' should be accepted"
        )
        assert validate_semantic_cache_status(semantic_cache_status), (
            f"Valid semantic_cache_status '{semantic_cache_status}' should be accepted"
        )
        assert validate_embeddings_progress(progress), (
            f"Valid progress {progress} should be accepted"
        )

    @given(
        embeddings_status=st.one_of(valid_embeddings_status(), invalid_embeddings_status()),
        semantic_cache_status=st.one_of(valid_semantic_cache_status(), invalid_semantic_cache_status()),
        progress=st.one_of(valid_progress(), invalid_progress_below(), invalid_progress_above()),
    )
    @settings(max_examples=200)
    def test_validation_consistency(
        self,
        embeddings_status: str,
        semantic_cache_status: str,
        progress: int,
    ):
        """
        **Feature: progress-tracking-refactor, Property 8: Database Constraint Enforcement**
        **Validates: Requirements 6.1, 6.2, 6.3**
        
        Property: For any combination of values (valid or invalid), the validation
        functions SHALL correctly identify valid vs invalid values.
        """
        # Embeddings status validation
        is_valid_emb = embeddings_status in VALID_EMBEDDINGS_STATUS
        assert validate_embeddings_status(embeddings_status) == is_valid_emb, (
            f"Validation mismatch for embeddings_status '{embeddings_status}'\n"
            f"Expected valid: {is_valid_emb}"
        )

        # Semantic cache status validation
        is_valid_sem = semantic_cache_status in VALID_SEMANTIC_CACHE_STATUS
        assert validate_semantic_cache_status(semantic_cache_status) == is_valid_sem, (
            f"Validation mismatch for semantic_cache_status '{semantic_cache_status}'\n"
            f"Expected valid: {is_valid_sem}"
        )

        # Progress validation
        is_valid_prog = 0 <= progress <= 100
        assert validate_embeddings_progress(progress) == is_valid_prog, (
            f"Validation mismatch for progress {progress}\n"
            f"Expected valid: {is_valid_prog}"
        )
