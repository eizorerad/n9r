"""Tests for full_tree backfill in _populate_content_cache."""

import uuid
from pathlib import Path
from unittest.mock import patch


@patch("app.workers.embeddings.run_async")
@patch("app.services.repo_content.RepoContentService")
@patch("app.core.database.async_session_maker")
def test_populate_content_cache_backfills_tree(mock_session_maker, mock_repo_content_service, mock_run_async):
    """
    Verify that _populate_content_cache backfills full_tree when cache is ready.
    """
    from app.workers.embeddings import _populate_content_cache

    # Setup mocks
    repo_id = str(uuid.uuid4())
    commit_sha = "a" * 40
    repo_path = Path("/tmp/test_repo")

    # Mock run_async to execute the coroutine and return result
    mock_run_async.return_value = {
        "status": "completed",
        "files_cached": 1,
        "uploaded": 1,
        "skipped": 0,
        "failed": 0,
    }

    # Run function
    result = _populate_content_cache(repo_id, commit_sha, repo_path)

    # Verify run_async was called
    mock_run_async.assert_called_once()
    assert result["status"] == "completed"


@patch("app.workers.embeddings.run_async")
@patch("app.services.repo_content.RepoContentService")
@patch("app.core.database.async_session_maker")
def test_populate_content_cache_skips_if_tree_exists(mock_session_maker, mock_repo_content_service, mock_run_async):
    """
    Verify that _populate_content_cache skips when cache is ready AND tree exists.
    """
    from app.workers.embeddings import _populate_content_cache

    # Setup mocks
    repo_id = str(uuid.uuid4())
    commit_sha = "b" * 40
    repo_path = Path("/tmp/test_repo")

    # Mock run_async to return skipped status
    mock_run_async.return_value = {
        "status": "skipped",
        "reason": "cache_already_ready",
    }

    # Run function
    result = _populate_content_cache(repo_id, commit_sha, repo_path)

    # Verify skipped
    mock_run_async.assert_called_once()
    assert result["status"] == "skipped"
    assert result["reason"] == "cache_already_ready"
