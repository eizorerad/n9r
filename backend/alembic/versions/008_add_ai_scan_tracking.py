"""Add AI scan tracking columns to analyses table.

Adds columns for tracking AI scan progress and status. This follows the same
pattern as embeddings tracking (migration 007), making PostgreSQL the single
source of truth for AI scan state management.

Revision ID: 008_add_ai_scan_tracking
Revises: 007_add_embeddings_tracking
Create Date: 2024-12-05

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import TIMESTAMP

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "008_add_ai_scan_tracking"
down_revision: str | None = "007_add_embeddings_tracking"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add AI scan tracking columns."""
    # AI scan status tracking column
    # Valid values: 'none', 'pending', 'running', 'completed', 'failed', 'skipped'
    op.add_column(
        "analyses",
        sa.Column(
            "ai_scan_status",
            sa.String(20),
            server_default="none",
            nullable=False,
        ),
    )

    # AI scan progress percentage (0-100)
    op.add_column(
        "analyses",
        sa.Column(
            "ai_scan_progress",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
    )

    # Current AI scan stage
    # Values: 'initializing', 'cloning', 'generating_view', 'scanning', 'merging', 'investigating', 'completed'
    op.add_column(
        "analyses",
        sa.Column(
            "ai_scan_stage",
            sa.String(50),
            nullable=True,
        ),
    )

    # Human-readable progress message
    op.add_column(
        "analyses",
        sa.Column(
            "ai_scan_message",
            sa.Text(),
            nullable=True,
        ),
    )

    # Error message if ai_scan_status is 'failed'
    op.add_column(
        "analyses",
        sa.Column(
            "ai_scan_error",
            sa.Text(),
            nullable=True,
        ),
    )

    # Timestamp when AI scan started
    op.add_column(
        "analyses",
        sa.Column(
            "ai_scan_started_at",
            TIMESTAMP(timezone=True),
            nullable=True,
        ),
    )

    # Timestamp when AI scan completed
    op.add_column(
        "analyses",
        sa.Column(
            "ai_scan_completed_at",
            TIMESTAMP(timezone=True),
            nullable=True,
        ),
    )

    # Add CHECK constraint for valid ai_scan_status values
    op.create_check_constraint(
        "ck_analyses_ai_scan_status",
        "analyses",
        "ai_scan_status IN ('none', 'pending', 'running', 'completed', 'failed', 'skipped')",
    )

    # Add CHECK constraint for ai_scan_progress bounds (0-100)
    op.create_check_constraint(
        "ck_analyses_ai_scan_progress",
        "analyses",
        "ai_scan_progress >= 0 AND ai_scan_progress <= 100",
    )

    # Add index for efficient queries on ai_scan_status
    op.create_index(
        "ix_analyses_ai_scan_status",
        "analyses",
        ["ai_scan_status"],
    )

    # Backfill existing analyses with ai_scan_cache to 'completed' status
    op.execute(
        """
        UPDATE analyses
        SET ai_scan_status = 'completed',
            ai_scan_progress = 100,
            state_updated_at = NOW()
        WHERE ai_scan_cache IS NOT NULL
        """
    )


def downgrade() -> None:
    """Remove AI scan tracking columns."""
    # Drop index
    op.drop_index("ix_analyses_ai_scan_status", table_name="analyses")

    # Drop CHECK constraints
    op.drop_constraint("ck_analyses_ai_scan_progress", "analyses", type_="check")
    op.drop_constraint("ck_analyses_ai_scan_status", "analyses", type_="check")

    # Drop columns
    op.drop_column("analyses", "ai_scan_completed_at")
    op.drop_column("analyses", "ai_scan_started_at")
    op.drop_column("analyses", "ai_scan_error")
    op.drop_column("analyses", "ai_scan_message")
    op.drop_column("analyses", "ai_scan_stage")
    op.drop_column("analyses", "ai_scan_progress")
    op.drop_column("analyses", "ai_scan_status")
