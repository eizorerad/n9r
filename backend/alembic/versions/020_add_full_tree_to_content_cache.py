"""Add full_tree column to repo_content_tree.

Adds a full_tree JSONB column to store complete directory structure
with metadata (type, size) for commit-centric file explorer.

Revision ID: 020_add_full_tree
Revises: 019_add_chat_message_context_ref
Create Date: 2024-12-15

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "020_add_full_tree"
down_revision: str | None = "019_add_chat_message_context_ref"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add full_tree column for complete directory structure."""
    # Add full_tree column - stores complete tree with directories and metadata
    # Format: [{"name": "src", "path": "src", "type": "directory", "size": null, "children": [...]}, ...]
    op.add_column(
        "repo_content_tree",
        sa.Column("full_tree", JSONB(), nullable=True),
    )


def downgrade() -> None:
    """Remove full_tree column."""
    op.drop_column("repo_content_tree", "full_tree")
