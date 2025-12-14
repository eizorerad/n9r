"""Non-destructive Qdrant payload-index migration for commit-aware vectors.

This script adds payload indexes required for commit-aware filtering:
- repository_id (KEYWORD)
- commit_sha (KEYWORD)
- file_path (KEYWORD)

It DOES NOT recreate the collection and does not delete points.

Run:
  python -m scripts.migrate_qdrant_commit_aware

Notes:
- Collection name is taken from settings.qdrant_collection_name.
- Existing indexes are detected via collection_info.payload_schema.
"""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from qdrant_client import QdrantClient
from qdrant_client.models import PayloadSchemaType

from app.core.config import settings


def migrate_qdrant_commit_aware() -> bool:
    client = QdrantClient(
        host=settings.qdrant_host,
        port=settings.qdrant_port,
        timeout=settings.qdrant_timeout,
    )

    collection_name = settings.qdrant_collection_name

    # Check if collection exists
    collections = client.get_collections().collections
    collection_names = [c.name for c in collections]

    if collection_name not in collection_names:
        print(f"Collection '{collection_name}' does not exist. Run init_all.py or init_qdrant.py first.")
        return False

    print(f"Migrating collection '{collection_name}' (commit-aware indexes)...")

    collection_info = client.get_collection(collection_name)
    existing_indexes = set(collection_info.payload_schema.keys()) if collection_info.payload_schema else set()
    print(f"Existing indexes: {sorted(existing_indexes)}")

    required_indexes: dict[str, PayloadSchemaType] = {
        "repository_id": PayloadSchemaType.KEYWORD,
        "commit_sha": PayloadSchemaType.KEYWORD,
        "file_path": PayloadSchemaType.KEYWORD,
    }

    added: list[str] = []
    skipped: list[str] = []
    failed: list[str] = []

    for field_name, field_schema in required_indexes.items():
        if field_name in existing_indexes:
            skipped.append(field_name)
            continue

        try:
            client.create_payload_index(
                collection_name=collection_name,
                field_name=field_name,
                field_schema=field_schema,
            )
            added.append(field_name)
            print(f"  ✅ Created index: {field_name} ({field_schema})")
        except Exception as e:
            failed.append(field_name)
            print(f"  ❌ Failed to create index {field_name}: {e}")

    if skipped:
        print(f"Skipped (already exist): {', '.join(skipped)}")
    if added:
        print(f"Added: {', '.join(added)}")
    if failed:
        print(f"Failed: {', '.join(failed)}")

    return len(failed) == 0


if __name__ == "__main__":
    ok = migrate_qdrant_commit_aware()
    raise SystemExit(0 if ok else 1)
