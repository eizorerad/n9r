"""Add embeddings and semantic cache tracking columns to analyses table.

Adds columns for tracking embeddings generation progress and semantic cache
computation status. PostgreSQL becomes the single source of truth for all
analysis state, replacing the previous Redis-based tracking.

Revision ID: 007_add_embeddings_tracking
Revises: 006_add_ai_scan_cache
Create Date: 2024-12-04

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import TIMESTAMP

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "007_add_embeddings_tracking"
down_revision: str | None = "006_add_ai_scan_cache"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add embeddings tracking and semantic cache status columns."""
    # Embeddings status tracking columns
    op.add_column(
        "analyses",
        sa.Column(
            "embeddings_status",
            sa.String(20),
            server_default="none",
            nullable=False,
        ),
    )
    op.add_column(
        "analyses",
        sa.Column(
            "embeddings_progress",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
    )
    op.add_column(
        "analyses",
        sa.Column(
            "embeddings_stage",
            sa.String(50),
            nullable=True,
        ),
    )
    op.add_column(
        "analyses",
        sa.Column(
            "embeddings_message",
            sa.Text(),
            nullable=True,
        ),
    )
    op.add_column(
        "analyses",
        sa.Column(
            "embeddings_error",
            sa.Text(),
            nullable=True,
        ),
    )
    op.add_column(
        "analyses",
        sa.Column(
            "embeddings_started_at",
            TIMESTAMP(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        "analyses",
        sa.Column(
            "embeddings_completed_at",
            TIMESTAMP(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        "analyses",
        sa.Column(
            "vectors_count",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
    )

    # Semantic cache status tracking column
    op.add_column(
        "analyses",
        sa.Column(
            "semantic_cache_status",
            sa.String(20),
            server_default="none",
            nullable=False,
        ),
    )

    # State update timestamp for polling optimization
    op.add_column(
        "analyses",
        sa.Column(
            "state_updated_at",
            TIMESTAMP(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
    )

    # Add CHECK constraints for valid status values
    # Requirements 6.1: embeddings_status valid values
    op.create_check_constraint(
        "ck_analyses_embeddings_status",
        "analyses",
        "embeddings_status IN ('none', 'pending', 'running', 'completed', 'failed')",
    )

    # Requirements 6.2: semantic_cache_status valid values
    op.create_check_constraint(
        "ck_analyses_semantic_cache_status",
        "analyses",
        "semantic_cache_status IN ('none', 'pending', 'computing', 'completed', 'failed')",
    )

    # Requirements 6.3: embeddings_progress bounds (0-100)
    op.create_check_constraint(
        "ck_analyses_embeddings_progress",
        "analyses",
        "embeddings_progress >= 0 AND embeddings_progress <= 100",
    )

    # Add indexes for efficient queries (Requirements 1.3)
    op.create_index(
        "ix_analyses_embeddings_status",
        "analyses",
        ["embeddings_status"],
    )
    op.create_index(
        "ix_analyses_state_updated_at",
        "analyses",
        ["state_updated_at"],
    )
    op.create_index(
        "ix_analyses_repository_status",
        "analyses",
        ["repository_id", "status"],
    )

    # Backfill existing completed analyses (Requirements 6.4)
    # Set embeddings_status='completed' for analyses with semantic_cache
    # Set semantic_cache_status='completed' for analyses with semantic_cache data
    op.execute(
        """
        UPDATE analyses
        SET embeddings_status = 'completed',
            embeddings_progress = 100,
            semantic_cache_status = 'completed',
            state_updated_at = NOW()
        WHERE semantic_cache IS NOT NULL
        """
    )


def downgrade() -> None:
    """Remove embeddings tracking and semantic cache status columns."""
    # Drop indexes
    op.drop_index("ix_analyses_repository_status", table_name="analyses")
    op.drop_index("ix_analyses_state_updated_at", table_name="analyses")
    op.drop_index("ix_analyses_embeddings_status", table_name="analyses")

    # Drop CHECK constraints
    op.drop_constraint("ck_analyses_embeddings_progress", "analyses", type_="check")
    op.drop_constraint("ck_analyses_semantic_cache_status", "analyses", type_="check")
    op.drop_constraint("ck_analyses_embeddings_status", "analyses", type_="check")

    # Drop columns
    op.drop_column("analyses", "state_updated_at")
    op.drop_column("analyses", "semantic_cache_status")
    op.drop_column("analyses", "vectors_count")
    op.drop_column("analyses", "embeddings_completed_at")
    op.drop_column("analyses", "embeddings_started_at")
    op.drop_column("analyses", "embeddings_error")
    op.drop_column("analyses", "embeddings_message")
    op.drop_column("analyses", "embeddings_stage")
    op.drop_column("analyses", "embeddings_progress")
    op.drop_column("analyses", "embeddings_status")
