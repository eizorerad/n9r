"""Initialize Qdrant collection for code embeddings."""

import asyncio

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PayloadSchemaType, VectorParams

from app.core.config import settings


async def init_qdrant():
    """Create the code_embeddings collection in Qdrant."""
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
        print(f"Collection '{collection_name}' already exists.")
        return

    # Create collection with proper configuration
    # NOTE: vector size must match the embedding model in runtime.
    # In this repo, the default is commonly 3072 (text-embedding-3-large).
    client.create_collection(
        collection_name=collection_name,
        vectors_config=VectorParams(
            size=3072,  # OpenAI/Azure text-embedding-3-large dimension
            distance=Distance.COSINE,
        ),
    )

    # Create payload indexes for efficient filtering
    for field in [
        "repository_id",  # runtime payload key
        "commit_sha",     # commit-aware filtering
        "file_path",
        "language",
    ]:
        client.create_payload_index(
            collection_name=collection_name,
            field_name=field,
            field_schema=PayloadSchemaType.KEYWORD,
        )

    print(f"Collection '{collection_name}' created successfully.")
    print("Payload indexes created for: repository_id, commit_sha, file_path, language")


if __name__ == "__main__":
    asyncio.run(init_qdrant())
