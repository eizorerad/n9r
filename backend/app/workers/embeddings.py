"""Embedding generation tasks."""

import asyncio
import logging
from uuid import UUID

from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct

from app.core.celery import celery_app
from app.core.config import settings
from app.services.code_chunker import CodeChunk, get_code_chunker

# Note: LLMGateway is imported lazily inside functions to avoid fork-safety issues
# with LiteLLM/aiohttp when used with Celery prefork pool on macOS.
# from app.services.llm_gateway import get_llm_gateway

logger = logging.getLogger(__name__)


def run_async(coro):
    """Run async function in sync context."""
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)

# Qdrant collection name
COLLECTION_NAME = "code_embeddings"


def get_qdrant_client() -> QdrantClient:
    """Get Qdrant client."""
    return QdrantClient(
        host=settings.qdrant_host,
        port=settings.qdrant_port,
    )


@celery_app.task(bind=True, name="app.workers.embeddings.generate_embeddings")
def generate_embeddings(
    self,
    repository_id: str,
    commit_sha: str | None = None,
    files: list[dict] | None = None,
) -> dict:
    """
    Generate code embeddings for a repository.
    
    Args:
        repository_id: UUID of the repository
        commit_sha: Optional specific commit
        files: List of {path: str, content: str} dicts to process
    
    Returns:
        dict with embedding generation results
    """
    logger.info(f"Generating embeddings for repository {repository_id}")
    
    try:
        self.update_state(
            state="PROGRESS",
            meta={"stage": "initializing", "progress": 0}
        )
        
        chunker = get_code_chunker()
        # Lazy import to avoid fork-safety issues with LiteLLM
        from app.services.llm_gateway import get_llm_gateway
        llm = get_llm_gateway()
        qdrant = get_qdrant_client()
        
        # If no files provided, this is a placeholder
        if not files:
            logger.warning("No files provided for embedding generation")
            return {
                "repository_id": repository_id,
                "status": "skipped",
                "message": "No files provided",
            }
        
        # Step 1: Chunk all files
        self.update_state(
            state="PROGRESS",
            meta={"stage": "chunking", "progress": 10}
        )
        
        all_chunks: list[CodeChunk] = []
        for file_info in files:
            file_path = file_info.get("path", "")
            content = file_info.get("content", "")
            
            if not content or len(content) < 10:
                continue
            
            # Skip binary/non-code files
            if any(file_path.endswith(ext) for ext in [
                ".png", ".jpg", ".gif", ".ico", ".svg",
                ".woff", ".woff2", ".ttf", ".eot",
                ".pdf", ".zip", ".tar", ".gz",
                ".lock", ".sum", ".min.js", ".min.css",
            ]):
                continue
            
            try:
                chunks = chunker.chunk_file(file_path, content)
                all_chunks.extend(chunks)
            except Exception as e:
                logger.warning(f"Failed to chunk {file_path}: {e}")
        
        logger.info(f"Created {len(all_chunks)} chunks from {len(files)} files")
        
        if not all_chunks:
            return {
                "repository_id": repository_id,
                "status": "completed",
                "chunks_processed": 0,
                "vectors_stored": 0,
            }
        
        # Step 2: Generate embeddings in batches
        self.update_state(
            state="PROGRESS",
            meta={"stage": "embedding", "progress": 30}
        )
        
        batch_size = 20
        points: list[PointStruct] = []
        
        for i in range(0, len(all_chunks), batch_size):
            batch = all_chunks[i:i + batch_size]
            
            # Prepare texts for embedding
            texts = []
            for chunk in batch:
                # Create embedding text with context
                text = f"File: {chunk.file_path}\n"
                if chunk.name:
                    text += f"Name: {chunk.name}\n"
                if chunk.chunk_type:
                    text += f"Type: {chunk.chunk_type}\n"
                if chunk.docstring:
                    text += f"Description: {chunk.docstring}\n"
                text += f"\n{chunk.content}"
                texts.append(text)
            
            # Generate embeddings (async call in sync worker)
            try:
                embeddings = run_async(llm.embed(texts))
            except Exception as e:
                logger.error(f"Failed to generate embeddings: {e}")
                continue
            
            # Create Qdrant points
            for j, (chunk, embedding) in enumerate(zip(batch, embeddings)):
                point_id = f"{repository_id}_{chunk.file_path}_{chunk.line_start}".replace("/", "_").replace(".", "_")
                
                points.append(PointStruct(
                    id=hash(point_id) % (2**63),  # Convert to int64
                    vector=embedding,
                    payload={
                        "repository_id": repository_id,
                        "commit_sha": commit_sha,
                        "file_path": chunk.file_path,
                        "language": chunk.language,
                        "chunk_type": chunk.chunk_type,
                        "name": chunk.name,
                        "line_start": chunk.line_start,
                        "line_end": chunk.line_end,
                        "parent_name": chunk.parent_name,
                        "docstring": chunk.docstring,
                        "content": chunk.content[:2000],  # Limit stored content
                        "token_estimate": chunk.token_estimate,
                        # NEW: Hierarchical and metrics fields
                        "level": chunk.level,
                        "qualified_name": chunk.qualified_name,
                        "cyclomatic_complexity": chunk.cyclomatic_complexity,
                        "line_count": chunk.line_count,
                        "cluster_id": None,  # Will be set by cluster analysis
                    }
                ))
            
            # Update progress
            progress = 30 + int(50 * (i + batch_size) / len(all_chunks))
            self.update_state(
                state="PROGRESS",
                meta={"stage": "embedding", "progress": min(progress, 80)}
            )
        
        logger.info(f"Generated {len(points)} embedding vectors")
        
        # Step 3: Store in Qdrant
        self.update_state(
            state="PROGRESS",
            meta={"stage": "indexing", "progress": 85}
        )
        
        if points:
            try:
                # Delete old embeddings for this repo first
                qdrant.delete(
                    collection_name=COLLECTION_NAME,
                    points_selector={
                        "filter": {
                            "must": [
                                {"key": "repository_id", "match": {"value": repository_id}}
                            ]
                        }
                    }
                )
                
                # Upsert new points in batches
                upsert_batch_size = 100
                for i in range(0, len(points), upsert_batch_size):
                    batch = points[i:i + upsert_batch_size]
                    qdrant.upsert(
                        collection_name=COLLECTION_NAME,
                        points=batch,
                    )
                
                logger.info(f"Stored {len(points)} vectors in Qdrant")
                
            except Exception as e:
                logger.error(f"Failed to store vectors in Qdrant: {e}")
                return {
                    "repository_id": repository_id,
                    "status": "error",
                    "error": str(e),
                    "chunks_processed": len(all_chunks),
                    "vectors_generated": len(points),
                }
        
        self.update_state(
            state="PROGRESS",
            meta={"stage": "completed", "progress": 100}
        )
        
        results = {
            "repository_id": repository_id,
            "commit_sha": commit_sha,
            "chunks_processed": len(all_chunks),
            "vectors_stored": len(points),
            "status": "completed",
        }
        
        logger.info(f"Embeddings generated for repository {repository_id}: {results}")
        return results
        
    except Exception as e:
        logger.error(f"Embedding generation failed for repository {repository_id}: {e}")
        self.update_state(
            state="FAILURE",
            meta={"error": str(e)}
        )
        raise


@celery_app.task(name="app.workers.embeddings.update_embeddings")
def update_embeddings(
    repository_id: str,
    changed_files: list[dict],
) -> dict:
    """
    Update embeddings for specific changed files.
    
    Args:
        repository_id: UUID of the repository
        changed_files: List of {path: str, content: str} dicts
    
    Returns:
        dict with update results
    """
    logger.info(
        f"Updating embeddings for {len(changed_files)} files "
        f"in repository {repository_id}"
    )
    
    chunker = get_code_chunker()
    # Lazy import to avoid fork-safety issues with LiteLLM
    from app.services.llm_gateway import get_llm_gateway
    llm = get_llm_gateway()
    qdrant = get_qdrant_client()

    # Delete existing embeddings for changed files
    for file_info in changed_files:
        file_path = file_info.get("path", "")
        try:
            qdrant.delete(
                collection_name=COLLECTION_NAME,
                points_selector={
                    "filter": {
                        "must": [
                            {"key": "repository_id", "match": {"value": repository_id}},
                            {"key": "file_path", "match": {"value": file_path}},
                        ]
                    }
                }
            )
        except Exception as e:
            logger.warning(f"Failed to delete old embeddings for {file_path}: {e}")
    
    # Generate new embeddings
    return generate_embeddings(repository_id, files=changed_files)


@celery_app.task(name="app.workers.embeddings.delete_embeddings")
def delete_embeddings(repository_id: str) -> dict:
    """
    Delete all embeddings for a repository.
    
    Args:
        repository_id: UUID of the repository
    
    Returns:
        dict with deletion results
    """
    logger.info(f"Deleting embeddings for repository {repository_id}")
    
    qdrant = get_qdrant_client()
    
    try:
        # Count before deletion
        count_result = qdrant.count(
            collection_name=COLLECTION_NAME,
            count_filter={
                "must": [
                    {"key": "repository_id", "match": {"value": repository_id}}
                ]
            }
        )
        vectors_count = count_result.count
        
        # Delete all vectors for this repository
        qdrant.delete(
            collection_name=COLLECTION_NAME,
            points_selector={
                "filter": {
                    "must": [
                        {"key": "repository_id", "match": {"value": repository_id}}
                    ]
                }
            }
        )
        
        logger.info(f"Deleted {vectors_count} vectors for repository {repository_id}")
        
        return {
            "repository_id": repository_id,
            "vectors_deleted": vectors_count,
            "status": "completed",
        }
        
    except Exception as e:
        logger.error(f"Failed to delete embeddings: {e}")
        return {
            "repository_id": repository_id,
            "status": "error",
            "error": str(e),
        }


@celery_app.task(name="app.workers.embeddings.search_similar")
def search_similar(
    repository_id: str,
    query: str,
    limit: int = 10,
) -> list[dict]:
    """
    Search for similar code chunks using vector similarity.
    
    Args:
        repository_id: UUID of the repository
        query: Search query text
        limit: Maximum results to return
    
    Returns:
        List of similar chunks with scores
    """
    logger.info(f"Searching for similar code in repository {repository_id}")

    # Lazy import to avoid fork-safety issues with LiteLLM
    from app.services.llm_gateway import get_llm_gateway
    llm = get_llm_gateway()
    qdrant = get_qdrant_client()
    
    try:
        # Generate embedding for query
        query_embedding = run_async(llm.embed([query]))[0]
        
        # Search in Qdrant
        results = qdrant.search(
            collection_name=COLLECTION_NAME,
            query_vector=query_embedding,
            query_filter={
                "must": [
                    {"key": "repository_id", "match": {"value": repository_id}}
                ]
            },
            limit=limit,
        )
        
        return [
            {
                "file_path": hit.payload.get("file_path"),
                "name": hit.payload.get("name"),
                "chunk_type": hit.payload.get("chunk_type"),
                "line_start": hit.payload.get("line_start"),
                "line_end": hit.payload.get("line_end"),
                "content": hit.payload.get("content"),
                "score": hit.score,
            }
            for hit in results
        ]
        
    except Exception as e:
        logger.error(f"Search failed: {e}")
        return []
