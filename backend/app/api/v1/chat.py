"""Chat API endpoints with RAG support."""

import logging
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from qdrant_client import QdrantClient
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import CurrentUser, DbSession
from app.core.config import settings
from app.models.chat import ChatMessage, ChatThread
from app.models.repository import Repository
from app.services.llm_gateway import get_llm_gateway

logger = logging.getLogger(__name__)
router = APIRouter()

# Qdrant collection name
COLLECTION_NAME = "code_embeddings"


def get_qdrant_client() -> QdrantClient:
    """Get Qdrant client."""
    return QdrantClient(
        host=settings.qdrant_host,
        port=settings.qdrant_port,
    )


class CreateThreadRequest(BaseModel):
    """Create chat thread request."""
    title: str | None = None
    context_file: str | None = None
    context_issue_id: UUID | None = None


class SendMessageRequest(BaseModel):
    """Send message request."""
    content: str
    stream: bool = True


@router.post("/repositories/{repository_id}/chat/threads")
async def create_thread(
    repository_id: UUID,
    payload: CreateThreadRequest,
    db: DbSession,
    user: CurrentUser,
) -> dict:
    """Create a new chat thread for a repository."""
    # Verify access
    result = await db.execute(
        select(Repository).where(
            Repository.id == repository_id,
            Repository.owner_id == user.id,
        )
    )
    repository = result.scalar_one_or_none()

    if not repository:
        raise HTTPException(status_code=404, detail="Repository not found")

    # Create thread
    thread = ChatThread(
        repository_id=repository_id,
        user_id=user.id,
        title=payload.title or "New conversation",
        context_file=payload.context_file,
        context_issue_id=payload.context_issue_id,
    )
    db.add(thread)
    await db.commit()
    await db.refresh(thread)

    return {
        "id": str(thread.id),
        "title": thread.title,
        "context_file": thread.context_file,
        "created_at": thread.created_at.isoformat(),
    }


@router.get("/repositories/{repository_id}/chat/threads")
async def list_threads(
    repository_id: UUID,
    db: DbSession,
    user: CurrentUser,
    limit: int = Query(20, ge=1, le=100),
) -> dict:
    """List chat threads for a repository."""
    result = await db.execute(
        select(ChatThread)
        .where(
            ChatThread.repository_id == repository_id,
            ChatThread.user_id == user.id,
        )
        .order_by(ChatThread.updated_at.desc())
        .limit(limit)
    )
    threads = result.scalars().all()

    return {
        "data": [
            {
                "id": str(t.id),
                "title": t.title,
                "context_file": t.context_file,
                "message_count": t.message_count,
                "created_at": t.created_at.isoformat(),
                "updated_at": t.updated_at.isoformat(),
            }
            for t in threads
        ]
    }


@router.get("/chat/threads/{thread_id}")
async def get_thread(
    thread_id: UUID,
    db: DbSession,
    user: CurrentUser,
) -> dict:
    """Get chat thread with messages."""
    result = await db.execute(
        select(ChatThread)
        .options(selectinload(ChatThread.messages))
        .where(ChatThread.id == thread_id, ChatThread.user_id == user.id)
    )
    thread = result.scalar_one_or_none()

    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")

    return {
        "id": str(thread.id),
        "title": thread.title,
        "context_file": thread.context_file,
        "messages": [
            {
                "id": str(m.id),
                "role": m.role,
                "content": m.content,
                "created_at": m.created_at.isoformat(),
            }
            for m in sorted(thread.messages, key=lambda x: x.created_at)
        ],
    }


@router.post("/chat/threads/{thread_id}/messages")
async def send_message(
    thread_id: UUID,
    payload: SendMessageRequest,
    db: DbSession,
    user: CurrentUser,
):
    """Send a message and get AI response (with optional streaming)."""
    # Get thread
    result = await db.execute(
        select(ChatThread)
        .options(
            selectinload(ChatThread.messages),
            selectinload(ChatThread.repository),
        )
        .where(ChatThread.id == thread_id, ChatThread.user_id == user.id)
    )
    thread = result.scalar_one_or_none()

    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")

    # Save user message
    user_message = ChatMessage(
        thread_id=thread_id,
        role="user",
        content=payload.content,
    )
    db.add(user_message)
    await db.commit()

    # Build context for RAG
    messages = await _build_chat_messages(thread, payload.content)

    if payload.stream:
        # Return streaming response
        return StreamingResponse(
            _stream_response(thread_id, messages, db),
            media_type="text/event-stream",
        )
    else:
        # Non-streaming response
        llm = get_llm_gateway()
        response = await llm.chat(messages)

        # Save assistant message
        assistant_message = ChatMessage(
            thread_id=thread_id,
            role="assistant",
            content=response,
        )
        db.add(assistant_message)
        thread.message_count += 2
        await db.commit()

        return {
            "message": {
                "id": str(assistant_message.id),
                "role": "assistant",
                "content": response,
            }
        }


async def _stream_response(thread_id: UUID, messages: list, db):
    """Stream LLM response."""
    llm = get_llm_gateway()
    full_response = []

    async for chunk in llm.complete_stream(
        prompt=messages[-1]["content"],
        system_prompt=messages[0]["content"] if messages[0]["role"] == "system" else None,
    ):
        full_response.append(chunk)
        yield f"data: {chunk}\n\n"

    yield "data: [DONE]\n\n"

    # Save complete response (would need separate db session in production)
    # This is simplified - in production use background task


async def _get_rag_context(
    repository_id: UUID,
    query: str,
    context_file: str | None = None,
    limit: int = 5,
) -> list[dict]:
    """Retrieve relevant code chunks from Qdrant for RAG."""
    try:
        llm = get_llm_gateway()
        qdrant = get_qdrant_client()

        # Generate embedding for query
        query_embedding = await llm.embed([query])

        # Build filter
        filter_conditions = [
            {"key": "repository_id", "match": {"value": str(repository_id)}}
        ]

        # Optionally prioritize current file context
        if context_file:
            # First search in context file
            file_results = qdrant.search(
                collection_name=COLLECTION_NAME,
                query_vector=query_embedding[0],
                query_filter={
                    "must": [
                        {"key": "repository_id", "match": {"value": str(repository_id)}},
                        {"key": "file_path", "match": {"value": context_file}},
                    ]
                },
                limit=2,
            )

            # Then search broader
            other_results = qdrant.search(
                collection_name=COLLECTION_NAME,
                query_vector=query_embedding[0],
                query_filter={
                    "must": filter_conditions,
                    "must_not": [
                        {"key": "file_path", "match": {"value": context_file}},
                    ]
                },
                limit=limit - len(file_results),
            )

            results = list(file_results) + list(other_results)
        else:
            results = qdrant.search(
                collection_name=COLLECTION_NAME,
                query_vector=query_embedding[0],
                query_filter={"must": filter_conditions},
                limit=limit,
            )

        # Format results
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
        logger.warning(f"RAG context retrieval failed: {e}")
        return []


async def _build_chat_messages(
    thread: ChatThread,
    user_message: str,
) -> list[dict]:
    """Build messages array with RAG context."""
    messages = []

    # Get RAG context
    rag_chunks = await _get_rag_context(
        repository_id=thread.repository_id,
        query=user_message,
        context_file=thread.context_file,
    )

    # Build context section
    context_section = ""
    if rag_chunks:
        context_section = "\n\n## Relevant Code Context:\n"
        for i, chunk in enumerate(rag_chunks, 1):
            context_section += f"\n### {i}. {chunk['file_path']}"
            if chunk['name']:
                context_section += f" - {chunk['chunk_type']} `{chunk['name']}`"
            if chunk['line_start']:
                context_section += f" (lines {chunk['line_start']}-{chunk['line_end']})"
            context_section += f"\n```\n{chunk['content'][:1500]}\n```\n"

    # System prompt with repository context
    system_prompt = f"""You are n9r, an AI assistant specialized in code analysis and improvement.
You are helping with repository: {thread.repository.full_name}

Your role is to:
1. Answer questions about the codebase
2. Explain code patterns and issues found
3. Suggest improvements and best practices
4. Help understand technical debt and how to address it

Be concise, technical, and helpful. Reference specific files and line numbers when relevant.
{context_section}
"""

    if thread.context_file:
        system_prompt += f"\nUser is currently viewing: {thread.context_file}"

    messages.append({"role": "system", "content": system_prompt})

    # Add conversation history (last 10 messages)
    for msg in sorted(thread.messages, key=lambda x: x.created_at)[-10:]:
        messages.append({"role": msg.role, "content": msg.content})

    # Add current message
    messages.append({"role": "user", "content": user_message})

    return messages


@router.delete("/chat/threads/{thread_id}")
async def delete_thread(
    thread_id: UUID,
    db: DbSession,
    user: CurrentUser,
) -> dict:
    """Delete a chat thread."""
    result = await db.execute(
        select(ChatThread).where(
            ChatThread.id == thread_id,
            ChatThread.user_id == user.id,
        )
    )
    thread = result.scalar_one_or_none()

    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")

    await db.delete(thread)
    await db.commit()

    return {"status": "deleted"}
