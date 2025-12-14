"""Ensure chat_messages.role is stored as TEXT (not Postgres enum).

Some DBs can end up with chat_messages.role still typed as an enum, or with enum
drift. This migration forces the column to TEXT in an idempotent way.

Revision ID: 015_fix_chat_role
Revises: 014_chat_messages_role_to_text
Create Date: 2025-12-13

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "015_fix_chat_role"
down_revision: str | None = "014_chat_messages_role_to_text"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Force role column to TEXT if it is not already."""
    op.execute(
        """
        DO $$
        DECLARE
          udt text;
        BEGIN
          SELECT c.udt_name INTO udt
          FROM information_schema.columns c
          WHERE c.table_name = 'chat_messages' AND c.column_name = 'role';

          IF udt IS NULL THEN
            RAISE NOTICE 'chat_messages.role not found';
            RETURN;
          END IF;

          IF udt NOT IN ('text', 'varchar', 'bpchar') THEN
            EXECUTE 'ALTER TABLE chat_messages ALTER COLUMN role TYPE text USING role::text';
          END IF;

          EXECUTE 'UPDATE chat_messages SET role = lower(role)';
        END $$;
        """
    )


def downgrade() -> None:
    """No-op downgrade (we do not restore enum types)."""
    pass