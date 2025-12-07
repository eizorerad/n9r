"""Recreate Qdrant collection with correct vector dimensions.

Use this when switching embedding models with different dimensions.
WARNING: This will delete all existing embeddings!
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PayloadSchemaType, VectorParams

from app.core.config import settings


def recreate_collection(vector_size: int = 1536):
    """Recreate Qdrant collection with specified vector size.

    Args:
        vector_size: Embedding dimension (1536 for text-embedding-3-small,
                     3072 for text-embedding-3-large)
    """
    client = QdrantClient(
        host=settings.qdrant_host,
        port=settings.qdrant_port,
        timeout=settings.qdrant_timeout,
    )

    collection_name = settings.qdrant_collection_name

    # Check if collection exists
    collections = client.get_collections().collections
    collection_names = [c.name for c in collections]

    if collection_name in collection_names:
        print(f"⚠️  Deleting existing collection '{collection_name}'...")
        client.delete_collection(collection_name)
        print("✅ Collection deleted")

    # Create collection with new vector size
    print(f"📦 Creating collection '{collection_name}' with vector size {vector_size}...")
    client.create_collection(
        collection_name=collection_name,
        vectors_config=VectorParams(
            size=vector_size,
            distance=Distance.COSINE,
        ),
    )

    # Create payload indexes
    for field in ["repo_id", "file_path", "language"]:
        client.create_payload_index(
            collection_name=collection_name,
            field_name=field,
            field_schema=PayloadSchemaType.KEYWORD,
        )

    print(f"✅ Collection '{collection_name}' created successfully")
    print(f"   Vector size: {vector_size}")
    print("   Distance metric: COSINE")
    print("   Payload indexes: repo_id, file_path, language")


if __name__ == "__main__":
    # Default to 1536 for text-embedding-3-small
    # Use 3072 for text-embedding-3-large
    size = int(sys.argv[1]) if len(sys.argv) > 1 else 1536
    recreate_collection(size)
