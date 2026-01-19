"""Add model column to chat_threads table.

Stores the default LLM model (provider-prefixed) selected for a chat thread.

Revision ID: 012_add_chat_thread_model
Revises: 011_add_scoring_columns
Create Date: 2025-12-13

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "012_add_chat_thread_model"
down_revision: str | None = "011_add_scoring_columns"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add model column to chat_threads table."""
    op.add_column(
        "chat_threads",
        sa.Column("model", sa.String(length=255), nullable=True),
    )


def downgrade() -> None:
    """Remove model column from chat_threads table."""
    op.drop_column("chat_threads", "model")
