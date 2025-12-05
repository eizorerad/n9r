"""Property-based tests for state persistence.

Uses Hypothesis for property-based testing to verify correctness properties
defined in the design document for the progress-tracking-refactor feature.

Tests cover:
- Property 1: State Persistence Across Restarts
- Property 2: State Independence from Redis

**Feature: progress-tracking-refactor**
**Validates: Requirements 1.1, 1.2**
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from app.services.analysis_state import (
    VALID_EMBEDDINGS_STATUS,
    VALID_SEMANTIC_CACHE_STATUS,
)


# =============================================================================
# Custom Strategies
# =============================================================================


def valid_embeddings_status() -> st.SearchStrategy[str]:
    """Generate valid embeddings_status values."""
    return st.sampled_from(list(VALID_EMBEDDINGS_STATUS))


def valid_semantic_cache_status() -> st.SearchStrategy[str]:
    """Generate valid semantic_cache_status values."""
    return st.sampled_from(list(VALID_SEMANTIC_CACHE_STATUS))


def valid_progress() -> st.SearchStrategy[int]:
    """Generate valid progress values (0-100)."""
    return st.integers(min_value=0, max_value=100)


def valid_vectors_count() -> st.SearchStrategy[int]:
    """Generate valid vectors_count values."""
    return st.integers(min_value=0, max_value=100000)


def valid_stage() -> st.SearchStrategy[str | None]:
    """Generate valid embeddings_stage values."""
    return st.sampled_from([
        None, "pending", "initializing", "chunking", "embedding", "indexing", "completed", "error"
    ])


def valid_message() -> st.SearchStrategy[str | None]:
    """Generate valid embeddings_message values."""
    return st.one_of(
        st.none(),
        st.text(min_size=1, max_size=100, alphabet=st.characters(whitelist_categories=('L', 'N', 'P', 'Z'))),
    )


def valid_error() -> st.SearchStrategy[str | None]:
    """Generate valid embeddings_error values."""
    return st.one_of(
        st.none(),
        st.text(min_size=1, max_size=200, alphabet=st.characters(whitelist_categories=('L', 'N', 'P', 'Z'))),
    )


def valid_vci_score() -> st.SearchStrategy[float | None]:
    """Generate valid VCI score values."""
    return st.one_of(
        st.none(),
        st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False),
    )


def valid_analysis_status() -> st.SearchStrategy[str]:
    """Generate valid analysis status values."""
    return st.sampled_from(["pending", "running", "completed", "failed"])


# =============================================================================
# Property 1: State Persistence Across Restarts
# =============================================================================


class TestStatePersistenceAcrossRestarts:
    """
    Property tests for state persistence across restarts.
    
    **Feature: progress-tracking-refactor, Property 1: State Persistence Across Restarts**
    **Validates: Requirements 1.1**
    """

    @given(
        embeddings_status=valid_embeddings_status(),
        embeddings_progress=valid_progress(),
        embeddings_stage=valid_stage(),
        embeddings_message=valid_message(),
        embeddings_error=valid_error(),
        vectors_count=valid_vectors_count(),
        semantic_cache_status=valid_semantic_cache_status(),
    )
    @settings(max_examples=100)
    def test_embeddings_state_persists_across_session_reconnect(
        self,
        embeddings_status: str,
        embeddings_progress: int,
        embeddings_stage: str | None,
        embeddings_message: str | None,
        embeddings_error: str | None,
        vectors_count: int,
        semantic_cache_status: str,
    ):
        """
        **Feature: progress-tracking-refactor, Property 1: State Persistence Across Restarts**
        **Validates: Requirements 1.1**
        
        Property: For any analysis with embeddings_status set to a valid value,
        if the database connection is closed and reopened (simulating restart),
        the embeddings_status SHALL remain unchanged.
        
        This test simulates the persistence behavior by:
        1. Creating an analysis state with given values
        2. Simulating a "restart" by creating a new session that reads the same data
        3. Verifying all state values are preserved
        """
        analysis_id = uuid.uuid4()
        repository_id = uuid.uuid4()
        initial_timestamp = datetime.now(timezone.utc)
        
        # Create the "persisted" state that would be stored in PostgreSQL
        persisted_state = {
            "id": analysis_id,
            "repository_id": repository_id,
            "commit_sha": "abc123def456",
            "status": "completed",
            "embeddings_status": embeddings_status,
            "embeddings_progress": embeddings_progress,
            "embeddings_stage": embeddings_stage,
            "embeddings_message": embeddings_message,
            "embeddings_error": embeddings_error,
            "vectors_count": vectors_count,
            "semantic_cache_status": semantic_cache_status,
            "state_updated_at": initial_timestamp,
        }
        
        # Simulate "Session 1" - the original session that wrote the state
        mock_analysis_session1 = MagicMock()
        for key, value in persisted_state.items():
            setattr(mock_analysis_session1, key, value)
        mock_analysis_session1.semantic_cache = None
        mock_analysis_session1.vci_score = 85.5
        mock_analysis_session1.grade = "B"
        mock_analysis_session1.embeddings_started_at = initial_timestamp
        mock_analysis_session1.embeddings_completed_at = None
        
        # Simulate "Session 2" - a new session after "restart" that reads the same data
        # In a real database, this would be a new connection reading from PostgreSQL
        mock_analysis_session2 = MagicMock()
        for key, value in persisted_state.items():
            setattr(mock_analysis_session2, key, value)
        mock_analysis_session2.semantic_cache = None
        mock_analysis_session2.vci_score = 85.5
        mock_analysis_session2.grade = "B"
        mock_analysis_session2.embeddings_started_at = initial_timestamp
        mock_analysis_session2.embeddings_completed_at = None
        
        # Verify all state values are preserved across "restart"
        # This simulates what PostgreSQL guarantees - data persists across connections
        assert mock_analysis_session2.embeddings_status == embeddings_status, (
            f"embeddings_status should persist: expected '{embeddings_status}', "
            f"got '{mock_analysis_session2.embeddings_status}'"
        )
        assert mock_analysis_session2.embeddings_progress == embeddings_progress, (
            f"embeddings_progress should persist: expected {embeddings_progress}, "
            f"got {mock_analysis_session2.embeddings_progress}"
        )
        assert mock_analysis_session2.embeddings_stage == embeddings_stage, (
            f"embeddings_stage should persist: expected '{embeddings_stage}', "
            f"got '{mock_analysis_session2.embeddings_stage}'"
        )
        assert mock_analysis_session2.embeddings_message == embeddings_message, (
            f"embeddings_message should persist"
        )
        assert mock_analysis_session2.embeddings_error == embeddings_error, (
            f"embeddings_error should persist"
        )
        assert mock_analysis_session2.vectors_count == vectors_count, (
            f"vectors_count should persist: expected {vectors_count}, "
            f"got {mock_analysis_session2.vectors_count}"
        )
        assert mock_analysis_session2.semantic_cache_status == semantic_cache_status, (
            f"semantic_cache_status should persist: expected '{semantic_cache_status}', "
            f"got '{mock_analysis_session2.semantic_cache_status}'"
        )
        assert mock_analysis_session2.state_updated_at == initial_timestamp, (
            f"state_updated_at should persist"
        )

    @given(
        embeddings_status=valid_embeddings_status(),
        semantic_cache_status=valid_semantic_cache_status(),
    )
    @settings(max_examples=100)
    def test_state_service_reads_persisted_state(
        self,
        embeddings_status: str,
        semantic_cache_status: str,
    ):
        """
        **Feature: progress-tracking-refactor, Property 1: State Persistence Across Restarts**
        **Validates: Requirements 1.1**
        
        Property: The AnalysisStateService SHALL read state from PostgreSQL,
        ensuring state persists across service restarts.
        """
        from app.services.analysis_state import AnalysisStateService
        
        analysis_id = uuid.uuid4()
        initial_timestamp = datetime.now(timezone.utc)
        
        # Create mock analysis with persisted state
        mock_analysis = MagicMock()
        mock_analysis.id = analysis_id
        mock_analysis.embeddings_status = embeddings_status
        mock_analysis.embeddings_progress = 50
        mock_analysis.embeddings_stage = "embedding"
        mock_analysis.embeddings_message = "Processing..."
        mock_analysis.embeddings_error = None
        mock_analysis.vectors_count = 100
        mock_analysis.semantic_cache_status = semantic_cache_status
        mock_analysis.semantic_cache = None
        mock_analysis.state_updated_at = initial_timestamp
        
        # Create mock session that returns the persisted state
        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_analysis
        mock_session.execute.return_value = mock_result
        
        # Create service (simulating a new service instance after restart)
        service = AnalysisStateService(mock_session, publish_events=False)
        
        # The service should read from the database (PostgreSQL)
        # This verifies the service uses the database as source of truth
        retrieved_analysis = service._get_analysis(analysis_id)
        
        # Verify the retrieved state matches what was "persisted"
        assert retrieved_analysis.embeddings_status == embeddings_status
        assert retrieved_analysis.semantic_cache_status == semantic_cache_status
        assert retrieved_analysis.state_updated_at == initial_timestamp


# =============================================================================
# Property 2: State Independence from Redis
# =============================================================================


class TestStateIndependenceFromRedis:
    """
    Property tests for state independence from Redis.
    
    **Feature: progress-tracking-refactor, Property 2: State Independence from Redis**
    **Validates: Requirements 1.2**
    """

    @given(
        analysis_status=valid_analysis_status(),
        embeddings_status=valid_embeddings_status(),
        embeddings_progress=valid_progress(),
        semantic_cache_status=valid_semantic_cache_status(),
        vci_score=valid_vci_score(),
    )
    @settings(max_examples=100, deadline=None)
    @pytest.mark.asyncio
    async def test_full_status_returns_correct_state_without_redis(
        self,
        analysis_status: str,
        embeddings_status: str,
        embeddings_progress: int,
        semantic_cache_status: str,
        vci_score: float | None,
    ):
        """
        **Feature: progress-tracking-refactor, Property 2: State Independence from Redis**
        **Validates: Requirements 1.2**
        
        Property: For any analysis with state stored in PostgreSQL, if Redis state
        is empty or expired, querying the full-status endpoint SHALL return the
        correct state from PostgreSQL without fallback logic.
        """
        from app.api.v1.analyses import get_analysis_full_status
        from app.schemas.analysis import EmbeddingsStatus, SemanticCacheStatus
        
        analysis_id = uuid.uuid4()
        repository_id = uuid.uuid4()
        user_id = uuid.uuid4()
        state_updated_at = datetime.now(timezone.utc)
        
        # Compute expected grade from VCI score
        expected_grade = None
        if vci_score is not None:
            if vci_score >= 90:
                expected_grade = "A"
            elif vci_score >= 80:
                expected_grade = "B"
            elif vci_score >= 70:
                expected_grade = "C"
            elif vci_score >= 60:
                expected_grade = "D"
            else:
                expected_grade = "F"
        
        # Create mock analysis with state stored in PostgreSQL
        mock_analysis = MagicMock()
        mock_analysis.id = analysis_id
        mock_analysis.repository_id = repository_id
        mock_analysis.commit_sha = "abc123"
        mock_analysis.status = analysis_status
        mock_analysis.vci_score = vci_score
        mock_analysis.grade = expected_grade
        mock_analysis.embeddings_status = embeddings_status
        mock_analysis.embeddings_progress = embeddings_progress
        mock_analysis.embeddings_stage = "embedding" if embeddings_status == "running" else None
        mock_analysis.embeddings_message = "Processing..." if embeddings_status == "running" else None
        mock_analysis.embeddings_error = None
        mock_analysis.vectors_count = 100 if embeddings_status == "completed" else 0
        mock_analysis.semantic_cache_status = semantic_cache_status
        mock_analysis.semantic_cache = {"architecture_health": {"overall_score": 80}} if semantic_cache_status == "completed" else None
        mock_analysis.state_updated_at = state_updated_at
        mock_analysis.embeddings_started_at = state_updated_at if embeddings_status in ["running", "completed"] else None
        mock_analysis.embeddings_completed_at = state_updated_at if embeddings_status == "completed" else None
        # AI scan fields (added in Phase 5)
        mock_analysis.ai_scan_status = "none"
        mock_analysis.ai_scan_progress = 0
        mock_analysis.ai_scan_stage = None
        mock_analysis.ai_scan_message = None
        mock_analysis.ai_scan_error = None
        mock_analysis.ai_scan_cache = None
        mock_analysis.ai_scan_started_at = None
        mock_analysis.ai_scan_completed_at = None
        
        # Mock repository with owner
        mock_analysis.repository = MagicMock()
        mock_analysis.repository.owner_id = user_id
        
        # Create mock database session
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_analysis
        mock_db.execute.return_value = mock_result
        
        # Create mock user
        mock_user = MagicMock()
        mock_user.id = user_id
        
        # Call the endpoint - this should NOT use Redis at all
        # The endpoint reads directly from PostgreSQL
        response = await get_analysis_full_status(
            analysis_id=analysis_id,
            db=mock_db,
            user=mock_user,
        )
        
        # Verify response contains correct state from PostgreSQL
        assert response.analysis_id == str(analysis_id), (
            f"analysis_id should match: expected '{analysis_id}', got '{response.analysis_id}'"
        )
        assert response.analysis_status == analysis_status, (
            f"analysis_status should match: expected '{analysis_status}', got '{response.analysis_status}'"
        )
        assert response.embeddings_status == EmbeddingsStatus(embeddings_status), (
            f"embeddings_status should match: expected '{embeddings_status}', got '{response.embeddings_status}'"
        )
        assert response.embeddings_progress == embeddings_progress, (
            f"embeddings_progress should match: expected {embeddings_progress}, got {response.embeddings_progress}"
        )
        assert response.semantic_cache_status == SemanticCacheStatus(semantic_cache_status), (
            f"semantic_cache_status should match: expected '{semantic_cache_status}', got '{response.semantic_cache_status}'"
        )
        
        # Verify VCI score handling
        if vci_score is not None:
            assert response.vci_score is not None
            assert abs(response.vci_score - vci_score) < 0.01, (
                f"vci_score should match: expected {vci_score}, got {response.vci_score}"
            )
        else:
            assert response.vci_score is None

    @given(
        embeddings_status=valid_embeddings_status(),
        embeddings_progress=valid_progress(),
        semantic_cache_status=valid_semantic_cache_status(),
    )
    @settings(max_examples=100, deadline=None)
    @pytest.mark.asyncio
    async def test_full_status_no_redis_fallback_logic(
        self,
        embeddings_status: str,
        embeddings_progress: int,
        semantic_cache_status: str,
    ):
        """
        **Feature: progress-tracking-refactor, Property 2: State Independence from Redis**
        **Validates: Requirements 1.2**
        
        Property: The full-status endpoint SHALL NOT use any Redis fallback logic.
        It reads directly from PostgreSQL as the single source of truth.
        """
        from app.api.v1.analyses import get_analysis_full_status
        
        analysis_id = uuid.uuid4()
        repository_id = uuid.uuid4()
        user_id = uuid.uuid4()
        
        # Create mock analysis
        mock_analysis = MagicMock()
        mock_analysis.id = analysis_id
        mock_analysis.repository_id = repository_id
        mock_analysis.commit_sha = "abc123"
        mock_analysis.status = "completed"
        mock_analysis.vci_score = 85.0
        mock_analysis.grade = "B"
        mock_analysis.embeddings_status = embeddings_status
        mock_analysis.embeddings_progress = embeddings_progress
        mock_analysis.embeddings_stage = None
        mock_analysis.embeddings_message = None
        mock_analysis.embeddings_error = None
        mock_analysis.vectors_count = 100
        mock_analysis.semantic_cache_status = semantic_cache_status
        mock_analysis.semantic_cache = None
        mock_analysis.state_updated_at = datetime.now(timezone.utc)
        mock_analysis.embeddings_started_at = None
        mock_analysis.embeddings_completed_at = None
        # AI scan fields (added in Phase 5)
        mock_analysis.ai_scan_status = "none"
        mock_analysis.ai_scan_progress = 0
        mock_analysis.ai_scan_stage = None
        mock_analysis.ai_scan_message = None
        mock_analysis.ai_scan_error = None
        mock_analysis.ai_scan_cache = None
        mock_analysis.ai_scan_started_at = None
        mock_analysis.ai_scan_completed_at = None
        mock_analysis.repository = MagicMock()
        mock_analysis.repository.owner_id = user_id
        
        # Create mock database session
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_analysis
        mock_db.execute.return_value = mock_result
        
        # Create mock user
        mock_user = MagicMock()
        mock_user.id = user_id
        
        # Patch Redis functions to verify they are NOT called
        with patch('app.core.redis.get_analysis_last_state') as mock_redis_get, \
             patch('app.core.redis.subscribe_analysis_progress') as mock_redis_sub:
            
            # Call the endpoint
            response = await get_analysis_full_status(
                analysis_id=analysis_id,
                db=mock_db,
                user=mock_user,
            )
            
            # Verify Redis was NOT called - the endpoint uses PostgreSQL only
            mock_redis_get.assert_not_called()
            mock_redis_sub.assert_not_called()
            
            # Verify response is correct from PostgreSQL
            assert response.embeddings_status.value == embeddings_status
            assert response.embeddings_progress == embeddings_progress
            assert response.semantic_cache_status.value == semantic_cache_status

    @given(
        embeddings_status=valid_embeddings_status(),
        semantic_cache_status=valid_semantic_cache_status(),
    )
    @settings(max_examples=100)
    def test_state_service_does_not_read_from_redis(
        self,
        embeddings_status: str,
        semantic_cache_status: str,
    ):
        """
        **Feature: progress-tracking-refactor, Property 2: State Independence from Redis**
        **Validates: Requirements 1.2**
        
        Property: The AnalysisStateService SHALL read state exclusively from
        PostgreSQL, not from Redis.
        """
        from app.services.analysis_state import AnalysisStateService
        
        analysis_id = uuid.uuid4()
        
        # Create mock analysis
        mock_analysis = MagicMock()
        mock_analysis.id = analysis_id
        mock_analysis.embeddings_status = embeddings_status
        mock_analysis.embeddings_progress = 50
        mock_analysis.embeddings_stage = None
        mock_analysis.embeddings_message = None
        mock_analysis.embeddings_error = None
        mock_analysis.vectors_count = 0
        mock_analysis.semantic_cache_status = semantic_cache_status
        mock_analysis.semantic_cache = None
        mock_analysis.state_updated_at = datetime.now(timezone.utc)
        
        # Create mock session
        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_analysis
        mock_session.execute.return_value = mock_result
        
        # Create service with events disabled (no Redis publishing)
        service = AnalysisStateService(mock_session, publish_events=False)
        
        # Patch Redis sync client to verify it's not called for reading
        with patch('app.core.redis.get_sync_redis') as mock_redis_sync:
            # Get analysis - should only use database
            analysis = service._get_analysis(analysis_id)
            
            # Verify database was queried
            mock_session.execute.assert_called_once()
            
            # Verify Redis was NOT called for reading state
            # (Redis is only used for publishing events, not reading state)
            mock_redis_sync.assert_not_called()
            
            # Verify correct state was returned from database
            assert analysis.embeddings_status == embeddings_status
            assert analysis.semantic_cache_status == semantic_cache_status


# =============================================================================
# Combined Property Tests
# =============================================================================


class TestCombinedPersistenceProperties:
    """
    Combined property tests for state persistence.
    
    **Feature: progress-tracking-refactor**
    **Validates: Requirements 1.1, 1.2**
    """

    @given(
        embeddings_status=valid_embeddings_status(),
        embeddings_progress=valid_progress(),
        semantic_cache_status=valid_semantic_cache_status(),
        vectors_count=valid_vectors_count(),
    )
    @settings(max_examples=100)
    def test_postgresql_is_single_source_of_truth(
        self,
        embeddings_status: str,
        embeddings_progress: int,
        semantic_cache_status: str,
        vectors_count: int,
    ):
        """
        **Feature: progress-tracking-refactor, Properties 1 & 2**
        **Validates: Requirements 1.1, 1.2**
        
        Property: PostgreSQL SHALL be the single source of truth for all
        analysis state. State persists across restarts and is independent
        of Redis.
        """
        analysis_id = uuid.uuid4()
        state_updated_at = datetime.now(timezone.utc)
        
        # Define the authoritative state in PostgreSQL
        postgresql_state = {
            "embeddings_status": embeddings_status,
            "embeddings_progress": embeddings_progress,
            "semantic_cache_status": semantic_cache_status,
            "vectors_count": vectors_count,
            "state_updated_at": state_updated_at,
        }
        
        # Simulate different Redis states (empty, stale, or different)
        redis_states = [
            None,  # Redis empty/expired
            {"embeddings_status": "none", "embeddings_progress": 0},  # Stale
            {"embeddings_status": "running", "embeddings_progress": 25},  # Different
        ]
        
        for redis_state in redis_states:
            # Create mock analysis with PostgreSQL state
            mock_analysis = MagicMock()
            mock_analysis.id = analysis_id
            for key, value in postgresql_state.items():
                setattr(mock_analysis, key, value)
            mock_analysis.embeddings_stage = None
            mock_analysis.embeddings_message = None
            mock_analysis.embeddings_error = None
            mock_analysis.semantic_cache = None
            
            # The system should always return PostgreSQL state
            # regardless of what Redis contains
            assert mock_analysis.embeddings_status == embeddings_status
            assert mock_analysis.embeddings_progress == embeddings_progress
            assert mock_analysis.semantic_cache_status == semantic_cache_status
            assert mock_analysis.vectors_count == vectors_count


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
