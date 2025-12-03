"""Fix organization schema drift.

The initial migration created organizations table for GitHub organizations,
but the model represents a multi-tenant SaaS organization. This migration
aligns the database schema with the ORM model.

Revision ID: 002_fix_org_schema
Revises: 001_initial
Create Date: 2024-11-30

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "002_fix_org_schema"
down_revision: str | None = "001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade database schema."""
    # ===========================================
    # 1. Fix organizations table
    # ===========================================

    # Add new columns required by the model
    # Note: updated_at already exists from BaseModel in initial migration
    op.add_column(
        "organizations",
        sa.Column("owner_id", sa.UUID(), nullable=True),
    )
    op.add_column(
        "organizations",
        sa.Column("slug", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "organizations",
        sa.Column(
            "plan",
            sa.String(length=20),
            server_default="solo",
            nullable=False,
        ),
    )

    # Create foreign key for owner_id
    op.create_foreign_key(
        "fk_organizations_owner_id",
        "organizations",
        "users",
        ["owner_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # Create unique index on slug
    op.create_index("ix_organizations_slug", "organizations", ["slug"], unique=True)

    # Note: We keep github_id, display_name, avatar_url, installation_id
    # as they may be useful for GitHub org integration. They're nullable
    # so won't conflict with the model (model just ignores them).

    # ===========================================
    # 2. Rename organization_members to members
    # ===========================================
    op.rename_table("organization_members", "members")

    # Update the unique constraint name
    op.drop_constraint("uq_org_user", "members", type_="unique")
    op.create_unique_constraint("uq_member_org_user", "members", ["org_id", "user_id"])

    # Add updated_at column to members (doesn't exist in initial migration)
    op.add_column(
        "members",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    # Create indexes on members table
    op.create_index("ix_members_org_id", "members", ["org_id"])
    op.create_index("ix_members_user_id", "members", ["user_id"])


def downgrade() -> None:
    """Downgrade database schema."""
    # ===========================================
    # 1. Revert members table to organization_members
    # ===========================================
    op.drop_index("ix_members_user_id", table_name="members")
    op.drop_index("ix_members_org_id", table_name="members")
    op.drop_column("members", "updated_at")
    op.drop_constraint("uq_member_org_user", "members", type_="unique")
    op.create_unique_constraint("uq_org_user", "members", ["org_id", "user_id"])
    op.rename_table("members", "organization_members")

    # ===========================================
    # 2. Revert organizations table
    # Note: Don't drop updated_at - it existed in initial migration
    # ===========================================
    op.drop_index("ix_organizations_slug", table_name="organizations")
    op.drop_constraint("fk_organizations_owner_id", "organizations", type_="foreignkey")
    op.drop_column("organizations", "plan")
    op.drop_column("organizations", "slug")
    op.drop_column("organizations", "owner_id")
