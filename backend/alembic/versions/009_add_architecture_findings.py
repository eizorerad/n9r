"""Add architecture findings tables for Semantic AI Insights.

Creates tables for dead_code, file_churn, and semantic_ai_insights to support
the Semantic AI Insights feature. These tables store architecture analysis
findings that are persisted to PostgreSQL as the single source of truth.

Revision ID: 009_add_architecture_findings
Revises: 008_add_ai_scan_tracking
Create Date: 2024-12-07

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "009_add_architecture_findings"
down_revision: str | None = "008_add_ai_scan_tracking"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create architecture findings tables."""
    # ==========================================================================
    # dead_code table - Dead code findings with dismissal support
    # Requirements: 7.1
    # ==========================================================================
    op.create_table(
        "dead_code",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("analysis_id", UUID(as_uuid=True), sa.ForeignKey("analyses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("repository_id", UUID(as_uuid=True), sa.ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False),
        sa.Column("file_path", sa.String(500), nullable=False),
        sa.Column("function_name", sa.String(200), nullable=False),
        sa.Column("line_start", sa.Integer(), nullable=False),
        sa.Column("line_end", sa.Integer(), nullable=False),
        sa.Column("line_count", sa.Integer(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("evidence", sa.String(500), nullable=False),
        sa.Column("suggested_action", sa.String(500), nullable=False),
        sa.Column("is_dismissed", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("dismissed_at", TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_at", TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("NOW()")),
    )

    # Indexes for dead_code table
    op.create_index("ix_dead_code_analysis_id", "dead_code", ["analysis_id"])
    op.create_index("ix_dead_code_repository_id", "dead_code", ["repository_id"])

    # ==========================================================================
    # file_churn table - Hot spot findings
    # Requirements: 7.2
    # ==========================================================================
    op.create_table(
        "file_churn",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("analysis_id", UUID(as_uuid=True), sa.ForeignKey("analyses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("file_path", sa.String(500), nullable=False),
        sa.Column("changes_90d", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("coverage_rate", sa.Float(), nullable=True),
        sa.Column("unique_authors", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("risk_factors", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("suggested_action", sa.String(500), nullable=True),
        sa.Column("created_at", TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        # Unique constraint per analysis + file
        sa.UniqueConstraint("analysis_id", "file_path", name="uq_file_churn_analysis_file"),
    )

    # Indexes for file_churn table
    op.create_index("ix_file_churn_analysis_id", "file_churn", ["analysis_id"])
    # Partial index for hot files (changes_90d > 10)
    op.create_index(
        "ix_file_churn_hot_files",
        "file_churn",
        ["changes_90d"],
        postgresql_where=sa.text("changes_90d > 10"),
    )

    # ==========================================================================
    # semantic_ai_insights table - AI-generated recommendations
    # Requirements: 5.4
    # ==========================================================================
    op.create_table(
        "semantic_ai_insights",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("analysis_id", UUID(as_uuid=True), sa.ForeignKey("analyses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("repository_id", UUID(as_uuid=True), sa.ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False),
        sa.Column("insight_type", sa.String(50), nullable=False),  # 'dead_code', 'hot_spot', 'architecture'
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("priority", sa.String(20), nullable=False),  # 'high', 'medium', 'low'
        sa.Column("affected_files", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("evidence", sa.Text(), nullable=True),
        sa.Column("suggested_action", sa.Text(), nullable=True),
        sa.Column("is_dismissed", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("dismissed_at", TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_at", TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("NOW()")),
    )

    # Indexes for semantic_ai_insights table
    op.create_index("ix_semantic_ai_insights_analysis_id", "semantic_ai_insights", ["analysis_id"])
    op.create_index("ix_semantic_ai_insights_repository_id", "semantic_ai_insights", ["repository_id"])
    op.create_index("ix_semantic_ai_insights_type", "semantic_ai_insights", ["insight_type"])

    # CHECK constraints for valid values
    op.create_check_constraint(
        "ck_semantic_ai_insights_priority",
        "semantic_ai_insights",
        "priority IN ('high', 'medium', 'low')",
    )
    op.create_check_constraint(
        "ck_semantic_ai_insights_type",
        "semantic_ai_insights",
        "insight_type IN ('dead_code', 'hot_spot', 'architecture')",
    )


def downgrade() -> None:
    """Drop architecture findings tables."""
    # Drop semantic_ai_insights table
    op.drop_constraint("ck_semantic_ai_insights_type", "semantic_ai_insights", type_="check")
    op.drop_constraint("ck_semantic_ai_insights_priority", "semantic_ai_insights", type_="check")
    op.drop_index("ix_semantic_ai_insights_type", table_name="semantic_ai_insights")
    op.drop_index("ix_semantic_ai_insights_repository_id", table_name="semantic_ai_insights")
    op.drop_index("ix_semantic_ai_insights_analysis_id", table_name="semantic_ai_insights")
    op.drop_table("semantic_ai_insights")

    # Drop file_churn table
    op.drop_index("ix_file_churn_hot_files", table_name="file_churn")
    op.drop_index("ix_file_churn_analysis_id", table_name="file_churn")
    op.drop_table("file_churn")

    # Drop dead_code table
    op.drop_index("ix_dead_code_repository_id", table_name="dead_code")
    op.drop_index("ix_dead_code_analysis_id", table_name="dead_code")
    op.drop_table("dead_code")
