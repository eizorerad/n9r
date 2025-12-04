"""Add ai_scan_cache column to analyses table.

Stores cached AI scan results (multi-model LLM analysis findings,
issues, investigation results) in PostgreSQL tied to commit SHA.

Revision ID: 006_add_ai_scan_cache
Revises: 005_add_semantic_cache
Create Date: 2024-12-04

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "006_add_ai_scan_cache"
down_revision: str | None = "005_add_semantic_cache"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add ai_scan_cache JSONB column to analyses table."""
    op.add_column(
        "analyses",
        sa.Column("ai_scan_cache", JSONB, nullable=True),
    )


def downgrade() -> None:
    """Remove ai_scan_cache column from analyses table."""
    op.drop_column("analyses", "ai_scan_cache")
