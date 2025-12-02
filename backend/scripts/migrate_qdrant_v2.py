"""Migrate Qdrant schema for Vector-Based Code Understanding.

This migration adds new indexes for:
- level: hierarchical level (0=file, 1=class, 2=method)
- cyclomatic_complexity: code complexity metric
- cluster_id: assigned cluster after analysis
- qualified_name: full qualified name (e.g., "UserService.create_user")

Run: python -m scripts.migrate_qdrant_v2
"""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from qdrant_client import QdrantClient
from qdrant_client.models import PayloadSchemaType

from app.core.config import settings


def migrate_qdrant_v2():
    """Add new indexes for semantic architecture analysis."""
    client = QdrantClient(
        host=settings.qdrant_host,
        port=settings.qdrant_port,
    )
    
    collection_name = settings.qdrant_collection_name
    
    # Check if collection exists
    collections = client.get_collections().collections
    collection_names = [c.name for c in collections]
    
    if collection_name not in collection_names:
        print(f"Collection '{collection_name}' does not exist. Run init_qdrant.py first.")
        return False
    
    print(f"Migrating collection '{collection_name}'...")
    
    # Get existing indexes
    collection_info = client.get_collection(collection_name)
    existing_indexes = set(collection_info.payload_schema.keys()) if collection_info.payload_schema else set()
    print(f"Existing indexes: {existing_indexes}")
    
    # New indexes to add
    new_indexes = {
        "level": PayloadSchemaType.INTEGER,
        "cyclomatic_complexity": PayloadSchemaType.INTEGER,
        "cluster_id": PayloadSchemaType.INTEGER,
        "qualified_name": PayloadSchemaType.KEYWORD,
        "line_count": PayloadSchemaType.INTEGER,
    }
    
    added = []
    skipped = []
    
    for field_name, field_schema in new_indexes.items():
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
            print(f"  ❌ Failed to create index {field_name}: {e}")
    
    if skipped:
        print(f"\nSkipped (already exist): {', '.join(skipped)}")
    
    if added:
        print(f"\nSuccessfully added indexes: {', '.join(added)}")
    else:
        print("\nNo new indexes added.")
    
    return True


if __name__ == "__main__":
    success = migrate_qdrant_v2()
    sys.exit(0 if success else 1)
