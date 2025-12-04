"""Embedding generation tasks.

This module handles code embedding generation for semantic search.
State is managed through AnalysisStateService with PostgreSQL as the single source of truth.

**Feature: progress-tracking-refactor**
**Validates: Requirements 2.1, 2.2, 2.3, 2.4, 3.1, 3.2, 3.3**
"""

import asyncio
import logging
from uuid import UUID

from qdrant_client import QdrantClient
from qdrant_client.models import FieldCondition, Filter, FilterSelector, MatchValue, PointStruct
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.celery import celery_app
from app.core.config import settings
from app.core.redis import publish_embedding_progress
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
    """Get Qdrant client with configured timeout."""
    return QdrantClient(
        host=settings.qdrant_host,
        port=settings.qdrant_port,
        timeout=settings.qdrant_timeout,
    )


def _get_db_session() -> Session:
    """Create a new database session for worker tasks.
    
    Returns:
        SQLAlchemy Session instance
    """
    engine = create_engine(str(settings.database_url))
    return Session(engine)


def _update_embeddings_state(
    analysis_id: str,
    status: str | None = None,
    progress: int | None = None,
    stage: str | None = None,
    message: str | None = None,
    error: str | None = None,
    vectors_count: int | None = None,
) -> None:
    """Update embeddings state in PostgreSQL via AnalysisStateService.
    
    This is the primary state update mechanism. Redis pub/sub is used for
    real-time updates but PostgreSQL is the single source of truth.
    
    Args:
        analysis_id: UUID of the analysis (as string)
        status: New embeddings_status (if changing status)
        progress: Progress percentage (0-100)
        stage: Current stage name
        message: Human-readable progress message
        error: Error message (for failed status)
        vectors_count: Number of vectors stored
        
    **Feature: progress-tracking-refactor**
    **Validates: Requirements 2.1, 2.2, 2.3, 2.4**
    """
    from app.services.analysis_state import AnalysisStateService
    
    try:
        with _get_db_session() as session:
            state_service = AnalysisStateService(session, publish_events=True)
            
            if status == "running":
                # Use start_embeddings for pending -> running transition
                state_service.start_embeddings(UUID(analysis_id))
            elif status == "completed":
                # Use complete_embeddings for running -> completed transition
                state_service.complete_embeddings(UUID(analysis_id), vectors_count or 0)
            elif status == "failed":
                # Use fail_embeddings for -> failed transition
                state_service.fail_embeddings(UUID(analysis_id), error or "Unknown error")
            elif progress is not None and stage is not None:
                # Progress update without status change
                state_service.update_embeddings_progress(
                    UUID(analysis_id),
                    progress=progress,
                    stage=stage,
                    message=message,
                )
            
    except Exception as e:
        logger.warning(f"Failed to update embeddings state in PostgreSQL: {e}")
        # Don't raise - we still want to continue processing


def _compute_and_store_semantic_cache(
    repository_id: str,
    analysis_id: str,
) -> dict | None:
    """Compute semantic analysis and store in Analysis.semantic_cache.
    
    This function is DEPRECATED. Use compute_semantic_cache task instead.
    Kept for backward compatibility during migration.
    
    Args:
        repository_id: UUID of the repository
        analysis_id: UUID of the analysis to update
    
    Returns:
        The computed semantic cache dict, or None if failed
    """
    from app.models.analysis import Analysis
    from app.services.cluster_analyzer import get_cluster_analyzer

    try:
        # Run cluster analysis
        analyzer = get_cluster_analyzer()
        health = run_async(analyzer.analyze(repository_id))

        # Convert to cacheable dict
        semantic_cache = health.to_cacheable_dict()

        # Store in database
        with _get_db_session() as session:
            analysis = session.get(Analysis, UUID(analysis_id))
            if analysis:
                analysis.semantic_cache = semantic_cache
                session.commit()
                logger.info(f"Stored semantic cache for analysis {analysis_id}")
                return semantic_cache
            else:
                logger.warning(f"Analysis {analysis_id} not found for semantic cache update")
                return None

    except Exception as e:
        logger.error(f"Failed to compute/store semantic cache: {e}")
        return None


@celery_app.task(bind=True, name="app.workers.embeddings.generate_embeddings")
def generate_embeddings(
    self,
    repository_id: str,
    commit_sha: str | None = None,
    files: list[dict] | None = None,
    analysis_id: str | None = None,
) -> dict:
    """
    Generate code embeddings for a repository.
    
    State is managed through AnalysisStateService with PostgreSQL as the single
    source of truth. Redis pub/sub is used for real-time updates but is not
    critical path.
    
    Args:
        repository_id: UUID of the repository
        commit_sha: Optional specific commit
        files: List of {path: str, content: str} dicts to process
        analysis_id: Optional analysis ID to update with semantic cache
    
    Returns:
        dict with embedding generation results
        
    **Feature: progress-tracking-refactor**
    **Validates: Requirements 2.1, 2.2, 2.3, 2.4**
    """
    logger.info(f"Generating embeddings for repository {repository_id}")

    def publish_progress(stage: str, progress: int, message: str | None = None,
                         status: str = "running", chunks: int = 0, vectors: int = 0):
        """Helper to publish embedding progress.
        
        Updates state in PostgreSQL (primary) and Redis (for real-time updates).
        """
        # Update PostgreSQL state via AnalysisStateService (primary source of truth)
        if analysis_id:
            if status == "running" and stage == "initializing" and progress <= 5:
                # Transition from pending -> running
                _update_embeddings_state(
                    analysis_id=analysis_id,
                    status="running",
                )
            elif status == "completed":
                # Transition from running -> completed
                _update_embeddings_state(
                    analysis_id=analysis_id,
                    status="completed",
                    vectors_count=vectors,
                )
            elif status == "error" or status == "failed":
                # Transition to failed
                _update_embeddings_state(
                    analysis_id=analysis_id,
                    status="failed",
                    error=message,
                )
            else:
                # Progress update without status change
                _update_embeddings_state(
                    analysis_id=analysis_id,
                    progress=progress,
                    stage=stage,
                    message=message,
                )
        
        # Also publish to Redis for backward compatibility and real-time updates
        publish_embedding_progress(
            repository_id=repository_id,
            stage=stage,
            progress=progress,
            message=message,
            status=status,
            chunks_processed=chunks,
            vectors_stored=vectors,
            analysis_id=analysis_id,
        )
        self.update_state(state="PROGRESS", meta={"stage": stage, "progress": progress})

    try:
        publish_progress("initializing", 5, "Starting embedding generation...")

        chunker = get_code_chunker()
        # Lazy import to avoid fork-safety issues with LiteLLM
        from app.services.llm_gateway import get_llm_gateway
        llm = get_llm_gateway()
        qdrant = get_qdrant_client()

        # If no files provided, this is a placeholder
        if not files:
            logger.warning("No files provided for embedding generation")
            publish_progress("skipped", 100, "No files to process", status="completed")
            return {
                "repository_id": repository_id,
                "status": "skipped",
                "message": "No files provided",
            }

        # Step 1: Chunk all files
        publish_progress("chunking", 10, f"Chunking {len(files)} files...")

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
        publish_progress("chunking", 20, f"Created {len(all_chunks)} chunks", chunks=len(all_chunks))

        if not all_chunks:
            publish_progress("completed", 100, "No chunks to embed", status="completed")
            return {
                "repository_id": repository_id,
                "status": "completed",
                "chunks_processed": 0,
                "vectors_stored": 0,
            }

        # Step 2: Generate embeddings in parallel batches for speed
        publish_progress("embedding", 25, f"Generating embeddings for {len(all_chunks)} chunks...")

        # Increased batch size (was 20) and parallel processing
        batch_size = 50  # Larger batches = fewer API calls
        concurrent_batches = 4  # Process 4 batches in parallel
        points: list[PointStruct] = []
        total_batches = (len(all_chunks) + batch_size - 1) // batch_size

        def prepare_texts(batch: list[CodeChunk]) -> list[str]:
            """Prepare texts for embedding."""
            texts = []
            for chunk in batch:
                text = f"File: {chunk.file_path}\n"
                if chunk.name:
                    text += f"Name: {chunk.name}\n"
                if chunk.chunk_type:
                    text += f"Type: {chunk.chunk_type}\n"
                if chunk.docstring:
                    text += f"Description: {chunk.docstring}\n"
                text += f"\n{chunk.content}"
                texts.append(text)
            return texts

        async def embed_batch(batch: list[CodeChunk], batch_idx: int) -> list[tuple[CodeChunk, list[float]]]:
            """Embed a single batch asynchronously."""
            texts = prepare_texts(batch)
            try:
                embeddings = await llm.embed(texts)
                return list(zip(batch, embeddings))
            except Exception as e:
                logger.error(f"Failed to embed batch {batch_idx}: {e}")
                return []

        async def process_all_batches():
            """Process all batches with controlled concurrency."""
            all_results = []
            batches = [
                all_chunks[i:i + batch_size]
                for i in range(0, len(all_chunks), batch_size)
            ]

            # Process batches in groups of concurrent_batches
            for group_idx in range(0, len(batches), concurrent_batches):
                group = batches[group_idx:group_idx + concurrent_batches]
                tasks = [
                    embed_batch(batch, group_idx + i)
                    for i, batch in enumerate(group)
                ]

                # Run concurrent batches
                results = await asyncio.gather(*tasks, return_exceptions=True)

                for result in results:
                    if isinstance(result, Exception):
                        logger.error(f"Batch failed: {result}")
                    elif result:
                        all_results.extend(result)

                # Update progress after each group
                completed_batches = min(group_idx + len(group), len(batches))
                progress = 25 + int(55 * completed_batches / len(batches))
                publish_progress(
                    "embedding",
                    min(progress, 80),
                    f"Embedding batch {completed_batches}/{len(batches)}...",
                    chunks=len(all_chunks),
                    vectors=len(all_results)
                )

            return all_results

        # Run parallel embedding
        chunk_embedding_pairs = run_async(process_all_batches())

        # Create Qdrant points from results
        for chunk, embedding in chunk_embedding_pairs:
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
                    # Hierarchical and metrics fields
                    "level": chunk.level,
                    "qualified_name": chunk.qualified_name,
                    "cyclomatic_complexity": chunk.cyclomatic_complexity,
                    "line_count": chunk.line_count,
                    "cluster_id": None,  # Will be set by cluster analysis
                }
            ))

        logger.info(f"Generated {len(points)} embedding vectors")

        # Step 3: Store in Qdrant
        publish_progress("indexing", 85, "Storing vectors in Qdrant...", chunks=len(all_chunks), vectors=len(points))

        if points:
            try:
                # Delete old embeddings for this repo first
                qdrant.delete(
                    collection_name=COLLECTION_NAME,
                    points_selector=FilterSelector(
                        filter=Filter(
                            must=[
                                FieldCondition(
                                    key="repository_id",
                                    match=MatchValue(value=repository_id)
                                )
                            ]
                        )
                    )
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
                publish_progress("error", 0, f"Failed to store vectors: {e}", status="error")
                return {
                    "repository_id": repository_id,
                    "status": "error",
                    "error": str(e),
                    "chunks_processed": len(all_chunks),
                    "vectors_generated": len(points),
                }

        # Publish completion for embeddings
        publish_progress(
            "completed", 100,
            f"Generated {len(points)} embeddings",
            status="completed",
            chunks=len(all_chunks),
            vectors=len(points)
        )

        # Step 4: Queue semantic cache computation as separate task
        # This is triggered automatically when embeddings complete (Requirements 2.5, 3.1)
        semantic_cache_queued = False
        if analysis_id and len(points) >= 5:
            try:
                # Queue the semantic cache computation task
                compute_semantic_cache.delay(
                    repository_id=repository_id,
                    analysis_id=analysis_id,
                )
                semantic_cache_queued = True
                logger.info(f"Queued semantic cache computation for analysis {analysis_id}")
            except Exception as e:
                logger.warning(f"Failed to queue semantic cache computation: {e}")
                # Don't fail the whole task, just log the warning

        results = {
            "repository_id": repository_id,
            "commit_sha": commit_sha,
            "chunks_processed": len(all_chunks),
            "vectors_stored": len(points),
            "status": "completed",
            "semantic_cache_queued": semantic_cache_queued,
        }

        logger.info(f"Embeddings generated for repository {repository_id}: {results}")
        return results

    except Exception as e:
        logger.error(f"Embedding generation failed for repository {repository_id}: {e}")
        
        # Update PostgreSQL state via AnalysisStateService (primary source of truth)
        if analysis_id:
            _update_embeddings_state(
                analysis_id=analysis_id,
                status="failed",
                error=str(e),
            )
        
        # Also publish to Redis for backward compatibility
        publish_embedding_progress(
            repository_id=repository_id,
            stage="error",
            progress=0,
            message=str(e),
            status="error",
            analysis_id=analysis_id,
        )
        self.update_state(
            state="FAILURE",
            meta={"error": str(e)}
        )
        raise


@celery_app.task(bind=True, name="app.workers.embeddings.compute_semantic_cache")
def compute_semantic_cache(
    self,
    repository_id: str,
    analysis_id: str,
) -> dict:
    """
    Compute semantic cache (cluster analysis) for an analysis.
    
    This task is automatically queued when embeddings generation completes.
    State is managed through AnalysisStateService with PostgreSQL as the
    single source of truth.
    
    Args:
        repository_id: UUID of the repository
        analysis_id: UUID of the analysis to update
    
    Returns:
        dict with semantic cache computation results
        
    **Feature: progress-tracking-refactor**
    **Validates: Requirements 3.1, 3.2, 3.3**
    """
    from app.models.analysis import Analysis
    from app.services.analysis_state import AnalysisStateService
    from app.services.cluster_analyzer import get_cluster_analyzer

    logger.info(f"Computing semantic cache for analysis {analysis_id}")

    try:
        # Transition semantic_cache_status: pending -> computing (Requirements 3.1)
        with _get_db_session() as session:
            state_service = AnalysisStateService(session, publish_events=True)
            state_service.start_semantic_cache(UUID(analysis_id))
        
        # Run cluster analysis
        analyzer = get_cluster_analyzer()
        health = run_async(analyzer.analyze(repository_id))

        # Convert to cacheable dict
        semantic_cache = health.to_cacheable_dict()

        # Transition semantic_cache_status: computing -> completed (Requirements 3.2)
        with _get_db_session() as session:
            state_service = AnalysisStateService(session, publish_events=True)
            state_service.complete_semantic_cache(UUID(analysis_id), semantic_cache)

        logger.info(f"Semantic cache computed for analysis {analysis_id}")

        return {
            "repository_id": repository_id,
            "analysis_id": analysis_id,
            "status": "completed",
            "clusters_count": len(semantic_cache.get("clusters", [])),
        }

    except Exception as e:
        logger.error(f"Failed to compute semantic cache for analysis {analysis_id}: {e}")
        
        # Transition semantic_cache_status: -> failed (Requirements 3.3)
        try:
            with _get_db_session() as session:
                state_service = AnalysisStateService(session, publish_events=True)
                state_service.fail_semantic_cache(UUID(analysis_id), str(e))
        except Exception as state_error:
            logger.warning(f"Failed to update semantic cache state to failed: {state_error}")
        
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
                points_selector=FilterSelector(
                    filter=Filter(
                        must=[
                            FieldCondition(key="repository_id", match=MatchValue(value=repository_id)),
                            FieldCondition(key="file_path", match=MatchValue(value=file_path)),
                        ]
                    )
                )
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
            count_filter=Filter(
                must=[
                    FieldCondition(key="repository_id", match=MatchValue(value=repository_id))
                ]
            )
        )
        vectors_count = count_result.count

        # Delete all vectors for this repository
        qdrant.delete(
            collection_name=COLLECTION_NAME,
            points_selector=FilterSelector(
                filter=Filter(
                    must=[
                        FieldCondition(key="repository_id", match=MatchValue(value=repository_id))
                    ]
                )
            )
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
