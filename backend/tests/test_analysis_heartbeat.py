"""Tests for the heartbeat-based stuck analysis detection system.

This module contains comprehensive tests for the heartbeat system including:
- Heartbeat update tests (update_heartbeat, throttling, publish_progress)
- trigger_analysis API tests (stuck detection, 409 conflicts)
- scheduler-cleanup tests (cleanup_stuck_analyses)
- Helper function tests (is_analysis_stuck, get_stuck_reason)

**Feature: heartbeat-stuck-detection**
**Validates: Section C5 of problems_tasks.md**
**Spec: docs/architecture/analysis-status-contract.md**
"""

import time
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest


# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def mock_analysis():
    """Create a mock Analysis object with default values."""
    analysis = MagicMock()
    analysis.id = uuid.uuid4()
    analysis.repository_id = uuid.uuid4()
    analysis.status = "pending"
    analysis.created_at = datetime.now(timezone.utc)
    analysis.state_updated_at = datetime.now(timezone.utc)
    analysis.started_at = None
    analysis.completed_at = None
    analysis.error_message = None
    analysis.pinned = False
    return analysis


@pytest.fixture
def mock_settings():
    """Create mock settings with default heartbeat configuration."""
    settings = MagicMock()
    settings.analysis_pending_stuck_minutes = 30
    settings.analysis_running_heartbeat_timeout_minutes = 15
    settings.analysis_heartbeat_interval_seconds = 30
    return settings


# =============================================================================
# 1. Heartbeat Update Tests
# =============================================================================


class TestUpdateHeartbeat:
    """Test the update_heartbeat() function in backend/app/workers/analysis.py.
    
    **Feature: heartbeat-stuck-detection**
    **Validates: C2 - Heartbeat for static analysis in DB**
    """

    @patch("app.workers.analysis.get_sync_session")
    @patch("app.workers.analysis.settings")
    def test_update_heartbeat_updates_state_updated_at(self, mock_settings, mock_get_session):
        """
        **Feature: heartbeat-stuck-detection**
        **Validates: C2 - update_heartbeat() updates state_updated_at**
        
        Test that update_heartbeat() updates the state_updated_at field.
        """
        from app.workers.analysis import _last_heartbeat_times, update_heartbeat

        # Clear any existing heartbeat tracking
        _last_heartbeat_times.clear()

        # Setup mock settings
        mock_settings.analysis_heartbeat_interval_seconds = 30

        # Create mock analysis
        analysis_id = uuid.uuid4()
        original_timestamp = datetime.utcnow() - timedelta(minutes=5)
        mock_analysis = MagicMock()
        mock_analysis.id = analysis_id
        mock_analysis.state_updated_at = original_timestamp

        # Setup mock session
        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_analysis
        mock_session.execute.return_value = mock_result
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)
        mock_get_session.return_value = mock_session

        # Call update_heartbeat
        result = update_heartbeat(str(analysis_id))

        # Verify heartbeat was updated
        assert result is True
        assert mock_analysis.state_updated_at != original_timestamp
        assert mock_analysis.state_updated_at > original_timestamp
        mock_session.commit.assert_called_once()

    @patch("app.workers.analysis.get_sync_session")
    @patch("app.workers.analysis.settings")
    def test_update_heartbeat_throttling(self, mock_settings, mock_get_session):
        """
        **Feature: heartbeat-stuck-detection**
        **Validates: C2 - Heartbeat throttling (not more frequent than interval)**
        
        Test that update_heartbeat() is throttled to avoid database spam.
        """
        from app.workers.analysis import _last_heartbeat_times, update_heartbeat

        # Clear any existing heartbeat tracking
        _last_heartbeat_times.clear()

        # Setup mock settings with 30 second interval
        mock_settings.analysis_heartbeat_interval_seconds = 30

        # Create mock analysis
        analysis_id = uuid.uuid4()
        mock_analysis = MagicMock()
        mock_analysis.id = analysis_id
        mock_analysis.state_updated_at = datetime.utcnow()

        # Setup mock session
        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_analysis
        mock_session.execute.return_value = mock_result
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)
        mock_get_session.return_value = mock_session

        # First call should succeed
        result1 = update_heartbeat(str(analysis_id))
        assert result1 is True

        # Second call immediately after should be throttled
        result2 = update_heartbeat(str(analysis_id))
        assert result2 is False

        # Verify commit was only called once
        assert mock_session.commit.call_count == 1

    @patch("app.workers.analysis.get_sync_session")
    @patch("app.workers.analysis.settings")
    def test_update_heartbeat_force_bypasses_throttling(self, mock_settings, mock_get_session):
        """
        **Feature: heartbeat-stuck-detection**
        **Validates: C2 - force=True bypasses throttling**
        
        Test that update_heartbeat(force=True) bypasses throttling.
        """
        from app.workers.analysis import _last_heartbeat_times, update_heartbeat

        # Clear any existing heartbeat tracking
        _last_heartbeat_times.clear()

        # Setup mock settings
        mock_settings.analysis_heartbeat_interval_seconds = 30

        # Create mock analysis
        analysis_id = uuid.uuid4()
        mock_analysis = MagicMock()
        mock_analysis.id = analysis_id
        mock_analysis.state_updated_at = datetime.utcnow()

        # Setup mock session
        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_analysis
        mock_session.execute.return_value = mock_result
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)
        mock_get_session.return_value = mock_session

        # First call
        result1 = update_heartbeat(str(analysis_id))
        assert result1 is True

        # Second call with force=True should succeed
        result2 = update_heartbeat(str(analysis_id), force=True)
        assert result2 is True

        # Verify commit was called twice
        assert mock_session.commit.call_count == 2

    @patch("app.workers.analysis.get_sync_session")
    @patch("app.workers.analysis.settings")
    def test_update_heartbeat_handles_nonexistent_analysis(self, mock_settings, mock_get_session):
        """
        **Feature: heartbeat-stuck-detection**
        **Validates: C2 - Graceful handling of nonexistent analysis**
        
        Test that update_heartbeat() handles nonexistent analysis gracefully.
        """
        from app.workers.analysis import _last_heartbeat_times, update_heartbeat

        # Clear any existing heartbeat tracking
        _last_heartbeat_times.clear()

        # Setup mock settings
        mock_settings.analysis_heartbeat_interval_seconds = 30

        # Setup mock session that returns None
        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)
        mock_get_session.return_value = mock_session

        # Call should return False but not raise
        result = update_heartbeat(str(uuid.uuid4()))
        assert result is False
        mock_session.commit.assert_not_called()

    @patch("app.workers.analysis.get_sync_session")
    @patch("app.workers.analysis.settings")
    def test_update_heartbeat_handles_db_error(self, mock_settings, mock_get_session):
        """
        **Feature: heartbeat-stuck-detection**
        **Validates: C2 - Heartbeat failures should not crash the worker**
        
        Test that update_heartbeat() handles database errors gracefully.
        """
        from app.workers.analysis import _last_heartbeat_times, update_heartbeat

        # Clear any existing heartbeat tracking
        _last_heartbeat_times.clear()

        # Setup mock settings
        mock_settings.analysis_heartbeat_interval_seconds = 30

        # Setup mock session that raises an exception
        mock_session = MagicMock()
        mock_session.execute.side_effect = Exception("Database connection error")
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)
        mock_get_session.return_value = mock_session

        # Call should return False but not raise
        result = update_heartbeat(str(uuid.uuid4()))
        assert result is False


class TestPublishProgressHeartbeat:
    """Test that publish_progress() triggers heartbeat update.
    
    **Feature: heartbeat-stuck-detection**
    **Validates: C2 - publish_progress triggers heartbeat update**
    """

    @patch("app.workers.analysis.update_heartbeat")
    @patch("app.workers.analysis.publish_analysis_progress")
    def test_publish_progress_calls_update_heartbeat(self, mock_publish, mock_update_heartbeat):
        """
        **Feature: heartbeat-stuck-detection**
        **Validates: C2 - publish_progress() triggers heartbeat update**
        
        Test that the publish_progress helper in analyze_repository calls update_heartbeat.
        """
        # This test verifies the integration by checking that update_heartbeat
        # is called when publish_progress is invoked within analyze_repository.
        # Since publish_progress is a nested function, we test the behavior
        # by examining the analyze_repository code structure.
        
        # The implementation shows that publish_progress calls update_heartbeat:
        # def publish_progress(stage: str, progress: int, message: str | None = None):
        #     ...
        #     update_heartbeat(analysis_id)
        
        # We verify this by checking the source code structure
        import inspect
        from app.workers.analysis import analyze_repository
        
        source = inspect.getsource(analyze_repository)
        assert "update_heartbeat(analysis_id)" in source, (
            "publish_progress should call update_heartbeat(analysis_id)"
        )


class TestCleanupHeartbeatTracking:
    """Test cleanup_heartbeat_tracking() function.
    
    **Feature: heartbeat-stuck-detection**
    **Validates: C2 - Cleanup heartbeat tracking to prevent memory leaks**
    """

    def test_cleanup_heartbeat_tracking_removes_entry(self):
        """
        **Feature: heartbeat-stuck-detection**
        **Validates: C2 - cleanup_heartbeat_tracking removes tracking entry**
        
        Test that cleanup_heartbeat_tracking() removes the tracking entry.
        """
        from app.workers.analysis import _last_heartbeat_times, cleanup_heartbeat_tracking

        # Add a tracking entry
        analysis_id = str(uuid.uuid4())
        _last_heartbeat_times[analysis_id] = time.time()

        # Verify entry exists
        assert analysis_id in _last_heartbeat_times

        # Cleanup
        cleanup_heartbeat_tracking(analysis_id)

        # Verify entry was removed
        assert analysis_id not in _last_heartbeat_times

    def test_cleanup_heartbeat_tracking_handles_nonexistent(self):
        """
        **Feature: heartbeat-stuck-detection**
        **Validates: C2 - cleanup_heartbeat_tracking handles nonexistent entry**
        
        Test that cleanup_heartbeat_tracking() handles nonexistent entries gracefully.
        """
        from app.workers.analysis import cleanup_heartbeat_tracking

        # Should not raise for nonexistent entry
        cleanup_heartbeat_tracking(str(uuid.uuid4()))


# =============================================================================
# 2. trigger_analysis API Tests
# =============================================================================


class TestTriggerAnalysisStuckDetection:
    """Test trigger_analysis stuck detection behavior.
    
    **Feature: heartbeat-stuck-detection**
    **Validates: C3 - Redesign cleanup in API (trigger_analysis)**
    """

    def test_is_analysis_stuck_pending_fresh(self, mock_analysis, mock_settings):
        """
        **Feature: heartbeat-stuck-detection**
        **Validates: C3 - Pending analysis with recent created_at is NOT stuck**
        
        Test that a pending analysis with recent created_at is not considered stuck.
        """
        from app.api.v1.analyses import is_analysis_stuck

        with patch("app.api.v1.analyses.settings", mock_settings):
            mock_analysis.status = "pending"
            mock_analysis.created_at = datetime.now(timezone.utc) - timedelta(minutes=5)

            result = is_analysis_stuck(mock_analysis)
            assert result is False

    def test_is_analysis_stuck_pending_stale(self, mock_analysis, mock_settings):
        """
        **Feature: heartbeat-stuck-detection**
        **Validates: C3 - Pending analysis with old created_at IS stuck**
        
        Test that a pending analysis with old created_at is considered stuck.
        """
        from app.api.v1.analyses import is_analysis_stuck

        with patch("app.api.v1.analyses.settings", mock_settings):
            mock_analysis.status = "pending"
            # Created 35 minutes ago (exceeds 30 minute timeout)
            mock_analysis.created_at = datetime.now(timezone.utc) - timedelta(minutes=35)

            result = is_analysis_stuck(mock_analysis)
            assert result is True

    def test_is_analysis_stuck_running_fresh_heartbeat(self, mock_analysis, mock_settings):
        """
        **Feature: heartbeat-stuck-detection**
        **Validates: C3 - Running analysis with fresh heartbeat is NOT stuck**
        
        Test that a running analysis with fresh state_updated_at is not considered stuck.
        """
        from app.api.v1.analyses import is_analysis_stuck

        with patch("app.api.v1.analyses.settings", mock_settings):
            mock_analysis.status = "running"
            mock_analysis.state_updated_at = datetime.now(timezone.utc) - timedelta(minutes=5)

            result = is_analysis_stuck(mock_analysis)
            assert result is False

    def test_is_analysis_stuck_running_stale_heartbeat(self, mock_analysis, mock_settings):
        """
        **Feature: heartbeat-stuck-detection**
        **Validates: C3 - Running analysis with stale heartbeat IS stuck**
        
        Test that a running analysis with stale state_updated_at is considered stuck.
        """
        from app.api.v1.analyses import is_analysis_stuck

        with patch("app.api.v1.analyses.settings", mock_settings):
            mock_analysis.status = "running"
            # Last heartbeat 20 minutes ago (exceeds 15 minute timeout)
            mock_analysis.state_updated_at = datetime.now(timezone.utc) - timedelta(minutes=20)

            result = is_analysis_stuck(mock_analysis)
            assert result is True

    def test_is_analysis_stuck_terminal_states_never_stuck(self, mock_analysis, mock_settings):
        """
        **Feature: heartbeat-stuck-detection**
        **Validates: C3 - Terminal states (completed/failed/skipped) are never stuck**
        
        Test that terminal states are never considered stuck.
        """
        from app.api.v1.analyses import is_analysis_stuck

        with patch("app.api.v1.analyses.settings", mock_settings):
            for status in ["completed", "failed", "skipped"]:
                mock_analysis.status = status
                # Even with very old timestamps
                mock_analysis.created_at = datetime.now(timezone.utc) - timedelta(days=30)
                mock_analysis.state_updated_at = datetime.now(timezone.utc) - timedelta(days=30)

                result = is_analysis_stuck(mock_analysis)
                assert result is False, f"Status '{status}' should never be stuck"


class TestGetStuckReason:
    """Test get_stuck_reason() helper function.
    
    **Feature: heartbeat-stuck-detection**
    **Validates: C3 - get_stuck_reason returns correct reasons**
    """

    def test_get_stuck_reason_pending_timeout(self, mock_analysis, mock_settings):
        """
        **Feature: heartbeat-stuck-detection**
        **Validates: C3 - get_stuck_reason returns 'pending_timeout' for stuck pending**
        
        Test that get_stuck_reason returns 'pending_timeout' for stuck pending analysis.
        """
        from app.api.v1.analyses import get_stuck_reason

        with patch("app.api.v1.analyses.settings", mock_settings):
            mock_analysis.status = "pending"
            mock_analysis.created_at = datetime.now(timezone.utc) - timedelta(minutes=35)

            result = get_stuck_reason(mock_analysis)
            assert result == "pending_timeout"

    def test_get_stuck_reason_heartbeat_timeout(self, mock_analysis, mock_settings):
        """
        **Feature: heartbeat-stuck-detection**
        **Validates: C3 - get_stuck_reason returns 'heartbeat_timeout' for stuck running**
        
        Test that get_stuck_reason returns 'heartbeat_timeout' for stuck running analysis.
        """
        from app.api.v1.analyses import get_stuck_reason

        with patch("app.api.v1.analyses.settings", mock_settings):
            mock_analysis.status = "running"
            mock_analysis.state_updated_at = datetime.now(timezone.utc) - timedelta(minutes=20)

            result = get_stuck_reason(mock_analysis)
            assert result == "heartbeat_timeout"

    def test_get_stuck_reason_not_stuck(self, mock_analysis, mock_settings):
        """
        **Feature: heartbeat-stuck-detection**
        **Validates: C3 - get_stuck_reason returns None for non-stuck analysis**
        
        Test that get_stuck_reason returns None for non-stuck analysis.
        """
        from app.api.v1.analyses import get_stuck_reason

        with patch("app.api.v1.analyses.settings", mock_settings):
            mock_analysis.status = "running"
            mock_analysis.state_updated_at = datetime.now(timezone.utc) - timedelta(minutes=5)

            result = get_stuck_reason(mock_analysis)
            assert result is None


class TestMarkAnalysisAsStuckFailed:
    """Test mark_analysis_as_stuck_failed() helper function.
    
    **Feature: heartbeat-stuck-detection**
    **Validates: C3 - mark_analysis_as_stuck_failed sets correct error messages**
    """

    def test_mark_analysis_as_stuck_failed_pending_timeout(self, mock_analysis):
        """
        **Feature: heartbeat-stuck-detection**
        **Validates: C3 - Correct error message for pending_timeout**
        
        Test that mark_analysis_as_stuck_failed sets correct error message for pending_timeout.
        """
        from app.api.v1.analyses import mark_analysis_as_stuck_failed

        mock_analysis.status = "pending"
        mark_analysis_as_stuck_failed(mock_analysis, "pending_timeout", source="trigger_analysis")

        assert mock_analysis.status == "failed"
        assert "pending-stuck" in mock_analysis.error_message
        assert mock_analysis.completed_at is not None

    def test_mark_analysis_as_stuck_failed_heartbeat_timeout(self, mock_analysis):
        """
        **Feature: heartbeat-stuck-detection**
        **Validates: C3 - Correct error message for heartbeat_timeout**
        
        Test that mark_analysis_as_stuck_failed sets correct error message for heartbeat_timeout.
        """
        from app.api.v1.analyses import mark_analysis_as_stuck_failed

        mock_analysis.status = "running"
        mark_analysis_as_stuck_failed(mock_analysis, "heartbeat_timeout", source="trigger_analysis")

        assert mock_analysis.status == "failed"
        assert "running-stuck" in mock_analysis.error_message
        assert "no heartbeat" in mock_analysis.error_message
        assert mock_analysis.completed_at is not None

    def test_mark_analysis_as_stuck_failed_scheduler_source(self, mock_analysis):
        """
        **Feature: heartbeat-stuck-detection**
        **Validates: C4 - Correct error message for scheduler cleanup**
        
        Test that mark_analysis_as_stuck_failed includes scheduler source in message.
        """
        from app.api.v1.analyses import mark_analysis_as_stuck_failed

        mock_analysis.status = "pending"
        mark_analysis_as_stuck_failed(mock_analysis, "pending_timeout", source="scheduler_cleanup")

        assert "scheduler cleanup" in mock_analysis.error_message


# =============================================================================
# 3. scheduler-cleanup Tests
# =============================================================================


class TestCleanupStuckAnalyses:
    """Test cleanup_stuck_analyses() scheduled task.
    
    **Feature: heartbeat-stuck-detection**
    **Validates: C4 - Redesign scheduler-cleanup**
    """

    @patch("app.workers.scheduled.get_sync_session")
    @patch("app.workers.scheduled.settings")
    def test_cleanup_pending_old_created_at(self, mock_settings, mock_get_session):
        """
        **Feature: heartbeat-stuck-detection**
        **Validates: C4 - Pending analysis with old created_at is marked as failed**
        
        Test that pending analysis with old created_at is marked as failed.
        """
        from app.workers.scheduled import cleanup_stuck_analyses

        # Setup mock settings
        mock_settings.analysis_pending_stuck_minutes = 30
        mock_settings.analysis_running_heartbeat_timeout_minutes = 15

        # Create mock pending analysis with old created_at
        mock_analysis = MagicMock()
        mock_analysis.id = uuid.uuid4()
        mock_analysis.repository_id = uuid.uuid4()
        mock_analysis.status = "pending"
        mock_analysis.created_at = datetime.now(timezone.utc) - timedelta(minutes=35)
        mock_analysis.state_updated_at = datetime.now(timezone.utc) - timedelta(minutes=35)
        mock_analysis.pinned = False

        # Setup mock session
        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_analysis]
        mock_pinned_result = MagicMock()
        mock_pinned_result.scalars.return_value.all.return_value = []
        mock_session.execute.side_effect = [mock_result, mock_pinned_result]
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)
        mock_get_session.return_value = mock_session

        # Run cleanup
        result = cleanup_stuck_analyses()

        # Verify analysis was marked as failed
        assert mock_analysis.status == "failed"
        assert "pending-stuck" in mock_analysis.error_message
        assert result["cleaned_count"] == 1
        assert result["pending_timeout_count"] == 1

    @patch("app.workers.scheduled.get_sync_session")
    @patch("app.workers.scheduled.settings")
    def test_cleanup_running_fresh_heartbeat_not_touched(self, mock_settings, mock_get_session):
        """
        **Feature: heartbeat-stuck-detection**
        **Validates: C4 - Running analysis with fresh heartbeat is NOT touched**
        
        Test that running analysis with fresh heartbeat is not touched.
        """
        from app.workers.scheduled import cleanup_stuck_analyses

        # Setup mock settings
        mock_settings.analysis_pending_stuck_minutes = 30
        mock_settings.analysis_running_heartbeat_timeout_minutes = 15

        # Create mock running analysis with fresh heartbeat
        mock_analysis = MagicMock()
        mock_analysis.id = uuid.uuid4()
        mock_analysis.repository_id = uuid.uuid4()
        mock_analysis.status = "running"
        mock_analysis.created_at = datetime.now(timezone.utc) - timedelta(hours=1)
        mock_analysis.state_updated_at = datetime.now(timezone.utc) - timedelta(minutes=5)
        mock_analysis.pinned = False

        # Setup mock session
        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_analysis]
        mock_pinned_result = MagicMock()
        mock_pinned_result.scalars.return_value.all.return_value = []
        mock_session.execute.side_effect = [mock_result, mock_pinned_result]
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)
        mock_get_session.return_value = mock_session

        # Run cleanup
        result = cleanup_stuck_analyses()

        # Verify analysis was NOT touched
        assert mock_analysis.status == "running"
        assert result["cleaned_count"] == 0

    @patch("app.workers.scheduled.get_sync_session")
    @patch("app.workers.scheduled.settings")
    def test_cleanup_running_stale_heartbeat_marked_failed(self, mock_settings, mock_get_session):
        """
        **Feature: heartbeat-stuck-detection**
        **Validates: C4 - Running analysis with stale heartbeat is marked as failed**
        
        Test that running analysis with stale heartbeat is marked as failed.
        """
        from app.workers.scheduled import cleanup_stuck_analyses

        # Setup mock settings
        mock_settings.analysis_pending_stuck_minutes = 30
        mock_settings.analysis_running_heartbeat_timeout_minutes = 15

        # Create mock running analysis with stale heartbeat
        mock_analysis = MagicMock()
        mock_analysis.id = uuid.uuid4()
        mock_analysis.repository_id = uuid.uuid4()
        mock_analysis.status = "running"
        mock_analysis.created_at = datetime.now(timezone.utc) - timedelta(hours=1)
        mock_analysis.state_updated_at = datetime.now(timezone.utc) - timedelta(minutes=20)
        mock_analysis.pinned = False

        # Setup mock session
        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_analysis]
        mock_pinned_result = MagicMock()
        mock_pinned_result.scalars.return_value.all.return_value = []
        mock_session.execute.side_effect = [mock_result, mock_pinned_result]
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)
        mock_get_session.return_value = mock_session

        # Run cleanup
        result = cleanup_stuck_analyses()

        # Verify analysis was marked as failed
        assert mock_analysis.status == "failed"
        assert "running-stuck" in mock_analysis.error_message
        assert result["cleaned_count"] == 1
        assert result["heartbeat_timeout_count"] == 1

    @patch("app.workers.scheduled.get_sync_session")
    @patch("app.workers.scheduled.settings")
    def test_cleanup_pinned_analyses_not_touched(self, mock_settings, mock_get_session):
        """
        **Feature: heartbeat-stuck-detection**
        **Validates: C4 - Pinned analyses are NOT touched even if stuck**
        
        Test that pinned analyses are not touched even if they appear stuck.
        """
        from app.workers.scheduled import cleanup_stuck_analyses

        # Setup mock settings
        mock_settings.analysis_pending_stuck_minutes = 30
        mock_settings.analysis_running_heartbeat_timeout_minutes = 15

        # Create mock pinned analysis that would be stuck
        mock_pinned_analysis = MagicMock()
        mock_pinned_analysis.id = uuid.uuid4()
        mock_pinned_analysis.repository_id = uuid.uuid4()
        mock_pinned_analysis.status = "running"
        mock_pinned_analysis.created_at = datetime.now(timezone.utc) - timedelta(hours=2)
        mock_pinned_analysis.state_updated_at = datetime.now(timezone.utc) - timedelta(hours=1)
        mock_pinned_analysis.pinned = True

        # Setup mock session - non-pinned query returns empty, pinned query returns our analysis
        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []  # No non-pinned stuck analyses
        mock_pinned_result = MagicMock()
        mock_pinned_result.scalars.return_value.all.return_value = [mock_pinned_analysis]
        mock_session.execute.side_effect = [mock_result, mock_pinned_result]
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)
        mock_get_session.return_value = mock_session

        # Run cleanup
        result = cleanup_stuck_analyses()

        # Verify pinned analysis was NOT touched
        assert mock_pinned_analysis.status == "running"
        assert result["cleaned_count"] == 0
        assert result["skipped_pinned_count"] == 1


# =============================================================================
# 4. Helper Function Tests
# =============================================================================


class TestIsAnalysisStuckEdgeCases:
    """Test is_analysis_stuck() edge cases.
    
    **Feature: heartbeat-stuck-detection**
    **Validates: C0 - Specification of stuck detection behavior**
    """

    def test_is_analysis_stuck_boundary_pending_exactly_at_timeout(self, mock_analysis, mock_settings):
        """
        **Feature: heartbeat-stuck-detection**
        **Validates: C0 - Boundary condition: exactly at timeout**
        
        Test boundary condition when pending analysis is exactly at timeout.
        """
        from app.api.v1.analyses import is_analysis_stuck

        with patch("app.api.v1.analyses.settings", mock_settings):
            mock_analysis.status = "pending"
            # Exactly at 30 minute boundary - should NOT be stuck (need to exceed)
            mock_analysis.created_at = datetime.now(timezone.utc) - timedelta(minutes=30)

            result = is_analysis_stuck(mock_analysis)
            # At exactly the boundary, it's not stuck yet (need to exceed)
            assert result is False

    def test_is_analysis_stuck_boundary_pending_just_over_timeout(self, mock_analysis, mock_settings):
        """
        **Feature: heartbeat-stuck-detection**
        **Validates: C0 - Boundary condition: just over timeout**
        
        Test boundary condition when pending analysis is just over timeout.
        """
        from app.api.v1.analyses import is_analysis_stuck

        with patch("app.api.v1.analyses.settings", mock_settings):
            mock_analysis.status = "pending"
            # Just over 30 minute boundary - should be stuck
            mock_analysis.created_at = datetime.now(timezone.utc) - timedelta(minutes=30, seconds=1)

            result = is_analysis_stuck(mock_analysis)
            assert result is True

    def test_is_analysis_stuck_handles_naive_datetime(self, mock_analysis, mock_settings):
        """
        **Feature: heartbeat-stuck-detection**
        **Validates: C0 - Handles naive datetime (no timezone info)**
        
        Test that is_analysis_stuck handles naive datetime correctly.
        """
        from app.api.v1.analyses import is_analysis_stuck

        with patch("app.api.v1.analyses.settings", mock_settings):
            mock_analysis.status = "pending"
            # Naive datetime (no timezone info)
            mock_analysis.created_at = datetime.utcnow() - timedelta(minutes=35)

            # Should not raise and should correctly identify as stuck
            result = is_analysis_stuck(mock_analysis)
            assert result is True

    def test_is_analysis_stuck_running_boundary_exactly_at_timeout(self, mock_analysis, mock_settings):
        """
        **Feature: heartbeat-stuck-detection**
        **Validates: C0 - Boundary condition: running exactly at heartbeat timeout**
        
        Test boundary condition when running analysis is exactly at heartbeat timeout.
        """
        from app.api.v1.analyses import is_analysis_stuck

        with patch("app.api.v1.analyses.settings", mock_settings):
            mock_analysis.status = "running"
            # Exactly at 15 minute boundary - should NOT be stuck
            mock_analysis.state_updated_at = datetime.now(timezone.utc) - timedelta(minutes=15)

            result = is_analysis_stuck(mock_analysis)
            assert result is False

    def test_is_analysis_stuck_unknown_status(self, mock_analysis, mock_settings):
        """
        **Feature: heartbeat-stuck-detection**
        **Validates: C0 - Unknown status is treated as not stuck**
        
        Test that unknown status is treated as not stuck.
        """
        from app.api.v1.analyses import is_analysis_stuck

        with patch("app.api.v1.analyses.settings", mock_settings):
            mock_analysis.status = "unknown_status"
            mock_analysis.created_at = datetime.now(timezone.utc) - timedelta(days=30)
            mock_analysis.state_updated_at = datetime.now(timezone.utc) - timedelta(days=30)

            result = is_analysis_stuck(mock_analysis)
            assert result is False


class TestGetStuckReasonEdgeCases:
    """Test get_stuck_reason() edge cases.
    
    **Feature: heartbeat-stuck-detection**
    **Validates: C0 - get_stuck_reason returns correct reasons**
    """

    def test_get_stuck_reason_terminal_states_return_none(self, mock_analysis, mock_settings):
        """
        **Feature: heartbeat-stuck-detection**
        **Validates: C0 - Terminal states return None**
        
        Test that terminal states return None for stuck reason.
        """
        from app.api.v1.analyses import get_stuck_reason

        with patch("app.api.v1.analyses.settings", mock_settings):
            for status in ["completed", "failed", "skipped"]:
                mock_analysis.status = status
                mock_analysis.created_at = datetime.now(timezone.utc) - timedelta(days=30)
                mock_analysis.state_updated_at = datetime.now(timezone.utc) - timedelta(days=30)

                result = get_stuck_reason(mock_analysis)
                assert result is None, f"Status '{status}' should return None"

    def test_get_stuck_reason_unknown_status_returns_none(self, mock_analysis, mock_settings):
        """
        **Feature: heartbeat-stuck-detection**
        **Validates: C0 - Unknown status returns None**
        
        Test that unknown status returns None for stuck reason.
        """
        from app.api.v1.analyses import get_stuck_reason

        with patch("app.api.v1.analyses.settings", mock_settings):
            mock_analysis.status = "unknown_status"
            mock_analysis.created_at = datetime.now(timezone.utc) - timedelta(days=30)
            mock_analysis.state_updated_at = datetime.now(timezone.utc) - timedelta(days=30)

            result = get_stuck_reason(mock_analysis)
            assert result is None


class TestCreateHeartbeatCallback:
    """Test create_heartbeat_callback() function.
    
    **Feature: heartbeat-stuck-detection**
    **Validates: C2 - Heartbeat callback for long operations**
    """

    @patch("app.workers.analysis.update_heartbeat")
    def test_create_heartbeat_callback_returns_callable(self, mock_update_heartbeat):
        """
        **Feature: heartbeat-stuck-detection**
        **Validates: C2 - create_heartbeat_callback returns callable**
        
        Test that create_heartbeat_callback returns a callable.
        """
        from app.workers.analysis import create_heartbeat_callback

        analysis_id = str(uuid.uuid4())
        callback = create_heartbeat_callback(analysis_id)

        assert callable(callback)

    @patch("app.workers.analysis.update_heartbeat")
    def test_create_heartbeat_callback_calls_update_heartbeat(self, mock_update_heartbeat):
        """
        **Feature: heartbeat-stuck-detection**
        **Validates: C2 - Callback calls update_heartbeat with correct analysis_id**
        
        Test that the callback calls update_heartbeat with the correct analysis_id.
        """
        from app.workers.analysis import create_heartbeat_callback

        analysis_id = str(uuid.uuid4())
        callback = create_heartbeat_callback(analysis_id)

        # Call the callback
        callback()

        # Verify update_heartbeat was called with the correct analysis_id
        mock_update_heartbeat.assert_called_once_with(analysis_id)


class TestMarkAnalysisRunningHeartbeat:
    """Test that _mark_analysis_running sets initial heartbeat.
    
    **Feature: heartbeat-stuck-detection**
    **Validates: C2 - Initial heartbeat on worker start**
    """

    @patch("app.workers.analysis.get_sync_session")
    def test_mark_analysis_running_sets_state_updated_at(self, mock_get_session):
        """
        **Feature: heartbeat-stuck-detection**
        **Validates: C2 - _mark_analysis_running sets state_updated_at (initial heartbeat)**
        
        Test that _mark_analysis_running sets state_updated_at for initial heartbeat.
        """
        from app.workers.analysis import _last_heartbeat_times, _mark_analysis_running

        # Clear any existing heartbeat tracking
        _last_heartbeat_times.clear()

        # Create mock analysis
        mock_analysis = MagicMock()
        mock_analysis.id = uuid.uuid4()
        mock_analysis.status = "pending"
        mock_analysis.started_at = None
        mock_analysis.state_updated_at = datetime.utcnow() - timedelta(hours=1)
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

        # Verify state_updated_at was set (initial heartbeat)
        assert mock_analysis.state_updated_at is not None
        # Verify heartbeat tracking was initialized
        assert str(mock_analysis.id) in _last_heartbeat_times


class TestSaveAnalysisResultsHeartbeat:
    """Test that _save_analysis_results updates final heartbeat.
    
    **Feature: heartbeat-stuck-detection**
    **Validates: C2 - Final heartbeat on completion**
    """

    @patch("app.workers.analysis.get_sync_session")
    def test_save_analysis_results_sets_final_heartbeat(self, mock_get_session):
        """
        **Feature: heartbeat-stuck-detection**
        **Validates: C2 - _save_analysis_results sets state_updated_at (final heartbeat)**
        
        Test that _save_analysis_results sets state_updated_at for final heartbeat.
        """
        from app.workers.analysis import _last_heartbeat_times, _save_analysis_results

        # Create mock analysis
        mock_analysis = MagicMock()
        mock_analysis.id = uuid.uuid4()
        mock_analysis.status = "running"
        mock_analysis.started_at = datetime.utcnow() - timedelta(minutes=10)
        mock_analysis.completed_at = None
        mock_analysis.state_updated_at = datetime.utcnow() - timedelta(minutes=5)

        # Add to heartbeat tracking
        _last_heartbeat_times[str(mock_analysis.id)] = time.time()

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

        # Verify state_updated_at was set (final heartbeat)
        assert mock_analysis.state_updated_at is not None
        # Verify heartbeat tracking was cleaned up
        assert str(mock_analysis.id) not in _last_heartbeat_times


class TestMarkAnalysisFailedHeartbeat:
    """Test that _mark_analysis_failed updates final heartbeat.
    
    **Feature: heartbeat-stuck-detection**
    **Validates: C2 - Final heartbeat on failure**
    """

    @patch("app.workers.analysis.publish_analysis_progress")
    @patch("app.workers.analysis.get_sync_session")
    def test_mark_analysis_failed_sets_final_heartbeat(self, mock_get_session, mock_publish):
        """
        **Feature: heartbeat-stuck-detection**
        **Validates: C2 - _mark_analysis_failed sets state_updated_at (final heartbeat)**
        
        Test that _mark_analysis_failed sets state_updated_at for final heartbeat.
        """
        from app.workers.analysis import _last_heartbeat_times, _mark_analysis_failed

        # Create mock analysis
        mock_analysis = MagicMock()
        mock_analysis.id = uuid.uuid4()
        mock_analysis.status = "running"
        mock_analysis.started_at = datetime.utcnow() - timedelta(minutes=10)
        mock_analysis.completed_at = None
        mock_analysis.state_updated_at = datetime.utcnow() - timedelta(minutes=5)
        mock_analysis.error_message = None

        # Add to heartbeat tracking
        _last_heartbeat_times[str(mock_analysis.id)] = time.time()

        # Setup mock session
        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_analysis
        mock_session.execute.return_value = mock_result
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)
        mock_get_session.return_value = mock_session

        # Call the function
        _mark_analysis_failed(str(mock_analysis.id), "Test error")

        # Verify state_updated_at was set (final heartbeat)
        assert mock_analysis.state_updated_at is not None
        # Verify heartbeat tracking was cleaned up
        assert str(mock_analysis.id) not in _last_heartbeat_times


# =============================================================================
# Integration-style Tests
# =============================================================================


class TestHeartbeatIntegration:
    """Integration-style tests for the heartbeat system.
    
    **Feature: heartbeat-stuck-detection**
    **Validates: C0-C4 - Full heartbeat system integration**
    """

    def test_stuck_detection_uses_correct_field_for_pending(self, mock_analysis, mock_settings):
        """
        **Feature: heartbeat-stuck-detection**
        **Validates: C0 - Pending uses created_at, not state_updated_at**
        
        Test that pending stuck detection uses created_at, not state_updated_at.
        """
        from app.api.v1.analyses import is_analysis_stuck

        with patch("app.api.v1.analyses.settings", mock_settings):
            mock_analysis.status = "pending"
            # Old created_at but fresh state_updated_at
            mock_analysis.created_at = datetime.now(timezone.utc) - timedelta(minutes=35)
            mock_analysis.state_updated_at = datetime.now(timezone.utc) - timedelta(minutes=1)

            # Should be stuck based on created_at
            result = is_analysis_stuck(mock_analysis)
            assert result is True

    def test_stuck_detection_uses_correct_field_for_running(self, mock_analysis, mock_settings):
        """
        **Feature: heartbeat-stuck-detection**
        **Validates: C0 - Running uses state_updated_at, not created_at**
        
        Test that running stuck detection uses state_updated_at, not created_at.
        """
        from app.api.v1.analyses import is_analysis_stuck

        with patch("app.api.v1.analyses.settings", mock_settings):
            mock_analysis.status = "running"
            # Fresh created_at but old state_updated_at
            mock_analysis.created_at = datetime.now(timezone.utc) - timedelta(minutes=5)
            mock_analysis.state_updated_at = datetime.now(timezone.utc) - timedelta(minutes=20)

            # Should be stuck based on state_updated_at
            result = is_analysis_stuck(mock_analysis)
            assert result is True

    def test_long_running_analysis_with_heartbeat_not_stuck(self, mock_analysis, mock_settings):
        """
        **Feature: heartbeat-stuck-detection**
        **Validates: C0 - Long running analysis with heartbeat is NOT stuck**
        
        Test that a long-running analysis with recent heartbeat is not considered stuck.
        This is the key scenario that the heartbeat system is designed to handle.
        """
        from app.api.v1.analyses import is_analysis_stuck

        with patch("app.api.v1.analyses.settings", mock_settings):
            mock_analysis.status = "running"
            # Very old created_at (analysis running for 2 hours)
            mock_analysis.created_at = datetime.now(timezone.utc) - timedelta(hours=2)
            # But fresh heartbeat (updated 5 minutes ago)
            mock_analysis.state_updated_at = datetime.now(timezone.utc) - timedelta(minutes=5)

            # Should NOT be stuck because heartbeat is fresh
            result = is_analysis_stuck(mock_analysis)
            assert result is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])