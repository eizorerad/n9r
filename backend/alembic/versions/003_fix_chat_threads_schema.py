"""Fix chat_threads schema drift.

The migration had context_type/context_ref but the model uses
context_file/context_issue_id. Also adds missing message_count column.

Revision ID: 003_fix_chat_threads
Revises: 002_fix_org_schema
Create Date: 2024-11-30

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "003_fix_chat_threads"
down_revision: str | None = "002_fix_org_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade database schema."""
    # ===========================================
    # Fix chat_threads table
    # ===========================================

    # Add message_count column
    op.add_column(
        "chat_threads",
        sa.Column("message_count", sa.Integer(), server_default="0", nullable=False),
    )

    # Add context_file column (replacing context_type/context_ref pattern)
    op.add_column(
        "chat_threads",
        sa.Column("context_file", sa.Text(), nullable=True),
    )

    # Add context_issue_id with foreign key
    op.add_column(
        "chat_threads",
        sa.Column("context_issue_id", sa.UUID(), nullable=True),
    )
    op.create_foreign_key(
        "fk_chat_threads_context_issue_id",
        "chat_threads",
        "issues",
        ["context_issue_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # Migrate data: context_type='file' + context_ref -> context_file
    op.execute("""
        UPDATE chat_threads
        SET context_file = context_ref
        WHERE context_type = 'file' AND context_ref IS NOT NULL
    """)

    # Drop old columns (keeping title which is correct)
    op.drop_column("chat_threads", "context_type")
    op.drop_column("chat_threads", "context_ref")


def downgrade() -> None:
    """Downgrade database schema."""
    # Add back old columns
    op.add_column(
        "chat_threads",
        sa.Column("context_type", sa.String(length=50), nullable=True),
    )
    op.add_column(
        "chat_threads",
        sa.Column("context_ref", sa.String(length=255), nullable=True),
    )

    # Migrate data back
    op.execute("""
        UPDATE chat_threads
        SET context_type = 'file', context_ref = context_file
        WHERE context_file IS NOT NULL
    """)

    # Drop new columns
    op.drop_constraint("fk_chat_threads_context_issue_id", "chat_threads", type_="foreignkey")
    op.drop_column("chat_threads", "context_issue_id")
    op.drop_column("chat_threads", "context_file")
    op.drop_column("chat_threads", "message_count")
