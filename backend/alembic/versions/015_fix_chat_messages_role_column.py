"""DEPRECATED no-op migration.

This file previously used an invalid revision id (longer than 32 chars) and
caused Alembic upgrade failures. It is now a no-op revision that depends on
015_fix_chat_role so Alembic can load it safely.

Revision ID: 015_deprecated
Revises: 015_fix_chat_role
Create Date: 2025-12-13
"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "015_deprecated"
down_revision: str | None = "015_fix_chat_role"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
