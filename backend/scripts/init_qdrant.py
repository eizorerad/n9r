"""Initialize Qdrant collection for code embeddings."""

import asyncio

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PayloadSchemaType

from app.core.config import settings


async def init_qdrant():
    """Create the code_embeddings collection in Qdrant."""
    client = QdrantClient(
        host=settings.qdrant_host,
        port=settings.qdrant_port,
    )
    
    collection_name = settings.qdrant_collection_name
    
    # Check if collection exists
    collections = client.get_collections().collections
    collection_names = [c.name for c in collections]
    
    if collection_name in collection_names:
        print(f"Collection '{collection_name}' already exists.")
        return
    
    # Create collection with proper configuration
    client.create_collection(
        collection_name=collection_name,
        vectors_config=VectorParams(
            size=1536,  # OpenAI text-embedding-3-small dimension
            distance=Distance.COSINE,
        ),
    )
    
    # Create payload indexes for efficient filtering
    client.create_payload_index(
        collection_name=collection_name,
        field_name="repo_id",
        field_schema=PayloadSchemaType.KEYWORD,
    )
    
    client.create_payload_index(
        collection_name=collection_name,
        field_name="file_path",
        field_schema=PayloadSchemaType.KEYWORD,
    )
    
    client.create_payload_index(
        collection_name=collection_name,
        field_name="language",
        field_schema=PayloadSchemaType.KEYWORD,
    )
    
    print(f"Collection '{collection_name}' created successfully.")
    print("Payload indexes created for: repo_id, file_path, language")


if __name__ == "__main__":
    asyncio.run(init_qdrant())
