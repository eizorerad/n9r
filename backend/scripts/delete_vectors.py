"""Admin script to delete vectors for a specific repository and commit.

Usage:
    # Delete vectors for a specific commit
    python -m scripts.delete_vectors --repo-id <UUID> --commit-sha <40-hex>

    # Delete ALL vectors for a repository (dangerous!)
    python -m scripts.delete_vectors --repo-id <UUID> --all-commits

    # Dry run (show what would be deleted)
    python -m scripts.delete_vectors --repo-id <UUID> --commit-sha <sha> --dry-run
"""

import argparse
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.vector_store import VectorStoreService, get_qdrant_client


def main():
    parser = argparse.ArgumentParser(
        description="Delete vectors from Qdrant for a repository/commit",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--repo-id",
        required=True,
        help="Repository UUID",
    )
    parser.add_argument(
        "--commit-sha",
        help="40-character commit SHA to delete vectors for",
    )
    parser.add_argument(
        "--all-commits",
        action="store_true",
        help="Delete ALL vectors for the repository (dangerous!)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be deleted without actually deleting",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Skip confirmation prompt",
    )

    args = parser.parse_args()

    # Validate arguments
    if not args.commit_sha and not args.all_commits:
        parser.error("Either --commit-sha or --all-commits must be specified")

    if args.commit_sha and args.all_commits:
        parser.error("Cannot specify both --commit-sha and --all-commits")

    if args.commit_sha and len(args.commit_sha) != 40:
        parser.error("--commit-sha must be a 40-character hex string")

    vs = VectorStoreService()
    repo_id = args.repo_id

    if args.all_commits:
        # Delete all vectors for the repository
        _delete_all_commits(vs, repo_id, dry_run=args.dry_run, force=args.force)
    else:
        # Delete vectors for a specific commit
        _delete_single_commit(vs, repo_id, args.commit_sha, dry_run=args.dry_run, force=args.force)


def _delete_single_commit(vs: VectorStoreService, repo_id: str, commit_sha: str, *, dry_run: bool, force: bool):
    """Delete vectors for a specific commit."""
    count = vs.count_vectors(repository_id=repo_id, commit_sha=commit_sha)

    if count == 0:
        print(f"No vectors found for repository={repo_id}, commit={commit_sha}")
        return

    print(f"Found {count} vectors for repository={repo_id}, commit={commit_sha[:8]}...")

    if dry_run:
        print("[DRY RUN] Would delete these vectors")
        return

    if not force:
        confirm = input(f"Delete {count} vectors? [y/N] ").strip().lower()
        if confirm != "y":
            print("Aborted")
            return

    vs.delete_vectors(repository_id=repo_id, commit_sha=commit_sha)
    print(f"✅ Deleted {count} vectors")


def _delete_all_commits(vs: VectorStoreService, repo_id: str, *, dry_run: bool, force: bool):
    """Delete ALL vectors for a repository (all commits)."""
    from qdrant_client.models import FieldCondition, Filter, FilterSelector, MatchValue

    # Count total vectors for this repo (no commit filter)
    q_filter = Filter(
        must=[FieldCondition(key="repository_id", match=MatchValue(value=repo_id))]
    )
    result = vs.qdrant.count(
        collection_name=vs.collection_name,
        count_filter=q_filter,
    )
    count = int(result.count or 0)

    if count == 0:
        print(f"No vectors found for repository={repo_id}")
        return

    print(f"⚠️  WARNING: Found {count} vectors for repository={repo_id} across ALL commits")

    if dry_run:
        print("[DRY RUN] Would delete these vectors")
        return

    if not force:
        print("This is a DESTRUCTIVE operation that cannot be undone!")
        confirm = input(f"Type 'DELETE ALL' to confirm: ").strip()
        if confirm != "DELETE ALL":
            print("Aborted")
            return

    # Delete using repo-only filter
    vs.qdrant.delete(
        collection_name=vs.collection_name,
        points_selector=FilterSelector(filter=q_filter),
    )
    print(f"✅ Deleted {count} vectors for repository={repo_id}")


if __name__ == "__main__":
    main()