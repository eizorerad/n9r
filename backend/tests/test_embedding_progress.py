"""Tests for embedding progress tracking (Solution 2).

Tests the two-phase progress system where:
1. VCI analysis completes quickly
2. Embeddings run in background with progress tracking
3. Frontend polls for progress and auto-refreshes when complete
"""

import json
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from uuid import uuid4

from app.core.redis import (
    publish_embedding_progress,
    get_embedding_channel,
    get_embedding_state_key,
)


class TestEmbeddingProgressTracking:
    """Test Redis-based embedding progress tracking."""
    
    def test_publish_embedding_progress(self):
        """Test publishing embedding progress to Redis."""
        repo_id = str(uuid4())
        
        with patch("app.core.redis.get_sync_redis_context") as mock_context:
            mock_redis = MagicMock()
            mock_context.return_value.__enter__ = MagicMock(return_value=mock_redis)
            mock_context.return_value.__exit__ = MagicMock(return_value=False)
            
            publish_embedding_progress(
                repository_id=repo_id,
                stage="initializing",
                progress=5,
                message="Starting embedding generation...",
                status="running",
                chunks_processed=0,
                vectors_stored=0,
            )
            
            # Verify setex was called with correct key and TTL
            mock_redis.setex.assert_called_once()
            call_args = mock_redis.setex.call_args
            assert f"embedding:state:{repo_id}" == call_args[0][0]
            assert call_args[0][1] == 3600  # TTL
            
            # Verify payload
            payload = json.loads(call_args[0][2])
            assert payload["repository_id"] == repo_id
            assert payload["stage"] == "initializing"
            assert payload["progress"] == 5
            assert payload["status"] == "running"
            
            # Verify publish was called
            mock_redis.publish.assert_called_once()
    
    def test_embedding_progress_flow(self):
        """Test complete embedding progress flow."""
        repo_id = str(uuid4())
        
        with patch("app.core.redis.get_sync_redis_context") as mock_context:
            mock_redis = MagicMock()
            mock_context.return_value.__enter__ = MagicMock(return_value=mock_redis)
            mock_context.return_value.__exit__ = MagicMock(return_value=False)
            
            # Step 1: Queued
            publish_embedding_progress(
                repository_id=repo_id,
                stage="queued",
                progress=0,
                message="Queued for processing",
                status="pending",
            )
            
            # Step 2: Chunking
            publish_embedding_progress(
                repository_id=repo_id,
                stage="chunking",
                progress=20,
                message="Created 50 chunks",
                status="running",
                chunks_processed=50,
            )
            
            # Step 3: Embedding
            publish_embedding_progress(
                repository_id=repo_id,
                stage="embedding",
                progress=60,
                message="Embedding batch 3/5...",
                status="running",
                chunks_processed=50,
                vectors_stored=30,
            )
            
            # Step 4: Completed
            publish_embedding_progress(
                repository_id=repo_id,
                stage="completed",
                progress=100,
                message="Generated 50 embeddings",
                status="completed",
                chunks_processed=50,
                vectors_stored=50,
            )
            
            # Verify 4 calls were made
            assert mock_redis.setex.call_count == 4
            assert mock_redis.publish.call_count == 4
            
            # Verify final state payload
            final_call = mock_redis.setex.call_args_list[-1]
            final_payload = json.loads(final_call[0][2])
            assert final_payload["status"] == "completed"
            assert final_payload["progress"] == 100
            assert final_payload["chunks_processed"] == 50
            assert final_payload["vectors_stored"] == 50
    
    def test_embedding_error_state(self):
        """Test embedding error handling."""
        repo_id = str(uuid4())
        
        with patch("app.core.redis.get_sync_redis_context") as mock_context:
            mock_redis = MagicMock()
            mock_context.return_value.__enter__ = MagicMock(return_value=mock_redis)
            mock_context.return_value.__exit__ = MagicMock(return_value=False)
            
            publish_embedding_progress(
                repository_id=repo_id,
                stage="error",
                progress=0,
                message="Failed to generate embeddings: Connection timeout",
                status="error",
            )
            
            # Verify error payload
            call_args = mock_redis.setex.call_args
            payload = json.loads(call_args[0][2])
            assert payload["status"] == "error"
            assert "Connection timeout" in payload["message"]
    
    def test_redis_key_generation(self):
        """Test Redis key and channel name generation."""
        repo_id = "test-repo-123"
        
        channel = get_embedding_channel(repo_id)
        state_key = get_embedding_state_key(repo_id)
        
        assert channel == "embedding:progress:test-repo-123"
        assert state_key == "embedding:state:test-repo-123"


class TestEmbeddingStatusAPI:
    """Test the embedding status API endpoint."""
    
    def test_embedding_status_response_model(self):
        """Test EmbeddingStatusResponse model."""
        from app.api.v1.semantic import EmbeddingStatusResponse
        
        response = EmbeddingStatusResponse(
            repository_id="test-repo",
            status="running",
            stage="embedding",
            progress=45,
            message="Embedding batch 2/4...",
            chunks_processed=80,
            vectors_stored=40,
        )
        
        assert response.repository_id == "test-repo"
        assert response.status == "running"
        assert response.stage == "embedding"
        assert response.progress == 45
        assert response.chunks_processed == 80
        assert response.vectors_stored == 40
    
    def test_embedding_status_response_all_fields(self):
        """Test EmbeddingStatusResponse with all fields."""
        from app.api.v1.semantic import EmbeddingStatusResponse
        
        response = EmbeddingStatusResponse(
            repository_id="test-repo",
            status="none",
            stage=None,
            progress=0,
            message=None,
            chunks_processed=0,
            vectors_stored=0,
        )
        
        assert response.repository_id == "test-repo"
        assert response.status == "none"
        assert response.stage is None
        assert response.progress == 0
        assert response.message is None
        assert response.chunks_processed == 0
        assert response.vectors_stored == 0


class TestGetEmbeddingState:
    """Test the get_embedding_state async function."""
    
    @pytest.mark.asyncio
    async def test_get_embedding_state_returns_data(self):
        """Test get_embedding_state returns parsed JSON data."""
        from app.core.redis import get_embedding_state
        
        repo_id = str(uuid4())
        expected_data = {
            "repository_id": repo_id,
            "stage": "embedding",
            "progress": 50,
            "message": "Processing...",
            "status": "running",
            "chunks_processed": 100,
            "vectors_stored": 50,
        }
        
        # Mock the async Redis client
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=json.dumps(expected_data))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        
        with patch("app.core.redis.aioredis.Redis", return_value=mock_client):
            result = await get_embedding_state(repo_id)
        
        assert result == expected_data
        assert result["progress"] == 50
        assert result["status"] == "running"
    
    @pytest.mark.asyncio
    async def test_get_embedding_state_returns_none(self):
        """Test get_embedding_state returns None when no state exists."""
        from app.core.redis import get_embedding_state
        
        repo_id = str(uuid4())
        
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=None)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        
        with patch("app.core.redis.aioredis.Redis", return_value=mock_client):
            result = await get_embedding_state(repo_id)
        
        assert result is None


class TestEmbeddingsWorkerProgress:
    """Test embedding progress integration in the embeddings worker."""
    
    def test_embeddings_worker_imports(self):
        """Test that embeddings worker can import progress functions."""
        from app.workers.embeddings import generate_embeddings
        from app.core.redis import publish_embedding_progress
        
        assert generate_embeddings is not None
        assert publish_embedding_progress is not None
    
    def test_progress_publishing_with_all_fields(self):
        """Test publishing progress with all fields populated."""
        repo_id = str(uuid4())
        
        with patch("app.core.redis.get_sync_redis_context") as mock_context:
            mock_redis = MagicMock()
            mock_context.return_value.__enter__ = MagicMock(return_value=mock_redis)
            mock_context.return_value.__exit__ = MagicMock(return_value=False)
            
            publish_embedding_progress(
                repository_id=repo_id,
                stage="embedding",
                progress=75,
                message="Embedding batch 4/5...",
                status="running",
                chunks_processed=100,
                vectors_stored=75,
            )
            
            call_args = mock_redis.setex.call_args
            payload = json.loads(call_args[0][2])
            
            assert payload["repository_id"] == repo_id
            assert payload["stage"] == "embedding"
            assert payload["progress"] == 75
            assert payload["message"] == "Embedding batch 4/5..."
            assert payload["status"] == "running"
            assert payload["chunks_processed"] == 100
            assert payload["vectors_stored"] == 75


class TestFrontendPollingBehavior:
    """Test frontend polling behavior simulation."""
    
    def test_frontend_polling_simulation(self):
        """Simulate how frontend would poll for embedding status."""
        repo_id = str(uuid4())
        
        with patch("app.core.redis.get_sync_redis_context") as mock_context:
            mock_redis = MagicMock()
            mock_context.return_value.__enter__ = MagicMock(return_value=mock_redis)
            mock_context.return_value.__exit__ = MagicMock(return_value=False)
            
            # Simulate embedding progress over time
            progress_states = [
                ("pending", 0, "Queued for processing"),
                ("running", 5, "Starting embedding generation..."),
                ("running", 20, "Created 50 chunks"),
                ("running", 45, "Embedding batch 2/4..."),
                ("running", 70, "Embedding batch 3/4..."),
                ("running", 90, "Storing vectors in Qdrant..."),
                ("completed", 100, "Generated 50 embeddings"),
            ]
            
            # Publish each state
            for status, progress, message in progress_states:
                publish_embedding_progress(
                    repository_id=repo_id,
                    stage="embedding" if status == "running" else status,
                    progress=progress,
                    message=message,
                    status=status,
                    chunks_processed=50 if progress > 20 else 0,
                    vectors_stored=50 if status == "completed" else int(progress * 0.5),
                )
            
            # Verify all states were published
            assert mock_redis.setex.call_count == 7
            assert mock_redis.publish.call_count == 7
            
            # Verify final state
            final_call = mock_redis.setex.call_args_list[-1]
            final_payload = json.loads(final_call[0][2])
            assert final_payload["status"] == "completed"
            assert final_payload["progress"] == 100
    
    def test_polling_should_stop_on_completion(self):
        """Test that frontend should stop polling when status is completed."""
        completed_state = {
            "status": "completed",
            "progress": 100,
        }
        
        should_stop = completed_state["status"] in ("completed", "error")
        assert should_stop is True
    
    def test_polling_should_stop_on_error(self):
        """Test that frontend should stop polling when status is error."""
        error_state = {
            "status": "error",
            "progress": 0,
        }
        
        should_stop = error_state["status"] in ("completed", "error")
        assert should_stop is True
    
    def test_polling_should_continue_when_running(self):
        """Test that frontend should continue polling when status is running."""
        running_state = {
            "status": "running",
            "progress": 50,
        }
        
        should_stop = running_state["status"] in ("completed", "error")
        assert should_stop is False


class TestAnalysisWorkerIntegration:
    """Test integration between analysis worker and embedding progress."""
    
    def test_analysis_worker_imports_embedding_progress(self):
        """Test that analysis worker can import embedding progress functions."""
        # This tests that the import path works
        from app.core.redis import publish_embedding_progress
        
        assert callable(publish_embedding_progress)
    
    def test_embedding_queued_state_format(self):
        """Test the format of the initial 'queued' state."""
        repo_id = str(uuid4())
        
        with patch("app.core.redis.get_sync_redis_context") as mock_context:
            mock_redis = MagicMock()
            mock_context.return_value.__enter__ = MagicMock(return_value=mock_redis)
            mock_context.return_value.__exit__ = MagicMock(return_value=False)
            
            # This is what the analysis worker publishes when queueing embeddings
            publish_embedding_progress(
                repository_id=repo_id,
                stage="queued",
                progress=0,
                message="Queued 20 files for embedding",
                status="pending",
            )
            
            call_args = mock_redis.setex.call_args
            payload = json.loads(call_args[0][2])
            
            assert payload["stage"] == "queued"
            assert payload["status"] == "pending"
            assert payload["progress"] == 0
            assert "Queued" in payload["message"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
