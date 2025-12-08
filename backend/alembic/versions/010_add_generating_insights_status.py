"""Add generating_insights to semantic_cache_status CHECK constraint.

Revision ID: 010
Revises: 009
Create Date: 2025-12-08

This migration adds 'generating_insights' as a valid value for semantic_cache_status.
This status is used to indicate when the LLM is generating AI insights after
cluster analysis completes but before the semantic cache is marked as completed.
"""

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "010_gen_insights_status"
down_revision: str | None = "009_add_architecture_findings"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    """Add generating_insights to semantic_cache_status CHECK constraint."""
    # Drop the old constraint
    op.drop_constraint("ck_analyses_semantic_cache_status", "analyses", type_="check")

    # Create new constraint with generating_insights included
    op.create_check_constraint(
        "ck_analyses_semantic_cache_status",
        "analyses",
        "semantic_cache_status IN ('none', 'pending', 'computing', 'generating_insights', 'completed', 'failed')",
    )


def downgrade() -> None:
    """Remove generating_insights from semantic_cache_status CHECK constraint."""
    # Drop the new constraint
    op.drop_constraint("ck_analyses_semantic_cache_status", "analyses", type_="check")

    # Restore original constraint (without generating_insights)
    op.create_check_constraint(
        "ck_analyses_semantic_cache_status",
        "analyses",
        "semantic_cache_status IN ('none', 'pending', 'computing', 'completed', 'failed')",
    )
