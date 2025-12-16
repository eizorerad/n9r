
import asyncio
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.workers.embeddings import _populate_content_cache

# Mock the entire RepoContentService to avoid DB/MinIO calls
@patch("app.workers.embeddings.RepoContentService")
@patch("app.workers.embeddings.async_session_maker")
def test_populate_content_cache_backfills_tree(mock_session_maker, MockRepoContentService):
    """
    Verify that _populate_content_cache backfills full_tree when cache is ready but tree is missing.
    """
    # Setup mocks
    repo_id = str(uuid.uuid4())
    commit_sha = "a" * 40
    repo_path = Path("/tmp/test_repo")
    
    # Mock DB session
    mock_db = AsyncMock()
    mock_session_maker.return_value.__aenter__.return_value = mock_db
    
    # Mock RepoContentService instance
    mock_service = MockRepoContentService.return_value
    
    # Mock cache object
    mock_cache = MagicMock()
    mock_cache.id = uuid.uuid4()
    mock_cache.status = "ready"
    mock_service.get_or_create_cache.return_value = mock_cache
    
    # SCENARIO 1: Cache ready, tree missing -> Should backfill
    mock_service.has_full_tree.return_value = False
    mock_service.collect_files_from_repo.return_value = [] # Return empty files to avoid upload logic
    mock_service.collect_full_tree.return_value = [{"path": "file.txt"}]
    
    # Run function
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    result = loop.run_until_complete(_populate_content_cache(repo_id, commit_sha, repo_path))
    
    # Verify backfill happened
    mock_service.has_full_tree.assert_called_once()
    mock_service.collect_full_tree.assert_called_once()
    mock_service.save_tree.assert_called_once()
    assert result["status"] == "completed"

@patch("app.workers.embeddings.RepoContentService")
@patch("app.workers.embeddings.async_session_maker")
def test_populate_content_cache_skips_if_tree_exists(mock_session_maker, MockRepoContentService):
    """
    Verify that _populate_content_cache skips when cache is ready AND tree exists.
    """
    # Setup mocks
    repo_id = str(uuid.uuid4())
    commit_sha = "b" * 40
    repo_path = Path("/tmp/test_repo")
    
    mock_db = AsyncMock()
    mock_session_maker.return_value.__aenter__.return_value = mock_db
    
    mock_service = MockRepoContentService.return_value
    
    mock_cache = MagicMock()
    mock_cache.id = uuid.uuid4()
    mock_cache.status = "ready"
    mock_service.get_or_create_cache.return_value = mock_cache
    
    # SCENARIO 2: Cache ready, tree exists -> Should skip
    mock_service.has_full_tree.return_value = True
    
    # Run function
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    result = loop.run_until_complete(_populate_content_cache(repo_id, commit_sha, repo_path))
    
    # Verify skipped
    mock_service.has_full_tree.assert_called_once()
    mock_service.collect_full_tree.assert_not_called()
    mock_service.save_tree.assert_not_called()
    assert result["status"] == "skipped"
    assert result["reason"] == "cache_already_ready"
