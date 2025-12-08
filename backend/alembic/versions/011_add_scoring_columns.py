"""Add impact_score and risk_score columns for transparent scoring.

Revision ID: 011
Revises: 010
Create Date: 2025-12-08

This migration adds scoring columns to support the transparent scoring formula feature:
- impact_score to dead_code table (Dead Code Impact Score 0-100)
- risk_score to file_churn table (Hot Spot Risk Score 0-100)

Requirements: 5.4
"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "011_add_scoring_columns"
down_revision: str | None = "010_gen_insights_status"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    """Add impact_score to dead_code and risk_score to file_churn tables."""
    # Add impact_score column to dead_code table
    op.add_column(
        "dead_code",
        sa.Column("impact_score", sa.Float(), nullable=False, server_default="0.0"),
    )

    # Add risk_score column to file_churn table
    op.add_column(
        "file_churn",
        sa.Column("risk_score", sa.Float(), nullable=False, server_default="0.0"),
    )


def downgrade() -> None:
    """Remove impact_score from dead_code and risk_score from file_churn tables."""
    op.drop_column("file_churn", "risk_score")
    op.drop_column("dead_code", "impact_score")
