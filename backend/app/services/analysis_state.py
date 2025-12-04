"""AnalysisStateService for centralized analysis state management.

This service provides a single source of truth for all analysis state updates,
ensuring state transitions are validated and events are published for real-time updates.

**Feature: progress-tracking-refactor**
**Validates: Requirements 2.1, 2.2, 2.3, 2.4, 2.5, 3.1, 3.2, 3.3, 5.1, 5.2, 5.3**
"""

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.analysis import Analysis

logger = logging.getLogger(__name__)


# =============================================================================
# Valid Status Values
# =============================================================================

VALID_EMBEDDINGS_STATUS = frozenset(["none", "pending", "running", "completed", "failed"])
VALID_SEMANTIC_CACHE_STATUS = frozenset(["none", "pending", "computing", "completed", "failed"])


# =============================================================================
# State Transition Definitions
# =============================================================================

# Embeddings status transitions (Requirements 5.1, 5.2)
# Key: current status, Value: set of allowed next statuses
EMBEDDINGS_TRANSITIONS: dict[str, set[str]] = {
    "none": {"pending"},
    "pending": {"running", "failed"},
    "running": {"completed", "failed"},
    "completed": set(),  # Terminal state - no transitions allowed
    "failed": {"pending"},  # Can retry
}

# Semantic cache status transitions (Requirements 5.1, 5.2)
SEMANTIC_CACHE_TRANSITIONS: dict[str, set[str]] = {
    "none": {"pending"},
    "pending": {"computing", "failed"},
    "computing": {"completed", "failed"},
    "completed": set(),  # Terminal state - no transitions allowed
    "failed": {"pending"},  # Can retry
}


# =============================================================================
# Exceptions
# =============================================================================


class InvalidStateTransitionError(ValueError):
    """Raised when an invalid state transition is attempted."""

    def __init__(self, current_status: str, new_status: str, status_type: str):
        self.current_status = current_status
        self.new_status = new_status
        self.status_type = status_type
        super().__init__(
            f"Invalid {status_type} transition: '{current_status}' -> '{new_status}'"
        )


class AnalysisNotFoundError(ValueError):
    """Raised when an analysis is not found."""

    def __init__(self, analysis_id: UUID):
        self.analysis_id = analysis_id
        super().__init__(f"Analysis not found: {analysis_id}")


class InvalidProgressValueError(ValueError):
    """Raised when progress value is out of bounds."""

    def __init__(self, progress: int):
        self.progress = progress
        super().__init__(f"Progress value must be between 0 and 100, got: {progress}")


# =============================================================================
# State Transition Validation Functions
# =============================================================================


def is_valid_embeddings_transition(current_status: str, new_status: str) -> bool:
    """
    Check if an embeddings status transition is valid.
    
    Args:
        current_status: Current embeddings_status value
        new_status: Proposed new embeddings_status value
        
    Returns:
        True if transition is valid, False otherwise
    """
    if current_status not in EMBEDDINGS_TRANSITIONS:
        return False
    return new_status in EMBEDDINGS_TRANSITIONS[current_status]


def is_valid_semantic_cache_transition(current_status: str, new_status: str) -> bool:
    """
    Check if a semantic cache status transition is valid.
    
    Args:
        current_status: Current semantic_cache_status value
        new_status: Proposed new semantic_cache_status value
        
    Returns:
        True if transition is valid, False otherwise
    """
    if current_status not in SEMANTIC_CACHE_TRANSITIONS:
        return False
    return new_status in SEMANTIC_CACHE_TRANSITIONS[current_status]


def validate_progress(progress: int) -> None:
    """
    Validate that progress value is within bounds (0-100).
    
    Args:
        progress: Progress value to validate
        
    Raises:
        InvalidProgressValueError: If progress is out of bounds
    """
    if not (0 <= progress <= 100):
        raise InvalidProgressValueError(progress)


# =============================================================================
# AnalysisStateService
# =============================================================================


class AnalysisStateService:
    """
    Centralized service for managing analysis state.
    
    This service ensures:
    - State transitions are validated against allowed transitions
    - Events are published for real-time updates (optional)
    - Audit trail via state_updated_at timestamp
    - Atomic updates using database transactions
    
    **Feature: progress-tracking-refactor**
    **Validates: Requirements 2.1, 2.2, 2.3, 2.4, 2.5, 3.1, 3.2, 3.3, 5.1, 5.2, 5.3**
    """

    def __init__(self, session: Session, publish_events: bool = True):
        """
        Initialize the state service.
        
        Args:
            session: SQLAlchemy session for database operations
            publish_events: Whether to publish Redis events on state changes
        """
        self.session = session
        self.publish_events = publish_events

    def _get_analysis(self, analysis_id: UUID) -> Analysis:
        """
        Get analysis by ID or raise AnalysisNotFoundError.
        
        Args:
            analysis_id: UUID of the analysis
            
        Returns:
            Analysis model instance
            
        Raises:
            AnalysisNotFoundError: If analysis not found
        """
        result = self.session.execute(
            select(Analysis).where(Analysis.id == analysis_id)
        )
        analysis = result.scalar_one_or_none()
        if analysis is None:
            raise AnalysisNotFoundError(analysis_id)
        return analysis

    def _update_timestamp(self, analysis: Analysis) -> None:
        """Update state_updated_at timestamp for polling optimization."""
        analysis.state_updated_at = datetime.now(timezone.utc)

    def _publish_event(
        self,
        analysis: Analysis,
        event_type: str,
        status_data: dict[str, Any],
    ) -> None:
        """
        Publish state change event to Redis pub/sub.
        
        Non-blocking: catches and logs errors without raising.
        Uses the centralized publish_analysis_event function from redis.py.
        
        Args:
            analysis: Analysis model instance
            event_type: Type of event (e.g., 'embeddings_status_changed')
            status_data: Additional status data to include
            
        **Validates: Requirements 7.1, 7.4**
        """
        if not self.publish_events:
            return

        try:
            from app.core.redis import publish_analysis_event
            
            # Call the centralized event publishing function
            # This is wrapped in try/except to ensure non-blocking (Requirements 7.2)
            publish_analysis_event(
                analysis_id=str(analysis.id),
                event_type=event_type,
                status_data=status_data,
            )

        except Exception as e:
            # Non-blocking: log and continue (Requirements 7.2, 7.4)
            logger.warning(f"Failed to publish event: {e}")

    def update_embeddings_status(
        self,
        analysis_id: UUID,
        status: str,
        progress: int | None = None,
        stage: str | None = None,
        message: str | None = None,
        error: str | None = None,
        vectors_count: int | None = None,
    ) -> Analysis:
        """
        Update embeddings status with transition validation.
        
        Args:
            analysis_id: UUID of the analysis
            status: New embeddings_status value
            progress: Progress percentage (0-100)
            stage: Current stage name
            message: Human-readable progress message
            error: Error message (for failed status)
            vectors_count: Number of vectors stored
            
        Returns:
            Updated Analysis model instance
            
        Raises:
            AnalysisNotFoundError: If analysis not found
            InvalidStateTransitionError: If transition is invalid
            InvalidProgressValueError: If progress is out of bounds
            
        **Validates: Requirements 2.1, 2.2, 2.3, 2.4, 5.1, 5.2, 5.3**
        """
        analysis = self._get_analysis(analysis_id)
        current_status = analysis.embeddings_status

        # Validate transition (Requirements 5.1, 5.2)
        if not is_valid_embeddings_transition(current_status, status):
            logger.warning(
                f"Invalid embeddings transition attempted: "
                f"'{current_status}' -> '{status}' for analysis {analysis_id}"
            )
            raise InvalidStateTransitionError(current_status, status, "embeddings_status")

        # Validate progress if provided (Requirements 5.3)
        if progress is not None:
            validate_progress(progress)
            analysis.embeddings_progress = progress

        # Update status
        analysis.embeddings_status = status

        # Update optional fields
        if stage is not None:
            analysis.embeddings_stage = stage
        if message is not None:
            analysis.embeddings_message = message
        if error is not None:
            analysis.embeddings_error = error
        if vectors_count is not None:
            analysis.vectors_count = vectors_count

        # Update timestamp for polling optimization (Requirements 1.4)
        self._update_timestamp(analysis)

        # Commit changes
        self.session.commit()

        # Publish event (Requirements 7.1, 7.4)
        self._publish_event(
            analysis,
            "embeddings_status_changed",
            {
                "embeddings_status": status,
                "embeddings_progress": analysis.embeddings_progress,
                "embeddings_stage": analysis.embeddings_stage,
            },
        )

        return analysis

    def update_semantic_cache_status(
        self,
        analysis_id: UUID,
        status: str,
        cache_data: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> Analysis:
        """
        Update semantic cache status with transition validation.
        
        Args:
            analysis_id: UUID of the analysis
            status: New semantic_cache_status value
            cache_data: Semantic cache data (for completed status)
            error: Error message (for failed status)
            
        Returns:
            Updated Analysis model instance
            
        Raises:
            AnalysisNotFoundError: If analysis not found
            InvalidStateTransitionError: If transition is invalid
            
        **Validates: Requirements 3.1, 3.2, 3.3, 5.1, 5.2**
        """
        analysis = self._get_analysis(analysis_id)
        current_status = analysis.semantic_cache_status

        # Validate transition (Requirements 5.1, 5.2)
        if not is_valid_semantic_cache_transition(current_status, status):
            logger.warning(
                f"Invalid semantic_cache transition attempted: "
                f"'{current_status}' -> '{status}' for analysis {analysis_id}"
            )
            raise InvalidStateTransitionError(
                current_status, status, "semantic_cache_status"
            )

        # Update status
        analysis.semantic_cache_status = status

        # Update optional fields
        if cache_data is not None:
            analysis.semantic_cache = cache_data
        if error is not None:
            # Store error in semantic_cache as JSON for consistency
            if analysis.semantic_cache is None:
                analysis.semantic_cache = {}
            analysis.semantic_cache["error"] = error

        # Update timestamp for polling optimization (Requirements 1.4)
        self._update_timestamp(analysis)

        # Commit changes
        self.session.commit()

        # Publish event (Requirements 7.1, 7.4)
        self._publish_event(
            analysis,
            "semantic_cache_status_changed",
            {
                "semantic_cache_status": status,
                "has_semantic_cache": analysis.semantic_cache is not None,
            },
        )

        return analysis


    # =========================================================================
    # Convenience Methods for Common Transitions
    # =========================================================================

    def mark_embeddings_pending(self, analysis_id: UUID) -> Analysis:
        """
        Mark embeddings as pending (ready to start).
        
        Transition: none -> pending
        
        Args:
            analysis_id: UUID of the analysis
            
        Returns:
            Updated Analysis model instance
            
        **Validates: Requirements 2.1**
        """
        return self.update_embeddings_status(
            analysis_id=analysis_id,
            status="pending",
            progress=0,
            stage="pending",
            message="Waiting for embedding generation to start...",
        )

    def start_embeddings(self, analysis_id: UUID) -> Analysis:
        """
        Start embeddings generation.
        
        Transition: pending -> running
        Sets embeddings_started_at timestamp.
        
        Args:
            analysis_id: UUID of the analysis
            
        Returns:
            Updated Analysis model instance
            
        **Validates: Requirements 2.1**
        """
        analysis = self._get_analysis(analysis_id)
        current_status = analysis.embeddings_status

        # Validate transition
        if not is_valid_embeddings_transition(current_status, "running"):
            logger.warning(
                f"Invalid embeddings transition attempted: "
                f"'{current_status}' -> 'running' for analysis {analysis_id}"
            )
            raise InvalidStateTransitionError(current_status, "running", "embeddings_status")

        # Update status and timestamps
        analysis.embeddings_status = "running"
        analysis.embeddings_progress = 0
        analysis.embeddings_stage = "initializing"
        analysis.embeddings_message = "Starting embedding generation..."
        analysis.embeddings_started_at = datetime.now(timezone.utc)
        analysis.embeddings_error = None  # Clear any previous error

        # Update timestamp for polling optimization
        self._update_timestamp(analysis)

        # Commit changes
        self.session.commit()

        # Publish event
        self._publish_event(
            analysis,
            "embeddings_started",
            {
                "embeddings_status": "running",
                "embeddings_progress": 0,
                "embeddings_stage": "initializing",
            },
        )

        return analysis

    def complete_embeddings(self, analysis_id: UUID, vectors_count: int) -> Analysis:
        """
        Mark embeddings as completed.
        
        Transition: running -> completed
        Sets embeddings_completed_at timestamp.
        Automatically triggers semantic_cache_status -> pending (Requirements 2.5).
        
        Args:
            analysis_id: UUID of the analysis
            vectors_count: Number of vectors stored in Qdrant
            
        Returns:
            Updated Analysis model instance
            
        **Validates: Requirements 2.3, 2.5**
        """
        analysis = self._get_analysis(analysis_id)
        current_status = analysis.embeddings_status

        # Validate transition
        if not is_valid_embeddings_transition(current_status, "completed"):
            logger.warning(
                f"Invalid embeddings transition attempted: "
                f"'{current_status}' -> 'completed' for analysis {analysis_id}"
            )
            raise InvalidStateTransitionError(
                current_status, "completed", "embeddings_status"
            )

        # Update embeddings status
        analysis.embeddings_status = "completed"
        analysis.embeddings_progress = 100
        analysis.embeddings_stage = "completed"
        analysis.embeddings_message = "Embedding generation completed"
        analysis.embeddings_completed_at = datetime.now(timezone.utc)
        analysis.vectors_count = vectors_count

        # Automatically trigger semantic cache pending (Requirements 2.5)
        # Only if semantic_cache_status is 'none'
        if analysis.semantic_cache_status == "none":
            analysis.semantic_cache_status = "pending"
            logger.info(
                f"Auto-triggered semantic_cache_status -> pending for analysis {analysis_id}"
            )

        # Update timestamp for polling optimization
        self._update_timestamp(analysis)

        # Commit changes
        self.session.commit()

        # Publish event
        self._publish_event(
            analysis,
            "embeddings_completed",
            {
                "embeddings_status": "completed",
                "embeddings_progress": 100,
                "vectors_count": vectors_count,
                "semantic_cache_status": analysis.semantic_cache_status,
            },
        )

        return analysis

    def fail_embeddings(self, analysis_id: UUID, error: str) -> Analysis:
        """
        Mark embeddings as failed.
        
        Transition: pending|running -> failed
        
        Args:
            analysis_id: UUID of the analysis
            error: Error message describing the failure
            
        Returns:
            Updated Analysis model instance
            
        **Validates: Requirements 2.4**
        """
        return self.update_embeddings_status(
            analysis_id=analysis_id,
            status="failed",
            stage="error",
            message=f"Embedding generation failed: {error}",
            error=error,
        )

    def start_semantic_cache(self, analysis_id: UUID) -> Analysis:
        """
        Start semantic cache computation.
        
        Transition: pending -> computing
        
        Args:
            analysis_id: UUID of the analysis
            
        Returns:
            Updated Analysis model instance
            
        **Validates: Requirements 3.1**
        """
        return self.update_semantic_cache_status(
            analysis_id=analysis_id,
            status="computing",
        )

    def complete_semantic_cache(
        self, analysis_id: UUID, cache_data: dict[str, Any]
    ) -> Analysis:
        """
        Mark semantic cache as completed.
        
        Transition: computing -> completed
        
        Args:
            analysis_id: UUID of the analysis
            cache_data: Computed semantic cache data
            
        Returns:
            Updated Analysis model instance
            
        **Validates: Requirements 3.2**
        """
        return self.update_semantic_cache_status(
            analysis_id=analysis_id,
            status="completed",
            cache_data=cache_data,
        )

    def fail_semantic_cache(self, analysis_id: UUID, error: str) -> Analysis:
        """
        Mark semantic cache as failed.
        
        Transition: pending|computing -> failed
        
        Args:
            analysis_id: UUID of the analysis
            error: Error message describing the failure
            
        Returns:
            Updated Analysis model instance
            
        **Validates: Requirements 3.3**
        """
        return self.update_semantic_cache_status(
            analysis_id=analysis_id,
            status="failed",
            error=error,
        )

    def update_embeddings_progress(
        self,
        analysis_id: UUID,
        progress: int,
        stage: str,
        message: str | None = None,
    ) -> Analysis:
        """
        Update embeddings progress without changing status.
        
        Use this for incremental progress updates during embedding generation.
        
        Args:
            analysis_id: UUID of the analysis
            progress: Progress percentage (0-100)
            stage: Current stage name
            message: Human-readable progress message
            
        Returns:
            Updated Analysis model instance
            
        Raises:
            InvalidProgressValueError: If progress is out of bounds
            
        **Validates: Requirements 2.2, 5.3**
        """
        # Validate progress
        validate_progress(progress)

        analysis = self._get_analysis(analysis_id)

        # Only allow progress updates when status is 'running'
        if analysis.embeddings_status != "running":
            logger.warning(
                f"Cannot update progress when status is '{analysis.embeddings_status}'"
            )
            return analysis

        # Update progress fields
        analysis.embeddings_progress = progress
        analysis.embeddings_stage = stage
        if message is not None:
            analysis.embeddings_message = message

        # Update timestamp for polling optimization
        self._update_timestamp(analysis)

        # Commit changes
        self.session.commit()

        # Publish event
        self._publish_event(
            analysis,
            "embeddings_progress_updated",
            {
                "embeddings_status": analysis.embeddings_status,
                "embeddings_progress": progress,
                "embeddings_stage": stage,
            },
        )

        return analysis
