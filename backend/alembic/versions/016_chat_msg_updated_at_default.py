"""Set server default for chat_messages.updated_at.

Some DBs have chat_messages.updated_at as NOT NULL but without a server default,
causing inserts to fail when the ORM doesn't explicitly set updated_at.

Revision ID: 016_chat_msg_updated_at_default
Revises: 015_deprecated
Create Date: 2025-12-13

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "016_chat_msg_updated_at_default"
down_revision: str | None = "015_deprecated"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add server default and backfill."""
    # Backfill any existing NULLs (defensive)
    op.execute("UPDATE chat_messages SET updated_at = created_at WHERE updated_at IS NULL")

    # Ensure future inserts get a value
    op.alter_column(
        "chat_messages",
        "updated_at",
        server_default=sa.text("now()"),
        existing_type=sa.DateTime(timezone=True),
        existing_nullable=False,
    )


def downgrade() -> None:
    """Remove server default."""
    op.alter_column(
        "chat_messages",
        "updated_at",
        server_default=None,
        existing_type=sa.DateTime(timezone=True),
        existing_nullable=False,
    )
