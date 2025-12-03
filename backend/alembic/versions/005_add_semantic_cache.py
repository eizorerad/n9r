"""Add semantic_cache column to analyses table.

Stores cached semantic analysis results (architecture health, clusters,
outliers, similar code) in PostgreSQL to avoid Qdrant queries when viewing.

Revision ID: 005_add_semantic_cache
Revises: 004_fix_auto_prs
Create Date: 2024-12-03

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "005_add_semantic_cache"
down_revision: str | None = "004_fix_auto_prs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add semantic_cache JSONB column to analyses table."""
    op.add_column(
        "analyses",
        sa.Column("semantic_cache", JSONB, nullable=True),
    )


def downgrade() -> None:
    """Remove semantic_cache column from analyses table."""
    op.drop_column("analyses", "semantic_cache")
