"""Add analysis pinned column for retention policy.

Revision ID: 017_add_analysis_pinned
Revises: 016_chat_msg_updated_at_default
Create Date: 2025-12-14

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "017_add_analysis_pinned"
down_revision: str | None = "016_chat_msg_updated_at_default"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add pinned column to analyses table."""
    op.add_column(
        "analyses",
        sa.Column(
            "pinned",
            sa.Boolean(),
            server_default="false",
            nullable=False,
        ),
    )
    # Create index for efficient filtering during cleanup
    op.create_index("ix_analyses_pinned", "analyses", ["pinned"])


def downgrade() -> None:
    """Remove pinned column from analyses table."""
    op.drop_index("ix_analyses_pinned", table_name="analyses")
    op.drop_column("analyses", "pinned")
