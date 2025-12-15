"""Add context_ref column to chat_messages.

Stores the git reference (branch name or commit SHA) for each chat message
to enable context-aware conversations when users switch branches.

Revision ID: 019_add_chat_message_context_ref
Revises: 018_add_repo_content_cache
Create Date: 2025-12-15

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "019_add_chat_message_context_ref"
down_revision: str | None = "018_add_repo_content_cache"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Add context_ref column to chat_messages
    op.add_column(
        "chat_messages",
        sa.Column("context_ref", sa.String(255), nullable=True),
    )
    
    # Add index for efficient filtering by context_ref
    op.create_index(
        "ix_chat_messages_context_ref",
        "chat_messages",
        ["context_ref"],
    )


def downgrade() -> None:
    op.drop_index("ix_chat_messages_context_ref", table_name="chat_messages")
    op.drop_column("chat_messages", "context_ref")
