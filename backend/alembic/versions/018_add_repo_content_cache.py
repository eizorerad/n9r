"""Add repository content cache tables.

Creates tables for repo_content_cache, repo_content_objects, and repo_content_tree
to support caching repository file content in PostgreSQL (metadata) and MinIO (bytes).

Revision ID: 018_add_repo_content_cache
Revises: 017_add_analysis_pinned
Create Date: 2024-12-14

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "018_add_repo_content_cache"
down_revision: str | None = "017_add_analysis_pinned"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create repository content cache tables."""
    # ==========================================================================
    # repo_content_cache table - Cache metadata per repository/commit
    # Requirements: 2.1, 3.1, 4.1, 4.3
    # ==========================================================================
    op.create_table(
        "repo_content_cache",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("repository_id", UUID(as_uuid=True), sa.ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False),
        sa.Column("commit_sha", sa.String(40), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("file_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_size_bytes", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        # Unique constraint on (repository_id, commit_sha)
        sa.UniqueConstraint("repository_id", "commit_sha", name="uq_repo_content_cache_repo_commit"),
    )

    # Indexes for repo_content_cache
    op.create_index("ix_repo_content_cache_repository_id", "repo_content_cache", ["repository_id"])
    op.create_index("ix_repo_content_cache_lookup", "repo_content_cache", ["repository_id", "commit_sha"])
    # Partial index for non-ready caches (for GC queries)
    op.create_index(
        "ix_repo_content_cache_status",
        "repo_content_cache",
        ["status"],
        postgresql_where=sa.text("status != 'ready'"),
    )

    # CHECK constraint for valid status values
    op.create_check_constraint(
        "ck_repo_content_cache_status",
        "repo_content_cache",
        "status IN ('pending', 'uploading', 'ready', 'failed')",
    )

    # ==========================================================================
    # repo_content_objects table - Individual file objects
    # Requirements: 2.2, 2.3
    # ==========================================================================
    op.create_table(
        "repo_content_objects",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("cache_id", UUID(as_uuid=True), sa.ForeignKey("repo_content_cache.id", ondelete="CASCADE"), nullable=False),
        sa.Column("path", sa.String(1024), nullable=False),
        sa.Column("object_key", sa.String(255), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="uploading"),
        sa.Column("created_at", TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        # Unique constraint on (cache_id, path)
        sa.UniqueConstraint("cache_id", "path", name="uq_repo_content_objects_cache_path"),
    )

    # Indexes for repo_content_objects
    op.create_index("ix_repo_content_objects_cache_id", "repo_content_objects", ["cache_id"])
    # Partial index for non-ready objects (for status queries)
    op.create_index(
        "ix_repo_content_objects_status",
        "repo_content_objects",
        ["status"],
        postgresql_where=sa.text("status != 'ready'"),
    )

    # CHECK constraint for valid status values
    op.create_check_constraint(
        "ck_repo_content_objects_status",
        "repo_content_objects",
        "status IN ('uploading', 'ready', 'failed', 'deleted')",
    )

    # ==========================================================================
    # repo_content_tree table - Cached tree structure (denormalized)
    # Requirements: 1.1
    # ==========================================================================
    op.create_table(
        "repo_content_tree",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("cache_id", UUID(as_uuid=True), sa.ForeignKey("repo_content_cache.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tree", JSONB(), nullable=False),
        sa.Column("created_at", TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        # Unique constraint on cache_id (one tree per cache)
        sa.UniqueConstraint("cache_id", name="uq_repo_content_tree_cache"),
    )

    # Index for repo_content_tree
    op.create_index("ix_repo_content_tree_cache_id", "repo_content_tree", ["cache_id"])


def downgrade() -> None:
    """Drop repository content cache tables."""
    # Drop repo_content_tree table
    op.drop_index("ix_repo_content_tree_cache_id", table_name="repo_content_tree")
    op.drop_table("repo_content_tree")

    # Drop repo_content_objects table
    op.drop_constraint("ck_repo_content_objects_status", "repo_content_objects", type_="check")
    op.drop_index("ix_repo_content_objects_status", table_name="repo_content_objects")
    op.drop_index("ix_repo_content_objects_cache_id", table_name="repo_content_objects")
    op.drop_table("repo_content_objects")

    # Drop repo_content_cache table
    op.drop_constraint("ck_repo_content_cache_status", "repo_content_cache", type_="check")
    op.drop_index("ix_repo_content_cache_status", table_name="repo_content_cache")
    op.drop_index("ix_repo_content_cache_lookup", table_name="repo_content_cache")
    op.drop_index("ix_repo_content_cache_repository_id", table_name="repo_content_cache")
    op.drop_table("repo_content_cache")
