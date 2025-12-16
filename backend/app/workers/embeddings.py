"""Embedding generation tasks.

This module handles code embedding generation for semantic search.
State is managed through AnalysisStateService with PostgreSQL as the single source of truth.

**Feature: progress-tracking-refactor, commit-aware-rag**
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
from app.services.vector_store import stable_int64_hash

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
    commit_sha: str,
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
        commit_sha: Commit SHA (required, must be concrete 40-hex)
        files: List of {path: str, content: str} dicts to process
        analysis_id: Optional analysis ID to update with semantic cache

    Returns:
        dict with embedding generation results

    **Feature: progress-tracking-refactor, commit-aware-rag**
    **Validates: Requirements 2.1, 2.2, 2.3, 2.4**
    """
    if not commit_sha:
        raise ValueError("commit_sha is required for generate_embeddings")
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
        (len(all_chunks) + batch_size - 1) // batch_size

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
                return list(zip(batch, embeddings, strict=False))
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

        # Create Qdrant points from results with deterministic commit-aware IDs
        for chunk, embedding in chunk_embedding_pairs:
            # Deterministic ID includes commit_sha for commit isolation
            point_key = f"{repository_id}:{commit_sha}:{chunk.file_path}:{chunk.line_start}"
            point_id = stable_int64_hash(point_key)

            points.append(PointStruct(
                id=point_id,
                vector=embedding,
                payload={
                    "schema_version": 1,  # Payload schema version for future migrations
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
                # Delete old embeddings for this (repo, commit) only - commit-aware isolation
                qdrant.delete(
                    collection_name=COLLECTION_NAME,
                    points_selector=FilterSelector(
                        filter=Filter(
                            must=[
                                FieldCondition(
                                    key="repository_id",
                                    match=MatchValue(value=repository_id)
                                ),
                                FieldCondition(
                                    key="commit_sha",
                                    match=MatchValue(value=commit_sha)
                                ),
                            ]
                        )
                    )
                )

                # Telemetry: log delete operation
                logger.info(
                    "embeddings_delete",
                    extra={
                        "telemetry": True,
                        "operation": "embeddings_delete_before_upsert",
                        "repository_id": repository_id,
                        "commit_sha": commit_sha[:8] if commit_sha else None,
                    },
                )

                # Upsert new points in batches
                upsert_batch_size = 100
                for i in range(0, len(points), upsert_batch_size):
                    batch = points[i:i + upsert_batch_size]
                    qdrant.upsert(
                        collection_name=COLLECTION_NAME,
                        points=batch,
                    )

                # Telemetry: log upsert operation
                logger.info(
                    "embeddings_upsert",
                    extra={
                        "telemetry": True,
                        "operation": "embeddings_upsert",
                        "repository_id": repository_id,
                        "commit_sha": commit_sha[:8] if commit_sha else None,
                        "vectors_count": len(points),
                        "chunks_count": len(all_chunks),
                    },
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

    Also generates Semantic AI Insights using LiteLLM directly (separate from AI Scan).

    Note: In the parallel analysis pipeline, AI Scan is dispatched directly
    from the API endpoint alongside Static Analysis and Embeddings. This
    task no longer queues AI scan on completion.

    Args:
        repository_id: UUID of the repository
        analysis_id: UUID of the analysis to update

    Returns:
        dict with semantic cache computation results

    **Feature: parallel-analysis-pipeline, cluster-map-refactoring**
    **Validates: Requirements 3.1, 3.2, 3.3, 5.1, 5.2, 5.3, 5.4, 6.1, 6.2, 6.3**
    """
    from app.services.analysis_state import AnalysisStateService
    from app.services.cluster_analyzer import get_cluster_analyzer

    logger.info(f"Computing semantic cache for analysis {analysis_id}")

    try:
        # Transition semantic_cache_status: pending -> computing (Requirements 3.1)
        with _get_db_session() as session:
            state_service = AnalysisStateService(session, publish_events=True)
            state_service.start_semantic_cache(UUID(analysis_id))

        # Get commit_sha from the Analysis record for commit-aware filtering
        commit_sha = None
        with _get_db_session() as session:
            from sqlalchemy import select

            from app.models.analysis import Analysis
            result = session.execute(
                select(Analysis.commit_sha).where(Analysis.id == UUID(analysis_id))
            )
            commit_sha = result.scalar_one_or_none()

        logger.info(f"Running cluster analysis for repo {repository_id}, commit={commit_sha or 'ALL'}")

        # Run cluster analysis (commit-aware when commit_sha available)
        analyzer = get_cluster_analyzer()
        health = run_async(analyzer.analyze(repository_id, commit_sha=commit_sha))

        # Convert to cacheable dict
        semantic_cache = health.to_cacheable_dict()

        # Transition semantic_cache_status: computing -> generating_insights
        # This lets the frontend know we're now calling the LLM
        with _get_db_session() as session:
            state_service = AnalysisStateService(session, publish_events=True)
            state_service.start_generating_insights(UUID(analysis_id))

        # Generate Semantic AI Insights BEFORE marking semantic cache as completed
        # This ensures insights are available when frontend sees completed status
        # (Requirements 5.1, 5.2, 5.3, 5.4)
        # This is SEPARATE from AI Scan - uses LiteLLM directly
        insights_result = _generate_semantic_ai_insights(
            repository_id=repository_id,
            analysis_id=analysis_id,
        )
        # Handle both old (int) and new (tuple) return format
        if isinstance(insights_result, tuple):
            insights_count, insights_failed = insights_result
        else:
            insights_count = insights_result
            insights_failed = insights_count == 0  # Assume failure if 0 insights

        # Mark insights_generation_failed in cache if insights failed
        if insights_failed:
            semantic_cache["insights_generation_failed"] = True

        # Transition semantic_cache_status: generating_insights -> completed (Requirements 3.2)
        # IMPORTANT: This must happen AFTER insights are generated to avoid race condition
        # where frontend fetches insights before they're saved to database
        with _get_db_session() as session:
            state_service = AnalysisStateService(session, publish_events=True)
            state_service.complete_semantic_cache(UUID(analysis_id), semantic_cache)

        logger.info(f"Semantic cache computed for analysis {analysis_id}")

        return {
            "repository_id": repository_id,
            "analysis_id": analysis_id,
            "status": "completed",
            "clusters_count": len(semantic_cache.get("clusters", [])),
            "insights_count": insights_count,
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


def _generate_semantic_ai_insights(
    repository_id: str,
    analysis_id: str,
) -> int:
    """Generate Semantic AI Insights using LiteLLM directly.

    This function:
    1. Gets the commit_sha from the analysis
    2. Clones the repository at that commit
    3. Runs analyze_for_llm() to get LLM-ready architecture data
    4. Calls SemanticAIInsightsService to generate recommendations
    5. Stores insights in the semantic_ai_insights table

    IMPORTANT: This is SEPARATE from AI Scan (BroadScanAgent).
    Uses LiteLLM directly via SemanticAIInsightsService.

    Args:
        repository_id: UUID of the repository
        analysis_id: UUID of the analysis

    Returns:
        Number of insights generated

    **Feature: cluster-map-refactoring**
    **Validates: Requirements 5.1, 5.2, 5.3, 5.4**
    """
    from pathlib import Path

    from sqlalchemy import select

    from app.core.database import get_sync_session
    from app.core.encryption import decrypt_token
    from app.models.analysis import Analysis
    from app.models.repository import Repository
    from app.models.semantic_ai_insight import SemanticAIInsight
    from app.models.user import User
    from app.services.cluster_analyzer import get_cluster_analyzer
    from app.services.repo_analyzer import RepoAnalyzer
    from app.services.semantic_ai_insights import get_semantic_ai_insights_service

    logger.info(f"Generating Semantic AI Insights for analysis {analysis_id}")

    try:
        # Step 1: Get analysis and repository info
        with get_sync_session() as db:
            result = db.execute(
                select(Analysis).where(Analysis.id == analysis_id)
            )
            analysis = result.scalar_one_or_none()

            if not analysis:
                logger.warning(f"Analysis {analysis_id} not found for AI insights")
                return 0

            repo_result = db.execute(
                select(Repository).where(Repository.id == analysis.repository_id)
            )
            repository = repo_result.scalar_one_or_none()

            if not repository:
                logger.warning(f"Repository for analysis {analysis_id} not found")
                return 0

            # Get owner's access token for private repos
            access_token = None
            if repository.owner_id:
                user_result = db.execute(
                    select(User).where(User.id == repository.owner_id)
                )
                user = user_result.scalar_one_or_none()
                if user and user.access_token_encrypted:
                    try:
                        access_token = decrypt_token(user.access_token_encrypted)
                    except Exception as e:
                        logger.warning(f"Could not decrypt access token: {e}")

            commit_sha = analysis.commit_sha
            repo_url = f"https://github.com/{repository.full_name}"

        # Step 2: Clone repository and run analyze_for_llm
        with RepoAnalyzer(repo_url, access_token, commit_sha=commit_sha) as analyzer:
            repo_path = analyzer.clone()
            logger.info(f"Cloned repository to {repo_path} for AI insights")

            # Run LLM-ready analysis
            cluster_analyzer = get_cluster_analyzer()
            architecture_data = cluster_analyzer.analyze_for_llm(
                repo_id=repository_id,
                repo_path=Path(repo_path),
            )

        # Step 2.5: Persist dead code and hot spot findings to PostgreSQL
        # Requirements: 7.1, 7.2
        from app.services.architecture_findings_service import get_architecture_findings_service
        findings_service = get_architecture_findings_service()
        with get_sync_session() as db:
            findings_result = findings_service.persist_findings(
                db=db,
                repository_id=UUID(repository_id),
                analysis_id=UUID(analysis_id),
                architecture_data=architecture_data,
            )
            logger.info(
                f"Persisted {findings_result['dead_code_count']} dead code and "
                f"{findings_result['hot_spot_count']} hot spot findings"
            )

        # Step 3: Generate AI insights
        service = get_semantic_ai_insights_service()
        insights = run_async(service.generate_insights(
            architecture_data=architecture_data,
            repository_id=UUID(repository_id),
            analysis_id=UUID(analysis_id),
        ))

        if not insights:
            logger.info(f"No AI insights generated for analysis {analysis_id}")
            return 0

        # Step 4: Store insights in database
        with get_sync_session() as db:
            for insight_data in insights:
                insight = SemanticAIInsight(
                    analysis_id=insight_data["analysis_id"],
                    repository_id=insight_data["repository_id"],
                    insight_type=insight_data["insight_type"],
                    title=insight_data["title"],
                    description=insight_data["description"],
                    priority=insight_data["priority"],
                    affected_files=insight_data["affected_files"],
                    evidence=insight_data.get("evidence"),
                    suggested_action=insight_data.get("suggested_action"),
                )
                db.add(insight)
            db.commit()

        logger.info(f"Generated {len(insights)} AI insights for analysis {analysis_id}")
        return (len(insights), False)  # (count, failed)

    except Exception as e:
        # Log error but don't fail the semantic cache task
        # AI insights are optional - the main semantic cache should still succeed
        logger.error(f"Failed to generate AI insights for analysis {analysis_id}: {e}")
        return (0, True)  # (count, failed)


@celery_app.task(name="app.workers.embeddings.update_embeddings")
def update_embeddings(
    repository_id: str,
    commit_sha: str,
    changed_files: list[dict],
) -> dict:
    """
    Update embeddings for specific changed files within a commit snapshot.

    Args:
        repository_id: UUID of the repository
        commit_sha: Commit SHA (required for commit-aware isolation)
        changed_files: List of {path: str, content: str} dicts

    Returns:
        dict with update results

    **Feature: commit-aware-rag**
    """
    if not commit_sha:
        raise ValueError("commit_sha is required for update_embeddings")

    logger.info(
        f"Updating embeddings for {len(changed_files)} files "
        f"in repository {repository_id} at commit {commit_sha[:7]}"
    )

    get_code_chunker()
    # Lazy import to avoid fork-safety issues with LiteLLM
    from app.services.llm_gateway import get_llm_gateway
    get_llm_gateway()
    qdrant = get_qdrant_client()

    # Delete existing embeddings for changed files (commit-aware)
    for file_info in changed_files:
        file_path = file_info.get("path", "")
        try:
            qdrant.delete(
                collection_name=COLLECTION_NAME,
                points_selector=FilterSelector(
                    filter=Filter(
                        must=[
                            FieldCondition(key="repository_id", match=MatchValue(value=repository_id)),
                            FieldCondition(key="commit_sha", match=MatchValue(value=commit_sha)),
                            FieldCondition(key="file_path", match=MatchValue(value=file_path)),
                        ]
                    )
                )
            )
        except Exception as e:
            logger.warning(f"Failed to delete old embeddings for {file_path}: {e}")

    # Generate new embeddings with commit_sha
    return generate_embeddings(repository_id, commit_sha=commit_sha, files=changed_files)


@celery_app.task(name="app.workers.embeddings.delete_embeddings")
def delete_embeddings(
    repository_id: str,
    commit_sha: str | None = None,
) -> dict:
    """
    Delete embeddings for a repository.

    If commit_sha is provided, only vectors for that commit are deleted.
    If commit_sha is None, ALL vectors for the repo are deleted (admin operation).

    Args:
        repository_id: UUID of the repository
        commit_sha: Optional commit SHA to delete only that snapshot

    Returns:
        dict with deletion results

    **Feature: commit-aware-rag**
    """
    scope = f"commit {commit_sha[:7]}" if commit_sha else "ALL commits (admin)"
    logger.info(f"Deleting embeddings for repository {repository_id}, scope: {scope}")

    qdrant = get_qdrant_client()

    try:
        # Build filter based on scope
        filter_conditions = [
            FieldCondition(key="repository_id", match=MatchValue(value=repository_id))
        ]
        if commit_sha:
            filter_conditions.append(
                FieldCondition(key="commit_sha", match=MatchValue(value=commit_sha))
            )

        # Count before deletion
        count_result = qdrant.count(
            collection_name=COLLECTION_NAME,
            count_filter=Filter(must=filter_conditions)
        )
        vectors_count = count_result.count

        # Delete vectors
        qdrant.delete(
            collection_name=COLLECTION_NAME,
            points_selector=FilterSelector(
                filter=Filter(must=filter_conditions)
            )
        )

        # Telemetry: log delete operation
        logger.info(
            "embeddings_delete",
            extra={
                "telemetry": True,
                "operation": "embeddings_delete_task",
                "repository_id": repository_id,
                "commit_sha": commit_sha[:8] if commit_sha else None,
                "vectors_deleted": vectors_count,
                "scope": "single_commit" if commit_sha else "all_commits",
            },
        )
        logger.info(f"Deleted {vectors_count} vectors for repository {repository_id} ({scope})")

        return {
            "repository_id": repository_id,
            "commit_sha": commit_sha,
            "vectors_deleted": vectors_count,
            "status": "completed",
        }

    except Exception as e:
        logger.error(f"Failed to delete embeddings: {e}")
        return {
            "repository_id": repository_id,
            "commit_sha": commit_sha,
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


def _populate_content_cache(
    repository_id: str,
    commit_sha: str,
    repo_path,
) -> dict:
    """Populate repository content cache during analysis.

    This function caches repository file contents in MinIO for fast
    retrieval during chat. It runs after clone, before embedding generation.

    Errors are handled gracefully - cache failures don't fail the analysis.

    Args:
        repository_id: UUID of the repository (as string)
        commit_sha: Git commit SHA
        repo_path: Path to the cloned repository

    Returns:
        dict with cache population results

    **Feature: repo-content-cache**
    **Validates: Requirements 2.1, 2.4, 2.5, 3.3**
    """
    from pathlib import Path
    from uuid import UUID

    from app.core.database import async_session_maker
    from app.services.repo_content import RepoContentService

    logger.info(f"Populating content cache for {commit_sha[:7]}")

    async def _do_cache_population():
        service = RepoContentService()

        async with async_session_maker() as db:
            try:
                # 1. Get or create cache entry
                cache = await service.get_or_create_cache(
                    db,
                    UUID(repository_id),
                    commit_sha,
                )

                # If cache is already ready, we update the full_tree to ensure dotfiles are visible
                # (since we changed the filter logic), but we MUST return "skipped" to avoid
                # triggering upload_files which sets status to "uploading" (causing GitHub fallback)
                if cache.status == "ready":
                    try:
                        logger.info(f"Cache ready for {commit_sha[:7]}, updating full_tree for dotfiles...")
                        # Collect full tree (fast, local disk walk)
                        full_tree = service.collect_full_tree(repo_path)
                        # Save tree (idempotent upsert)
                        await service.save_tree(db, cache.id, [], full_tree=full_tree)
                        
                        logger.info(f"Updated full_tree for {commit_sha[:7]}")
                        return {
                            "status": "skipped",
                            "reason": "cache_already_ready",
                        }
                    except Exception as e:
                        logger.error(f"Failed to update full_tree for ready cache: {e}")
                        # If tree update fails, still return skipped to keep system stable
                        return {
                            "status": "skipped",
                            "reason": "cache_already_ready_tree_update_failed",
                        }




                # If cache is uploading (another process is working on it), skip
                if cache.status == "uploading":
                    logger.info(f"Cache already uploading for {commit_sha[:7]}")
                    return {
                        "status": "skipped",
                        "reason": "cache_uploading",
                    }

                # 2. Collect files from cloned repo (code files for MinIO)
                files = service.collect_files_from_repo(Path(repo_path))

                # 2b. Collect full tree for file explorer (all files/dirs)
                full_tree = service.collect_full_tree(Path(repo_path))

                if not files and not full_tree:
                    logger.info(f"No files to cache for {commit_sha[:7]}")
                    # Mark as ready with 0 files
                    await service.mark_cache_ready(db, cache.id)
                    await db.commit()
                    return {
                        "status": "completed",
                        "files_cached": 0,
                    }

                # 3. Upload code files to MinIO + record in PostgreSQL
                result = await service.upload_files(db, cache, files) if files else None

                if result and result.failed > 0 and result.uploaded == 0:
                    # All files failed - mark cache as failed
                    await service.mark_cache_failed(
                        db,
                        cache.id,
                        f"All {result.failed} files failed to upload",
                    )
                    await db.commit()
                    return {
                        "status": "failed",
                        "error": f"All {result.failed} files failed to upload",
                        "errors": result.errors[:5],  # First 5 errors
                    }

                # 4. Build and save tree structures
                tree = [f.path for f in files] if files else []
                await service.save_tree(db, cache.id, tree, full_tree=full_tree)

                # 5. Mark cache as ready
                await service.mark_cache_ready(db, cache.id)
                await db.commit()

                if result:
                    logger.info(
                        f"Content cache populated for {commit_sha[:7]}: "
                        f"{result.uploaded} uploaded, {result.skipped} skipped, "
                        f"{result.failed} failed, {len(full_tree)} tree entries"
                    )
                else:
                    logger.info(
                        f"Content cache populated for {commit_sha[:7]}: "
                        f"0 code files, {len(full_tree)} tree entries"
                    )

                return {
                    "status": "completed",
                    "files_cached": result.uploaded + result.skipped,
                    "uploaded": result.uploaded,
                    "skipped": result.skipped,
                    "failed": result.failed,
                }

            except Exception as e:
                logger.error(f"Failed to populate content cache: {e}")
                # Try to mark cache as failed
                try:
                    await service.mark_cache_failed(db, cache.id, str(e))
                    await db.commit()
                except Exception:
                    pass
                return {
                    "status": "failed",
                    "error": str(e),
                }

    try:
        return run_async(_do_cache_population())
    except Exception as e:
        logger.error(f"Content cache population failed: {e}")
        return {
            "status": "failed",
            "error": str(e),
        }


@celery_app.task(bind=True, name="app.workers.embeddings.generate_embeddings_parallel")
def generate_embeddings_parallel(
    self,
    repository_id: str,
    analysis_id: str,
    commit_sha: str,
) -> dict:
    """
    Generate code embeddings with independent repository clone.

    This task clones the repository independently using the commit_sha from
    the Analysis record, enabling true parallel execution with Static Analysis
    and AI Scan tracks.

    Unlike generate_embeddings which receives files from Static Analysis,
    this task clones the repo itself and collects files for embedding.

    Also populates the repository content cache for fast file retrieval
    during chat (Requirements 2.1, 2.4, 2.5, 3.3).

    Args:
        repository_id: UUID of the repository
        analysis_id: UUID of the analysis
        commit_sha: Commit SHA to clone (from Analysis record)

    Returns:
        dict with embedding generation results

    **Feature: parallel-analysis-pipeline, repo-content-cache**
    **Validates: Requirements 5.1, 5.4, 6.1**
    """
    from app.services.repo_analyzer import RepoAnalyzer
    from app.workers.helpers import collect_files_for_embedding, get_repo_url

    logger.info(
        f"Starting parallel embeddings for analysis {analysis_id}, "
        f"repository {repository_id}, commit {commit_sha}"
    )

    def publish_progress(stage: str, progress: int, message: str | None = None,
                         status: str = "running", chunks: int = 0, vectors: int = 0):
        """Helper to publish embedding progress."""
        # Update PostgreSQL state via AnalysisStateService (primary source of truth)
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

        # Also publish to Redis for real-time updates
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
        publish_progress("initializing", 5, "Starting parallel embedding generation...")

        # Step 1: Get repository URL and access token
        repo_url, access_token = get_repo_url(repository_id)
        logger.info(f"Repository URL: {repo_url}")

        # Step 2: Clone repository independently using commit_sha
        publish_progress("cloning", 10, f"Cloning repository at commit {commit_sha[:7]}...")

        with RepoAnalyzer(repo_url, access_token, commit_sha=commit_sha) as analyzer:
            # Clone the repository
            repo_path = analyzer.clone()
            logger.info(f"Cloned repository to {repo_path}")

            publish_progress("cloning", 15, "Repository cloned successfully")

            # Step 2.5: Populate content cache (for fast chat file retrieval)
            # This runs after clone, before embedding generation
            # Errors are handled gracefully - cache failures don't fail analysis
            # **Feature: repo-content-cache**
            # **Validates: Requirements 2.1, 2.4, 2.5, 3.3**
            try:
                cache_result = _populate_content_cache(
                    repository_id=repository_id,
                    commit_sha=commit_sha,
                    repo_path=repo_path,
                )
                logger.info(f"Content cache result: {cache_result}")
            except Exception as e:
                # Don't fail analysis if cache fails
                logger.warning(f"Content cache population failed (non-fatal): {e}")

            # Step 3: Collect files for embedding
            publish_progress("collecting", 20, "Collecting code files...")
            files = collect_files_for_embedding(repo_path)
            logger.info(f"Collected {len(files)} files for embedding")

        # Step 4: If no files, complete early
        if not files:
            logger.warning("No files found for embedding generation")
            publish_progress("completed", 100, "No files to process", status="completed", vectors=0)
            return {
                "repository_id": repository_id,
                "analysis_id": analysis_id,
                "commit_sha": commit_sha,
                "status": "completed",
                "message": "No files to process",
                "chunks_processed": 0,
                "vectors_stored": 0,
            }

        # Step 5: Delegate to existing generate_embeddings logic
        # We call the task function directly (not .delay()) to reuse the embedding logic
        # but we need to handle the state transitions ourselves

        chunker = get_code_chunker()
        from app.services.llm_gateway import get_llm_gateway
        llm = get_llm_gateway()
        qdrant = get_qdrant_client()

        # Chunk all files
        publish_progress("chunking", 25, f"Chunking {len(files)} files...")

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
        publish_progress("chunking", 30, f"Created {len(all_chunks)} chunks", chunks=len(all_chunks))

        if not all_chunks:
            publish_progress("completed", 100, "No chunks to embed", status="completed", vectors=0)
            return {
                "repository_id": repository_id,
                "analysis_id": analysis_id,
                "commit_sha": commit_sha,
                "status": "completed",
                "chunks_processed": 0,
                "vectors_stored": 0,
            }

        # Generate embeddings in parallel batches
        publish_progress("embedding", 35, f"Generating embeddings for {len(all_chunks)} chunks...")

        batch_size = 50
        concurrent_batches = 4
        points: list[PointStruct] = []
        (len(all_chunks) + batch_size - 1) // batch_size

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
                return list(zip(batch, embeddings, strict=False))
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

            for group_idx in range(0, len(batches), concurrent_batches):
                group = batches[group_idx:group_idx + concurrent_batches]
                tasks = [
                    embed_batch(batch, group_idx + i)
                    for i, batch in enumerate(group)
                ]

                results = await asyncio.gather(*tasks, return_exceptions=True)

                for result in results:
                    if isinstance(result, Exception):
                        logger.error(f"Batch failed: {result}")
                    elif result:
                        all_results.extend(result)

                completed_batches = min(group_idx + len(group), len(batches))
                progress = 35 + int(45 * completed_batches / len(batches))
                publish_progress(
                    "embedding",
                    min(progress, 80),
                    f"Embedding batch {completed_batches}/{len(batches)}...",
                    chunks=len(all_chunks),
                    vectors=len(all_results)
                )

            return all_results

        chunk_embedding_pairs = run_async(process_all_batches())

        # Create Qdrant points from results with deterministic commit-aware IDs
        for chunk, embedding in chunk_embedding_pairs:
            # Deterministic ID includes commit_sha for commit isolation
            point_key = f"{repository_id}:{commit_sha}:{chunk.file_path}:{chunk.line_start}"
            point_id = stable_int64_hash(point_key)

            points.append(PointStruct(
                id=point_id,
                vector=embedding,
                payload={
                    "schema_version": 1,  # Payload schema version for future migrations
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
                    "content": chunk.content[:2000],
                    "token_estimate": chunk.token_estimate,
                    "level": chunk.level,
                    "qualified_name": chunk.qualified_name,
                    "cyclomatic_complexity": chunk.cyclomatic_complexity,
                    "line_count": chunk.line_count,
                    "cluster_id": None,
                }
            ))

        logger.info(f"Generated {len(points)} embedding vectors")

        # Store in Qdrant
        publish_progress("indexing", 85, "Storing vectors in Qdrant...", chunks=len(all_chunks), vectors=len(points))

        if points:
            try:
                # Delete old embeddings for this (repo, commit) only - commit-aware isolation
                qdrant.delete(
                    collection_name=COLLECTION_NAME,
                    points_selector=FilterSelector(
                        filter=Filter(
                            must=[
                                FieldCondition(
                                    key="repository_id",
                                    match=MatchValue(value=repository_id)
                                ),
                                FieldCondition(
                                    key="commit_sha",
                                    match=MatchValue(value=commit_sha)
                                ),
                            ]
                        )
                    )
                )

                # Telemetry: log delete operation
                logger.info(
                    "embeddings_delete",
                    extra={
                        "telemetry": True,
                        "operation": "embeddings_delete_before_upsert",
                        "repository_id": repository_id,
                        "commit_sha": commit_sha[:8],
                        "analysis_id": analysis_id,
                    },
                )

                # Upsert new points in batches
                upsert_batch_size = 100
                for i in range(0, len(points), upsert_batch_size):
                    batch = points[i:i + upsert_batch_size]
                    qdrant.upsert(
                        collection_name=COLLECTION_NAME,
                        points=batch,
                    )

                # Telemetry: log upsert operation
                logger.info(
                    "embeddings_upsert",
                    extra={
                        "telemetry": True,
                        "operation": "embeddings_upsert",
                        "repository_id": repository_id,
                        "commit_sha": commit_sha[:8],
                        "analysis_id": analysis_id,
                        "vectors_count": len(points),
                        "chunks_count": len(all_chunks),
                    },
                )
                logger.info(f"Stored {len(points)} vectors in Qdrant")

            except Exception as e:
                logger.error(f"Failed to store vectors in Qdrant: {e}")
                publish_progress("error", 0, f"Failed to store vectors: {e}", status="error")
                return {
                    "repository_id": repository_id,
                    "analysis_id": analysis_id,
                    "commit_sha": commit_sha,
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

        # Queue semantic cache computation (Requirements 6.1)
        semantic_cache_queued = False
        if len(points) >= 5:
            try:
                compute_semantic_cache.delay(
                    repository_id=repository_id,
                    analysis_id=analysis_id,
                )
                semantic_cache_queued = True
                logger.info(f"Queued semantic cache computation for analysis {analysis_id}")
            except Exception as e:
                logger.warning(f"Failed to queue semantic cache computation: {e}")

        results = {
            "repository_id": repository_id,
            "analysis_id": analysis_id,
            "commit_sha": commit_sha,
            "chunks_processed": len(all_chunks),
            "vectors_stored": len(points),
            "status": "completed",
            "semantic_cache_queued": semantic_cache_queued,
        }

        logger.info(f"Parallel embeddings completed for analysis {analysis_id}: {results}")
        return results

    except Exception as e:
        logger.error(f"Parallel embedding generation failed for analysis {analysis_id}: {e}")

        # Update PostgreSQL state
        _update_embeddings_state(
            analysis_id=analysis_id,
            status="failed",
            error=str(e),
        )

        # Also publish to Redis
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
