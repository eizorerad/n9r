"""Add updated_at column to chat_messages table.

The ORM base model includes updated_at, but some existing databases may have
chat_messages without this column. This migration adds it and backfills from
created_at to keep ordering/queries consistent.

Revision ID: 013_add_chat_messages_updated_at
Revises: 012_add_chat_thread_model
Create Date: 2025-12-13

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "013_add_chat_messages_updated_at"
down_revision: str | None = "012_add_chat_thread_model"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add updated_at column and backfill."""
    op.add_column(
        "chat_messages",
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Backfill existing rows
    op.execute("UPDATE chat_messages SET updated_at = created_at WHERE updated_at IS NULL")
    # Make non-null going forward
    op.alter_column("chat_messages", "updated_at", nullable=False)


def downgrade() -> None:
    """Remove updated_at column."""
    op.drop_column("chat_messages", "updated_at")