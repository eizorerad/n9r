"""Property-based tests for Embeddings → Semantic Cache chain.

Tests that verify the correct chaining behavior in the parallel analysis pipeline:
- Semantic Cache is dispatched after Embeddings completes
- AI Scan is NOT dispatched from Semantic Cache (it runs in parallel from API)

**Feature: parallel-analysis-pipeline**
**Validates: Requirements 6.1, 6.2, 6.3**
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch, call

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st


# =============================================================================
# Hypothesis Strategies
# =============================================================================


def valid_uuid_str() -> st.SearchStrategy[str]:
    """Generate valid UUID strings."""
    return st.uuids().map(str)


@st.composite
def valid_semantic_cache_data(draw) -> dict:
    """Generate valid semantic cache data."""
    return {
        "clusters": draw(st.lists(
            st.fixed_dictionaries({
                "id": st.integers(min_value=0, max_value=100),
                "name": st.text(min_size=3, max_size=20, alphabet="abcdefghijklmnopqrstuvwxyz"),
            }),
            min_size=0,
            max_size=5,
        )),
        "health_score": draw(st.integers(min_value=0, max_value=100)),
    }


def valid_ai_scan_status() -> st.SearchStrategy[str]:
    """Generate valid AI scan status values."""
    return st.sampled_from(["none", "pending", "running", "completed", "failed", "skipped"])


# =============================================================================
# Test Fixtures
# =============================================================================


def create_mock_analysis(
    analysis_id: uuid.UUID | None = None,
    embeddings_status: str = "completed",
    semantic_cache_status: str = "computing",
    semantic_cache: dict | None = None,
    ai_scan_status: str = "pending",  # In parallel pipeline, AI scan is already pending
) -> MagicMock:
    """Create a mock Analysis object for testing."""
    mock = MagicMock()
    mock.id = analysis_id or uuid.uuid4()
    mock.embeddings_status = embeddings_status
    mock.semantic_cache_status = semantic_cache_status
    mock.semantic_cache = semantic_cache
    mock.ai_scan_status = ai_scan_status
    mock.ai_scan_stage = None
    mock.ai_scan_message = None
    mock.state_updated_at = datetime.now(timezone.utc)
    return mock


def create_mock_session(mock_analysis: MagicMock) -> MagicMock:
    """Create a mock SQLAlchemy session."""
    mock_session = MagicMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_analysis
    mock_session.execute.return_value = mock_result
    return mock_session


# =============================================================================
# Property Tests: Embeddings → Semantic Cache Chain
# =============================================================================


class TestEmbeddingsSemanticCacheChainProperty:
    """
    Property tests for Embeddings → Semantic Cache chain.
    
    **Feature: parallel-analysis-pipeline, Property 10: Embeddings → Semantic Cache Chain**
    **Validates: Requirements 6.1, 6.2, 6.3**
    """

    @given(
        repository_id=valid_uuid_str(),
        analysis_id=valid_uuid_str(),
        vectors_count=st.integers(min_value=5, max_value=1000),
    )
    @settings(max_examples=100, deadline=None)
    def test_embeddings_completion_dispatches_semantic_cache(
        self,
        repository_id: str,
        analysis_id: str,
        vectors_count: int,
    ):
        """
        Property: For any successful embeddings completion with >= 5 vectors,
        the compute_semantic_cache task SHALL be dispatched.
        
        **Feature: parallel-analysis-pipeline, Property 10: Embeddings → Semantic Cache Chain**
        **Validates: Requirements 6.1**
        """
        # Track if compute_semantic_cache.delay was called
        semantic_cache_dispatched = False
        dispatch_args = {}
        
        def mock_semantic_cache_delay(**kwargs):
            nonlocal semantic_cache_dispatched, dispatch_args
            semantic_cache_dispatched = True
            dispatch_args = kwargs
        
        # Mock all external dependencies
        with patch('app.workers.embeddings._update_embeddings_state') as mock_update_state, \
             patch('app.workers.embeddings.publish_embedding_progress') as mock_publish, \
             patch('app.workers.embeddings.get_code_chunker') as mock_chunker, \
             patch('app.services.llm_gateway.get_llm_gateway') as mock_llm, \
             patch('app.workers.embeddings.get_qdrant_client') as mock_qdrant, \
             patch('app.workers.embeddings.compute_semantic_cache') as mock_semantic_cache:
            
            # Setup mock chunker
            mock_chunker_instance = MagicMock()
            mock_chunker_instance.chunk_file.return_value = []
            mock_chunker.return_value = mock_chunker_instance
            
            # Setup mock LLM
            mock_llm_instance = MagicMock()
            mock_llm.return_value = mock_llm_instance
            
            # Setup mock Qdrant
            mock_qdrant_instance = MagicMock()
            mock_qdrant.return_value = mock_qdrant_instance
            
            # Setup mock semantic cache task
            mock_semantic_cache.delay = mock_semantic_cache_delay
            
            from app.workers.embeddings import generate_embeddings
            
            # Patch the task's update_state method
            generate_embeddings.update_state = MagicMock()
            
            # Create mock files that will generate enough vectors
            mock_files = [
                {"path": f"file{i}.py", "content": f"def func{i}(): pass\n" * 20}
                for i in range(vectors_count // 5 + 1)
            ]
            
            # Create mock chunks that will result in vectors
            mock_chunks = []
            for i in range(vectors_count):
                chunk = MagicMock()
                chunk.file_path = f"file{i % 10}.py"
                chunk.name = f"func{i}"
                chunk.chunk_type = "function"
                chunk.docstring = None
                chunk.content = f"def func{i}(): pass"
                chunk.language = "python"
                chunk.line_start = i * 10
                chunk.line_end = i * 10 + 5
                chunk.parent_name = None
                chunk.token_estimate = 50
                chunk.level = 0
                chunk.qualified_name = f"func{i}"
                chunk.cyclomatic_complexity = 1
                chunk.line_count = 5
                mock_chunks.append(chunk)
            
            mock_chunker_instance.chunk_file.return_value = mock_chunks[:5]  # Return 5 chunks per file
            
            # Mock embedding generation
            async def mock_embed(texts):
                return [[0.1] * 1536 for _ in texts]
            mock_llm_instance.embed = mock_embed
            
            # Call the task
            result = generate_embeddings.apply(
                args=[repository_id],
                kwargs={
                    "files": mock_files,
                    "analysis_id": analysis_id,
                },
            )
            
            # Verify semantic cache was dispatched
            assert semantic_cache_dispatched, (
                f"compute_semantic_cache.delay() was not called after embeddings completion\n"
                f"vectors_count={vectors_count}"
            )
            
            # Verify correct arguments were passed
            assert dispatch_args.get("repository_id") == repository_id, (
                f"Expected repository_id={repository_id}, got {dispatch_args.get('repository_id')}"
            )
            assert dispatch_args.get("analysis_id") == analysis_id, (
                f"Expected analysis_id={analysis_id}, got {dispatch_args.get('analysis_id')}"
            )

    @given(
        repository_id=valid_uuid_str(),
        analysis_id=valid_uuid_str(),
        cache_data=valid_semantic_cache_data(),
        ai_scan_status=valid_ai_scan_status(),
    )
    @settings(max_examples=100, deadline=None)
    def test_semantic_cache_completion_does_not_dispatch_ai_scan(
        self,
        repository_id: str,
        analysis_id: str,
        cache_data: dict,
        ai_scan_status: str,
    ):
        """
        Property: For any semantic cache completion, the run_ai_scan task
        SHALL NOT be dispatched from compute_semantic_cache.
        
        In the parallel analysis pipeline, AI Scan is dispatched directly
        from the API endpoint, not from Semantic Cache.
        
        **Feature: parallel-analysis-pipeline, Property 10: Embeddings → Semantic Cache Chain**
        **Validates: Requirements 6.3**
        """
        # Track if run_ai_scan.delay was called
        ai_scan_dispatched = False
        
        def mock_ai_scan_delay(**kwargs):
            nonlocal ai_scan_dispatched
            ai_scan_dispatched = True
        
        # Create mock analysis with the given ai_scan_status
        mock_analysis = create_mock_analysis(
            analysis_id=uuid.UUID(analysis_id),
            semantic_cache_status="computing",
            ai_scan_status=ai_scan_status,
        )
        mock_session = create_mock_session(mock_analysis)
        
        # Mock all external dependencies
        with patch('app.workers.embeddings._get_db_session') as mock_get_session, \
             patch('app.services.cluster_analyzer.get_cluster_analyzer') as mock_analyzer, \
             patch('app.workers.ai_scan.run_ai_scan') as mock_ai_scan, \
             patch('app.core.redis.publish_analysis_event'):
            
            # Setup mock session context manager
            mock_get_session.return_value.__enter__ = MagicMock(return_value=mock_session)
            mock_get_session.return_value.__exit__ = MagicMock(return_value=False)
            
            # Setup mock cluster analyzer
            mock_health = MagicMock()
            mock_health.to_cacheable_dict.return_value = cache_data
            mock_analyzer_instance = MagicMock()
            
            async def mock_analyze(repo_id):
                return mock_health
            mock_analyzer_instance.analyze = mock_analyze
            mock_analyzer.return_value = mock_analyzer_instance
            
            # Setup mock AI scan task
            mock_ai_scan.delay = mock_ai_scan_delay
            
            from app.workers.embeddings import compute_semantic_cache
            
            # Patch the task's update_state method
            compute_semantic_cache.update_state = MagicMock()
            
            # Call the task
            result = compute_semantic_cache.apply(
                args=[repository_id, analysis_id],
            )
            
            # Verify AI scan was NOT dispatched
            assert not ai_scan_dispatched, (
                f"run_ai_scan.delay() was called from compute_semantic_cache, "
                f"but it should NOT be (AI Scan runs in parallel from API)\n"
                f"ai_scan_status={ai_scan_status}"
            )

    @given(
        repository_id=valid_uuid_str(),
        analysis_id=valid_uuid_str(),
    )
    @settings(max_examples=50, deadline=None)
    def test_embeddings_failure_does_not_dispatch_semantic_cache(
        self,
        repository_id: str,
        analysis_id: str,
    ):
        """
        Property: For any embeddings failure, the compute_semantic_cache task
        SHALL NOT be dispatched.
        
        **Feature: parallel-analysis-pipeline, Property 10: Embeddings → Semantic Cache Chain**
        **Validates: Requirements 6.2**
        """
        # Track if compute_semantic_cache.delay was called
        semantic_cache_dispatched = False
        
        def mock_semantic_cache_delay(**kwargs):
            nonlocal semantic_cache_dispatched
            semantic_cache_dispatched = True
        
        # Mock all external dependencies to simulate failure
        with patch('app.workers.embeddings._update_embeddings_state') as mock_update_state, \
             patch('app.workers.embeddings.publish_embedding_progress') as mock_publish, \
             patch('app.workers.embeddings.get_code_chunker') as mock_chunker, \
             patch('app.workers.embeddings.compute_semantic_cache') as mock_semantic_cache:
            
            # Setup mock chunker to raise an exception
            mock_chunker.side_effect = Exception("Simulated chunker failure")
            
            # Setup mock semantic cache task
            mock_semantic_cache.delay = mock_semantic_cache_delay
            
            from app.workers.embeddings import generate_embeddings
            
            # Patch the task's update_state method
            generate_embeddings.update_state = MagicMock()
            
            # Call the task and expect it to raise
            with pytest.raises(Exception):
                generate_embeddings.apply(
                    args=[repository_id],
                    kwargs={
                        "files": [{"path": "test.py", "content": "def test(): pass"}],
                        "analysis_id": analysis_id,
                    },
                ).get()
            
            # Verify semantic cache was NOT dispatched
            assert not semantic_cache_dispatched, (
                f"compute_semantic_cache.delay() was called after embeddings failure, "
                f"but it should NOT be"
            )


# =============================================================================
# Property Tests: complete_semantic_cache State Service Method
# =============================================================================


class TestCompleteSemanticCacheNoAIScanTrigger:
    """
    Property tests verifying complete_semantic_cache does not auto-trigger AI scan.
    
    **Feature: parallel-analysis-pipeline**
    **Validates: Requirements 6.3**
    """

    @given(
        cache_data=valid_semantic_cache_data(),
        initial_ai_scan_status=valid_ai_scan_status(),
    )
    @settings(max_examples=100)
    def test_complete_semantic_cache_preserves_ai_scan_status(
        self,
        cache_data: dict,
        initial_ai_scan_status: str,
    ):
        """
        Property: For any semantic cache completion, the ai_scan_status
        SHALL NOT be modified by complete_semantic_cache.
        
        In the parallel pipeline, AI scan status is set by the API endpoint
        and should not be changed by semantic cache completion.
        
        **Feature: parallel-analysis-pipeline**
        **Validates: Requirements 6.3**
        """
        from app.services.analysis_state import AnalysisStateService
        
        analysis_id = uuid.uuid4()
        
        # Create mock analysis with semantic_cache_status='computing'
        mock_analysis = create_mock_analysis(
            analysis_id=analysis_id,
            semantic_cache_status="computing",
            ai_scan_status=initial_ai_scan_status,
        )
        mock_session = create_mock_session(mock_analysis)
        
        with patch('app.core.redis.publish_analysis_event'):
            service = AnalysisStateService(mock_session, publish_events=True)
            
            # Complete semantic cache
            service.complete_semantic_cache(analysis_id, cache_data)
            
            # Verify semantic cache is completed
            assert mock_analysis.semantic_cache_status == "completed", (
                f"Expected semantic_cache_status='completed', "
                f"got '{mock_analysis.semantic_cache_status}'"
            )
            
            # Verify AI scan status was NOT changed
            assert mock_analysis.ai_scan_status == initial_ai_scan_status, (
                f"AI scan status was modified by complete_semantic_cache!\n"
                f"Expected: {initial_ai_scan_status}\n"
                f"Got: {mock_analysis.ai_scan_status}\n"
                f"In parallel pipeline, AI scan status should not be changed by semantic cache"
            )

    @given(cache_data=valid_semantic_cache_data())
    @settings(max_examples=50)
    def test_complete_semantic_cache_does_not_set_ai_scan_pending(
        self,
        cache_data: dict,
    ):
        """
        Property: When ai_scan_status is 'none', complete_semantic_cache
        SHALL NOT change it to 'pending'.
        
        This is the key change for parallel pipeline - previously it would
        auto-trigger AI scan, now it should not.
        
        **Feature: parallel-analysis-pipeline**
        **Validates: Requirements 6.3**
        """
        from app.services.analysis_state import AnalysisStateService
        
        analysis_id = uuid.uuid4()
        
        # Create mock analysis with ai_scan_status='none'
        mock_analysis = create_mock_analysis(
            analysis_id=analysis_id,
            semantic_cache_status="computing",
            ai_scan_status="none",  # This is the key case
        )
        mock_session = create_mock_session(mock_analysis)
        
        with patch('app.core.redis.publish_analysis_event'):
            service = AnalysisStateService(mock_session, publish_events=True)
            
            # Complete semantic cache
            service.complete_semantic_cache(analysis_id, cache_data)
            
            # Verify AI scan status is still 'none' (not auto-triggered to 'pending')
            assert mock_analysis.ai_scan_status == "none", (
                f"AI scan status was changed from 'none' to '{mock_analysis.ai_scan_status}'!\n"
                f"In parallel pipeline, complete_semantic_cache should NOT auto-trigger AI scan"
            )


# =============================================================================
# Unit Tests: compute_semantic_cache Return Value
# =============================================================================


class TestComputeSemanticCacheReturnValue:
    """
    Unit tests for compute_semantic_cache task return value.
    
    **Feature: parallel-analysis-pipeline**
    **Validates: Requirements 6.3**
    """

    def test_compute_semantic_cache_does_not_return_ai_scan_queued(self):
        """
        Test that compute_semantic_cache return value does not include ai_scan_queued.
        
        In the parallel pipeline, AI scan is not queued from semantic cache,
        so the return value should not include this field.
        """
        repository_id = str(uuid.uuid4())
        analysis_id = str(uuid.uuid4())
        
        # Start with semantic_cache_status="pending" so the task can transition to "computing"
        mock_analysis = create_mock_analysis(
            analysis_id=uuid.UUID(analysis_id),
            semantic_cache_status="pending",
            ai_scan_status="pending",
        )
        mock_session = create_mock_session(mock_analysis)
        
        cache_data = {"clusters": [], "health_score": 85}
        
        with patch('app.workers.embeddings._get_db_session') as mock_get_session, \
             patch('app.services.cluster_analyzer.get_cluster_analyzer') as mock_analyzer, \
             patch('app.core.redis.publish_analysis_event'):
            
            # Setup mock session context manager
            mock_get_session.return_value.__enter__ = MagicMock(return_value=mock_session)
            mock_get_session.return_value.__exit__ = MagicMock(return_value=False)
            
            # Setup mock cluster analyzer
            mock_health = MagicMock()
            mock_health.to_cacheable_dict.return_value = cache_data
            mock_analyzer_instance = MagicMock()
            
            async def mock_analyze(repo_id):
                return mock_health
            mock_analyzer_instance.analyze = mock_analyze
            mock_analyzer.return_value = mock_analyzer_instance
            
            from app.workers.embeddings import compute_semantic_cache
            
            # Patch the task's update_state method
            compute_semantic_cache.update_state = MagicMock()
            
            # Call the task
            async_result = compute_semantic_cache.apply(
                args=[repository_id, analysis_id],
            )
            result = async_result.result
            
            # Verify ai_scan_queued is NOT in the result
            assert "ai_scan_queued" not in result, (
                f"compute_semantic_cache should not return 'ai_scan_queued' field\n"
                f"Result: {result}"
            )
            
            # Verify expected fields are present
            assert result["status"] == "completed"
            assert result["repository_id"] == repository_id
            assert result["analysis_id"] == analysis_id
