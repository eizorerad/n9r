"""Unit tests for analysis worker status transitions.

Tests the status transition functions in the analysis worker:
- _mark_analysis_running(): pending→running transition
- _save_analysis_results(): running→completed transition
- _mark_analysis_failed(): running→failed transition

**Feature: status-transitions-fix**
**Validates: A2, A3, A4, A6 requirements from problems_tasks.md**
"""

import uuid
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

# =============================================================================
# Test _mark_analysis_running() - A2 requirements
# =============================================================================


class TestMarkAnalysisRunning:
    """Test the _mark_analysis_running() function.

    **Feature: status-transitions-fix**
    **Validates: A2 - pending→running transition**
    """

    @patch("app.workers.analysis.get_sync_session")
    def test_sets_status_to_running(self, mock_get_session):
        """
        **Feature: status-transitions-fix**
        **Validates: A2 - Worker sets status="running"**

        Test that _mark_analysis_running() sets status="running".
        """
        from app.workers.analysis import _mark_analysis_running

        # Create mock analysis with pending status
        mock_analysis = MagicMock()
        mock_analysis.id = uuid.uuid4()
        mock_analysis.status = "pending"
        mock_analysis.started_at = None
        mock_analysis.error_message = None

        # Setup mock session
        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_analysis
        mock_session.execute.return_value = mock_result
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)
        mock_get_session.return_value = mock_session

        # Call the function
        _mark_analysis_running(str(mock_analysis.id))

        # Verify status was set to running
        assert mock_analysis.status == "running"
        mock_session.commit.assert_called_once()

    @patch("app.workers.analysis.get_sync_session")
    def test_sets_started_at_when_null(self, mock_get_session):
        """
        **Feature: status-transitions-fix**
        **Validates: A2 - Worker sets started_at only if null**

        Test that _mark_analysis_running() sets started_at when it's null.
        """
        from app.workers.analysis import _mark_analysis_running

        # Create mock analysis with null started_at
        mock_analysis = MagicMock()
        mock_analysis.id = uuid.uuid4()
        mock_analysis.status = "pending"
        mock_analysis.started_at = None
        mock_analysis.error_message = None

        # Setup mock session
        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_analysis
        mock_session.execute.return_value = mock_result
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)
        mock_get_session.return_value = mock_session

        # Call the function
        _mark_analysis_running(str(mock_analysis.id))

        # Verify started_at was set
        assert mock_analysis.started_at is not None
        assert isinstance(mock_analysis.started_at, datetime)

    @patch("app.workers.analysis.get_sync_session")
    def test_does_not_overwrite_started_at_if_already_set(self, mock_get_session):
        """
        **Feature: status-transitions-fix**
        **Validates: A2 - started_at is NOT overwritten (idempotency)**

        Test that _mark_analysis_running() does NOT overwrite started_at if already set.
        This ensures idempotency and correct duration calculation.
        """
        from app.workers.analysis import _mark_analysis_running

        # Create mock analysis with existing started_at
        original_started_at = datetime.utcnow() - timedelta(minutes=5)
        mock_analysis = MagicMock()
        mock_analysis.id = uuid.uuid4()
        mock_analysis.status = "pending"
        mock_analysis.started_at = original_started_at
        mock_analysis.error_message = None

        # Setup mock session
        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_analysis
        mock_session.execute.return_value = mock_result
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)
        mock_get_session.return_value = mock_session

        # Call the function
        _mark_analysis_running(str(mock_analysis.id))

        # Verify started_at was NOT changed
        assert mock_analysis.started_at == original_started_at

    @patch("app.workers.analysis.get_sync_session")
    def test_clears_error_message_on_retry(self, mock_get_session):
        """
        **Feature: status-transitions-fix**
        **Validates: A2 - error_message is cleared on retry**

        Test that _mark_analysis_running() clears error_message when retrying
        after a previous failure.
        """
        from app.workers.analysis import _mark_analysis_running

        # Create mock analysis with existing error_message (from previous failure)
        mock_analysis = MagicMock()
        mock_analysis.id = uuid.uuid4()
        mock_analysis.status = "failed"
        mock_analysis.started_at = None
        mock_analysis.error_message = "Previous failure error"

        # Setup mock session
        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_analysis
        mock_session.execute.return_value = mock_result
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)
        mock_get_session.return_value = mock_session

        # Call the function
        _mark_analysis_running(str(mock_analysis.id))

        # Verify error_message was cleared
        assert mock_analysis.error_message is None
        assert mock_analysis.status == "running"

    @patch("app.workers.analysis.get_sync_session")
    def test_handles_nonexistent_analysis(self, mock_get_session):
        """
        **Feature: status-transitions-fix**
        **Validates: A2 - Graceful handling of nonexistent analysis**

        Test that _mark_analysis_running() handles nonexistent analysis gracefully.
        """
        from app.workers.analysis import _mark_analysis_running

        # Setup mock session that returns None
        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)
        mock_get_session.return_value = mock_session

        # Call the function - should not raise
        _mark_analysis_running(str(uuid.uuid4()))

        # Verify commit was NOT called (no analysis to update)
        mock_session.commit.assert_not_called()


# =============================================================================
# Test _save_analysis_results() - A3 requirements
# =============================================================================


class TestSaveAnalysisResults:
    """Test the _save_analysis_results() function.

    **Feature: status-transitions-fix**
    **Validates: A3 - running→completed transition**
    """

    @patch("app.workers.analysis.get_sync_session")
    def test_does_not_overwrite_started_at(self, mock_get_session):
        """
        **Feature: status-transitions-fix**
        **Validates: A3 - started_at is NOT overwritten on completion**

        Test that _save_analysis_results() does NOT overwrite started_at.
        """
        from app.workers.analysis import _save_analysis_results

        # Create mock analysis with existing started_at
        original_started_at = datetime.utcnow() - timedelta(minutes=10)
        mock_analysis = MagicMock()
        mock_analysis.id = uuid.uuid4()
        mock_analysis.status = "running"
        mock_analysis.started_at = original_started_at
        mock_analysis.completed_at = None

        # Create mock result
        mock_result_data = MagicMock()
        mock_result_data.vci_score = 85.5
        mock_result_data.tech_debt_level = "low"
        mock_result_data.metrics = {"test": "data"}
        mock_result_data.ai_report = "Test report"
        mock_result_data.issues = []

        # Setup mock session
        mock_session = MagicMock()
        mock_db_result = MagicMock()
        mock_db_result.scalar_one_or_none.return_value = mock_analysis
        mock_session.execute.return_value = mock_db_result
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)
        mock_get_session.return_value = mock_session

        # Call the function
        _save_analysis_results(str(uuid.uuid4()), str(mock_analysis.id), mock_result_data)

        # Verify started_at was NOT changed
        assert mock_analysis.started_at == original_started_at
        # Verify completed_at was set
        assert mock_analysis.completed_at is not None
        # Verify status is completed
        assert mock_analysis.status == "completed"

    @patch("app.workers.analysis.get_sync_session")
    def test_sets_started_at_as_fallback_if_null(self, mock_get_session):
        """
        **Feature: status-transitions-fix**
        **Validates: A3 - Defensive fallback: started_at set if null**

        Test that _save_analysis_results() sets started_at as fallback if null
        (for legacy records or rare race conditions).
        """
        from app.workers.analysis import _save_analysis_results

        # Create mock analysis with null started_at (legacy/race condition)
        mock_analysis = MagicMock()
        mock_analysis.id = uuid.uuid4()
        mock_analysis.status = "running"
        mock_analysis.started_at = None
        mock_analysis.completed_at = None

        # Create mock result
        mock_result_data = MagicMock()
        mock_result_data.vci_score = 85.5
        mock_result_data.tech_debt_level = "low"
        mock_result_data.metrics = {"test": "data"}
        mock_result_data.ai_report = "Test report"
        mock_result_data.issues = []

        # Setup mock session
        mock_session = MagicMock()
        mock_db_result = MagicMock()
        mock_db_result.scalar_one_or_none.return_value = mock_analysis
        mock_session.execute.return_value = mock_db_result
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)
        mock_get_session.return_value = mock_session

        # Call the function
        _save_analysis_results(str(uuid.uuid4()), str(mock_analysis.id), mock_result_data)

        # Verify started_at was set as fallback
        assert mock_analysis.started_at is not None
        assert isinstance(mock_analysis.started_at, datetime)
        # Verify completed_at was also set
        assert mock_analysis.completed_at is not None

    @patch("app.workers.analysis.get_sync_session")
    def test_sets_completed_at(self, mock_get_session):
        """
        **Feature: status-transitions-fix**
        **Validates: A3 - completed_at is set on completion**

        Test that _save_analysis_results() sets completed_at.
        """
        from app.workers.analysis import _save_analysis_results

        # Create mock analysis
        mock_analysis = MagicMock()
        mock_analysis.id = uuid.uuid4()
        mock_analysis.status = "running"
        mock_analysis.started_at = datetime.utcnow() - timedelta(minutes=5)
        mock_analysis.completed_at = None

        # Create mock result
        mock_result_data = MagicMock()
        mock_result_data.vci_score = 85.5
        mock_result_data.tech_debt_level = "low"
        mock_result_data.metrics = {"test": "data"}
        mock_result_data.ai_report = "Test report"
        mock_result_data.issues = []

        # Setup mock session
        mock_session = MagicMock()
        mock_db_result = MagicMock()
        mock_db_result.scalar_one_or_none.return_value = mock_analysis
        mock_session.execute.return_value = mock_db_result
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)
        mock_get_session.return_value = mock_session

        # Call the function
        _save_analysis_results(str(uuid.uuid4()), str(mock_analysis.id), mock_result_data)

        # Verify completed_at was set
        assert mock_analysis.completed_at is not None
        assert isinstance(mock_analysis.completed_at, datetime)


# =============================================================================
# Test _mark_analysis_failed() - A4 requirements
# =============================================================================


class TestMarkAnalysisFailed:
    """Test the _mark_analysis_failed() function.

    **Feature: status-transitions-fix**
    **Validates: A4 - running→failed transition**
    """

    @patch("app.workers.analysis.publish_analysis_progress")
    @patch("app.workers.analysis.get_sync_session")
    def test_does_not_overwrite_started_at(self, mock_get_session, mock_publish):
        """
        **Feature: status-transitions-fix**
        **Validates: A4 - started_at is NOT overwritten on failure**

        Test that _mark_analysis_failed() does NOT overwrite started_at.
        """
        from app.workers.analysis import _mark_analysis_failed

        # Create mock analysis with existing started_at
        original_started_at = datetime.utcnow() - timedelta(minutes=10)
        mock_analysis = MagicMock()
        mock_analysis.id = uuid.uuid4()
        mock_analysis.status = "running"
        mock_analysis.started_at = original_started_at
        mock_analysis.completed_at = None
        mock_analysis.error_message = None

        # Setup mock session
        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_analysis
        mock_session.execute.return_value = mock_result
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)
        mock_get_session.return_value = mock_session

        # Call the function
        _mark_analysis_failed(str(mock_analysis.id), "Test error message")

        # Verify started_at was NOT changed
        assert mock_analysis.started_at == original_started_at
        # Verify status is failed
        assert mock_analysis.status == "failed"
        # Verify error_message was set
        assert mock_analysis.error_message == "Test error message"

    @patch("app.workers.analysis.publish_analysis_progress")
    @patch("app.workers.analysis.get_sync_session")
    def test_sets_started_at_as_fallback_if_null(self, mock_get_session, mock_publish):
        """
        **Feature: status-transitions-fix**
        **Validates: A4 - Defensive fallback: started_at set if null**

        Test that _mark_analysis_failed() sets started_at as fallback if null.
        """
        from app.workers.analysis import _mark_analysis_failed

        # Create mock analysis with null started_at
        mock_analysis = MagicMock()
        mock_analysis.id = uuid.uuid4()
        mock_analysis.status = "running"
        mock_analysis.started_at = None
        mock_analysis.completed_at = None
        mock_analysis.error_message = None

        # Setup mock session
        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_analysis
        mock_session.execute.return_value = mock_result
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)
        mock_get_session.return_value = mock_session

        # Call the function
        _mark_analysis_failed(str(mock_analysis.id), "Test error message")

        # Verify started_at was set as fallback
        assert mock_analysis.started_at is not None
        assert isinstance(mock_analysis.started_at, datetime)

    @patch("app.workers.analysis.publish_analysis_progress")
    @patch("app.workers.analysis.get_sync_session")
    def test_sets_completed_at_on_failure(self, mock_get_session, mock_publish):
        """
        **Feature: status-transitions-fix**
        **Validates: A4 - completed_at is set on failure**

        Test that _mark_analysis_failed() sets completed_at.
        """
        from app.workers.analysis import _mark_analysis_failed

        # Create mock analysis
        mock_analysis = MagicMock()
        mock_analysis.id = uuid.uuid4()
        mock_analysis.status = "running"
        mock_analysis.started_at = datetime.utcnow() - timedelta(minutes=5)
        mock_analysis.completed_at = None
        mock_analysis.error_message = None

        # Setup mock session
        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_analysis
        mock_session.execute.return_value = mock_result
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)
        mock_get_session.return_value = mock_session

        # Call the function
        _mark_analysis_failed(str(mock_analysis.id), "Test error message")

        # Verify completed_at was set
        assert mock_analysis.completed_at is not None
        assert isinstance(mock_analysis.completed_at, datetime)

    @patch("app.workers.analysis.publish_analysis_progress")
    @patch("app.workers.analysis.get_sync_session")
    def test_truncates_long_error_message(self, mock_get_session, mock_publish):
        """
        **Feature: status-transitions-fix**
        **Validates: A4 - error_message is truncated to 500 chars**

        Test that _mark_analysis_failed() truncates long error messages.
        """
        from app.workers.analysis import _mark_analysis_failed

        # Create mock analysis
        mock_analysis = MagicMock()
        mock_analysis.id = uuid.uuid4()
        mock_analysis.status = "running"
        mock_analysis.started_at = datetime.utcnow()
        mock_analysis.completed_at = None
        mock_analysis.error_message = None

        # Setup mock session
        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_analysis
        mock_session.execute.return_value = mock_result
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)
        mock_get_session.return_value = mock_session

        # Create a very long error message
        long_error = "x" * 1000

        # Call the function
        _mark_analysis_failed(str(mock_analysis.id), long_error)

        # Verify error_message was truncated to 500 chars
        assert len(mock_analysis.error_message) == 500

    @patch("app.workers.analysis.publish_analysis_progress")
    @patch("app.workers.analysis.get_sync_session")
    def test_publishes_failure_to_redis(self, mock_get_session, mock_publish):
        """
        **Feature: status-transitions-fix**
        **Validates: A4 - Failure is published to Redis for SSE**

        Test that _mark_analysis_failed() publishes failure to Redis.
        """
        from app.workers.analysis import _mark_analysis_failed

        # Create mock analysis
        analysis_id = uuid.uuid4()
        mock_analysis = MagicMock()
        mock_analysis.id = analysis_id
        mock_analysis.status = "running"
        mock_analysis.started_at = datetime.utcnow()
        mock_analysis.completed_at = None
        mock_analysis.error_message = None

        # Setup mock session
        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_analysis
        mock_session.execute.return_value = mock_result
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)
        mock_get_session.return_value = mock_session

        # Call the function
        _mark_analysis_failed(str(analysis_id), "Test error")

        # Verify publish was called
        mock_publish.assert_called_once_with(
            analysis_id=str(analysis_id),
            stage="failed",
            progress=0,
            message="Test error"[:200],
            status="failed",
        )


# =============================================================================
# Integration-style tests for status transition sequence
# =============================================================================


class TestStatusTransitionSequence:
    """Test the complete status transition sequence.

    **Feature: status-transitions-fix**
    **Validates: A2, A3, A4 - Full transition sequence**
    """

    @patch("app.workers.analysis.publish_analysis_progress")
    @patch("app.workers.analysis.get_sync_session")
    def test_full_success_sequence_preserves_started_at(self, mock_get_session, mock_publish):
        """
        **Feature: status-transitions-fix**
        **Validates: A2, A3 - Full success sequence preserves started_at**

        Test that the full success sequence (pending→running→completed)
        preserves the original started_at timestamp.
        """
        from app.workers.analysis import _mark_analysis_running, _save_analysis_results

        # Create mock analysis
        mock_analysis = MagicMock()
        mock_analysis.id = uuid.uuid4()
        mock_analysis.status = "pending"
        mock_analysis.started_at = None
        mock_analysis.completed_at = None
        mock_analysis.error_message = None

        # Setup mock session
        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_analysis
        mock_session.execute.return_value = mock_result
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)
        mock_get_session.return_value = mock_session

        # Step 1: Mark as running
        _mark_analysis_running(str(mock_analysis.id))

        # Capture the started_at set during running transition
        started_at_after_running = mock_analysis.started_at
        assert started_at_after_running is not None
        assert mock_analysis.status == "running"

        # Create mock result
        mock_result_data = MagicMock()
        mock_result_data.vci_score = 85.5
        mock_result_data.tech_debt_level = "low"
        mock_result_data.metrics = {"test": "data"}
        mock_result_data.ai_report = "Test report"
        mock_result_data.issues = []

        # Step 2: Save results (complete)
        _save_analysis_results(str(uuid.uuid4()), str(mock_analysis.id), mock_result_data)

        # Verify started_at was NOT changed during completion
        assert mock_analysis.started_at == started_at_after_running
        assert mock_analysis.status == "completed"
        assert mock_analysis.completed_at is not None

    @patch("app.workers.analysis.publish_analysis_progress")
    @patch("app.workers.analysis.get_sync_session")
    def test_full_failure_sequence_preserves_started_at(self, mock_get_session, mock_publish):
        """
        **Feature: status-transitions-fix**
        **Validates: A2, A4 - Full failure sequence preserves started_at**

        Test that the full failure sequence (pending→running→failed)
        preserves the original started_at timestamp.
        """
        from app.workers.analysis import _mark_analysis_failed, _mark_analysis_running

        # Create mock analysis
        mock_analysis = MagicMock()
        mock_analysis.id = uuid.uuid4()
        mock_analysis.status = "pending"
        mock_analysis.started_at = None
        mock_analysis.completed_at = None
        mock_analysis.error_message = None

        # Setup mock session
        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_analysis
        mock_session.execute.return_value = mock_result
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)
        mock_get_session.return_value = mock_session

        # Step 1: Mark as running
        _mark_analysis_running(str(mock_analysis.id))

        # Capture the started_at set during running transition
        started_at_after_running = mock_analysis.started_at
        assert started_at_after_running is not None
        assert mock_analysis.status == "running"

        # Step 2: Mark as failed
        _mark_analysis_failed(str(mock_analysis.id), "Test failure")

        # Verify started_at was NOT changed during failure
        assert mock_analysis.started_at == started_at_after_running
        assert mock_analysis.status == "failed"
        assert mock_analysis.completed_at is not None
        assert mock_analysis.error_message == "Test failure"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
