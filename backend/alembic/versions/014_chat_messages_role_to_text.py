"""Convert chat_messages.role from Postgres enum to TEXT.

Some databases are missing the underlying enum type (messagerole), causing inserts
to fail. Storing role as TEXT avoids enum drift and keeps compatibility.

Revision ID: 014_chat_messages_role_to_text
Revises: 013_add_chat_messages_updated_at
Create Date: 2025-12-13

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "014_chat_messages_role_to_text"
down_revision: str | None = "013_add_chat_messages_updated_at"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Convert role column to TEXT and normalize values.

    Must be robust even if the enum type is missing or the column is already text.
    """
    op.execute(
        """
        DO $$
        DECLARE
          udt text;
        BEGIN
          SELECT c.udt_name INTO udt
          FROM information_schema.columns c
          WHERE c.table_name = 'chat_messages' AND c.column_name = 'role';

          -- If already text-like, do nothing
          IF udt IN ('text', 'varchar', 'bpchar') THEN
            NULL;
          ELSE
            -- Best-effort cast to text
            EXECUTE 'ALTER TABLE chat_messages ALTER COLUMN role TYPE text USING role::text';
          END IF;
        END $$;
        """
    )

    # Normalize to lowercase to match API usage ("user", "assistant", "system")
    op.execute("UPDATE chat_messages SET role = lower(role)")

    # Drop enum type if it exists (safe cleanup)
    op.execute("DO $$ BEGIN DROP TYPE IF EXISTS messagerole; EXCEPTION WHEN others THEN END $$;")


def downgrade() -> None:
    """Best-effort downgrade: recreate enum and cast back."""
    op.execute("CREATE TYPE messagerole AS ENUM ('user', 'assistant', 'system')")
    op.execute(
        """
        ALTER TABLE chat_messages
        ALTER COLUMN role TYPE messagerole
        USING role::messagerole
        """
    )