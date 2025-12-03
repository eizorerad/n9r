"""Add missing auto_prs columns.

The API referenced fields that didn't exist in the model or database.
This migration adds the missing columns.

Revision ID: 004_fix_auto_prs
Revises: 003_fix_chat_threads
Create Date: 2024-11-30

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "004_fix_auto_prs"
down_revision: str | None = "003_fix_chat_threads"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add missing columns to auto_prs table."""
    # Add base_branch column
    op.add_column(
        "auto_prs",
        sa.Column("base_branch", sa.String(length=255), nullable=True),
    )

    # Add PR stats columns
    op.add_column(
        "auto_prs",
        sa.Column("files_changed", sa.Integer(), nullable=True),
    )
    op.add_column(
        "auto_prs",
        sa.Column("additions", sa.Integer(), nullable=True),
    )
    op.add_column(
        "auto_prs",
        sa.Column("deletions", sa.Integer(), nullable=True),
    )

    # Add test result columns
    op.add_column(
        "auto_prs",
        sa.Column("test_status", sa.String(length=50), nullable=True),
    )
    op.add_column(
        "auto_prs",
        sa.Column("test_output", sa.Text(), nullable=True),
    )

    # Add review feedback column
    op.add_column(
        "auto_prs",
        sa.Column("review_feedback", sa.Text(), nullable=True),
    )

    # Add merged_at timestamp
    op.add_column(
        "auto_prs",
        sa.Column("merged_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    """Remove added columns from auto_prs table."""
    op.drop_column("auto_prs", "merged_at")
    op.drop_column("auto_prs", "review_feedback")
    op.drop_column("auto_prs", "test_output")
    op.drop_column("auto_prs", "test_status")
    op.drop_column("auto_prs", "deletions")
    op.drop_column("auto_prs", "additions")
    op.drop_column("auto_prs", "files_changed")
    op.drop_column("auto_prs", "base_branch")
