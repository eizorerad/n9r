"""Chat API endpoints with RAG support.

**Feature: commit-aware-rag**
"""

import logging
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from qdrant_client import QdrantClient
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.rate_limit import enforce_rate_limit

from app.api.deps import CurrentUser, DbSession
from app.core.config import settings
from app.models.chat import ChatMessage, ChatThread
from app.models.repository import Repository
from app.services.github import GitHubService
from app.services.llm_gateway import get_llm_gateway
from app.services.vector_store import VectorStoreService

logger = logging.getLogger(__name__)
router = APIRouter()

# Qdrant collection name
COLLECTION_NAME = "code_embeddings"

# Safety limits for best-effort context pack (not a full tool loop yet)
_MAX_TREE_DEPTH = 6
_MAX_TREE_ENTRIES = 2000
_MAX_TREE_LINES = 2000
_MAX_ACTIVE_FILE_CHARS = 12000
_MAX_FILE_BYTES = 1_000_000  # GitHub contents API limit
_SENSITIVE_PATH_SUBSTRINGS = [
    "/.env",
    ".env",
    "id_rsa",
    ".pem",
    "secrets",
    "secret",
    "private_key",
    "credentials",
]


@router.get("/chat/models")
async def list_chat_models(user: CurrentUser) -> dict:
    """List supported chat models and whether they are available in this environment.

    Availability is determined by presence of provider credentials in env.
    """
    llm = get_llm_gateway()

    # Curated supported list (can be expanded later)
    supported = [
        {"id": "gemini/gemini-3-pro-preview", "label": "Gemini 3 Pro", "provider": "gemini"},
        {"id": "bedrock/anthropic.claude-sonnet-4-5-20250929-v1:0", "label": "Claude Sonnet 4.5 (Bedrock)", "provider": "bedrock"},
        {"id": "azure/gpt-5.1-codex-mini", "label": "Azure Codex 5.1 Mini", "provider": "azure"},
        {"id": "openai/gpt-4o", "label": "OpenAI GPT-4o", "provider": "openai"},
        {"id": "openai/gpt-5", "label": "OpenAI GPT-5", "provider": "openai"},
        {"id": "openrouter/anthropic/claude-3.5-sonnet", "label": "OpenRouter Claude 3.5 Sonnet", "provider": "openrouter"},
    ]

    # Determine availability using the same mapping concept as the gateway
    key_mapping = getattr(llm, "_MODEL_KEY_MAPPING", {})
    import os

    def availability(model_id: str) -> tuple[bool, str | None]:
        for prefix, env_key in key_mapping.items():
            if model_id.startswith(prefix):
                if os.environ.get(env_key):
                    return True, None
                return False, f"Missing {env_key}"
        # Unknown prefix: treat as unavailable
        return False, "Unsupported provider"

    models = []
    for m in supported:
        ok, reason = availability(m["id"])
        models.append(
            {
                **m,
                "available": ok,
                "reason_unavailable": reason,
                "is_default": m["id"] == llm.DEFAULT_MODELS.get("chat"),
            }
        )

    return {
        "models": models,
        "defaults": llm.DEFAULT_MODELS,
    }


def get_qdrant_client() -> QdrantClient:
    """Get Qdrant client with configured timeout."""
    return QdrantClient(
        host=settings.qdrant_host,
        port=settings.qdrant_port,
        timeout=settings.qdrant_timeout,
    )


def _is_sensitive_repo_path(path: str) -> bool:
    p = (path or "").lower()
    return any(s in p for s in _SENSITIVE_PATH_SUBSTRINGS)


async def _get_repo_tree_lines(
    repository_id: UUID,
    user_id: UUID,
    path: str,
    ref: str | None,
    depth: int,
    max_entries: int,
) -> tuple[list[str], str]:
    """Best-effort tree snapshot using cache first, then GitHub contents API.

    This is not a full agent tool. It is used to reduce hallucinations by giving
    the model a partial view of the repo structure.
    
    Returns:
        Tuple of (tree_lines, source) where source is "cache" or "github_api"
        
    **Feature: repo-content-cache**
    **Validates: Requirements 1.1, 6.1**
    """
    if depth <= 0:
        return [], "none"
    if max_entries <= 0:
        return [], "none"

    # Verify repository ownership and get full_name/default_branch + user token
    from app.core.database import async_session_maker
    from app.core.encryption import decrypt_token_or_none
    from app.models.user import User
    from app.services.repo_content import RepoContentService

    async with async_session_maker() as db:
        result = await db.execute(
            select(Repository).where(
                Repository.id == repository_id,
                Repository.owner_id == user_id,
            )
        )
        repo = result.scalar_one_or_none()
        if not repo:
            return [], "none"

        user_result = await db.execute(select(User).where(User.id == user_id))
        user = user_result.scalar_one_or_none()
        if not user:
            return [], "none"

        github_token = decrypt_token_or_none(user.access_token_encrypted)
        if not github_token:
            return [], "none"

        target_ref = ref or repo.default_branch

        # Try cache first (fast path)
        # **Feature: repo-content-cache**
        # **Validates: Requirements 1.1, 6.1**
        if target_ref:
            try:
                repo_content_service = RepoContentService()
                cached_tree = await repo_content_service.get_tree(
                    db=db,
                    repository_id=repository_id,
                    commit_sha=target_ref,
                )
                if cached_tree:
                    # Format cached tree into lines with proper indentation
                    lines = _format_cached_tree_lines(
                        cached_tree,
                        path=path or "",
                        depth=depth,
                        max_entries=max_entries,
                    )
                    if lines:
                        logger.debug(
                            f"Cache hit for tree {target_ref[:7]}: {len(lines)} lines"
                        )
                        return lines, "cache"
            except Exception as e:
                logger.warning(f"Cache tree retrieval failed, falling back to GitHub: {e}")

    # Fall back to GitHub API (slow path)
    github = GitHubService(github_token)
    owner, repo_name = repo.full_name.split("/")

    # BFS traversal with depth limit
    lines: list[str] = []
    queue: list[tuple[str, int]] = [(path or "", 0)]
    seen: set[str] = set()

    while queue and len(lines) < _MAX_TREE_LINES and len(seen) < max_entries:
        current_path, level = queue.pop(0)
        if current_path in seen:
            continue
        seen.add(current_path)

        try:
            contents = await github.get_repository_contents(
                owner=owner,
                repo=repo_name,
                path=current_path,
                ref=target_ref,
            )
        except Exception:
            continue

        if isinstance(contents, dict):
            # file, not directory
            continue

        # Sort dirs first then files
        contents_sorted = sorted(
            contents,
            key=lambda x: (x.get("type") != "dir", (x.get("name") or "").lower()),
        )

        indent = "  " * level
        for item in contents_sorted:
            if len(lines) >= _MAX_TREE_LINES or len(seen) >= max_entries:
                break
            name = item.get("name") or ""
            item_path = item.get("path") or ""
            item_type = item.get("type")
            if item_type == "dir":
                lines.append(f"{indent}- {name}/")
                if level + 1 < depth and item_path not in seen:
                    queue.append((item_path, level + 1))
            else:
                lines.append(f"{indent}- {name}")

    return lines, "github_api"


def _format_cached_tree_lines(
    cached_tree: list[str],
    path: str,
    depth: int,
    max_entries: int,
) -> list[str]:
    """Format cached tree paths into indented lines.
    
    The cached tree is a flat list of file paths. This function filters
    by the requested path prefix and formats with proper indentation.
    
    Args:
        cached_tree: List of file paths from cache
        path: Path prefix to filter by (empty string for root)
        depth: Maximum depth to display
        max_entries: Maximum number of entries to return
        
    Returns:
        List of formatted tree lines with indentation
    """
    if not cached_tree:
        return []
    
    # Normalize path prefix
    path_prefix = path.rstrip("/") + "/" if path else ""
    
    # Filter paths by prefix and build directory structure
    entries: dict[str, set[str]] = {}  # dir_path -> set of immediate children
    
    for file_path in cached_tree:
        # Skip if doesn't match prefix
        if path_prefix and not file_path.startswith(path_prefix):
            continue
        
        # Get relative path from the prefix
        rel_path = file_path[len(path_prefix):] if path_prefix else file_path
        
        # Split into parts and track directory structure
        parts = rel_path.split("/")
        
        # Track each level of the path
        current_dir = ""
        for i, part in enumerate(parts):
            if i >= depth:
                break
            
            parent_dir = current_dir
            current_dir = f"{current_dir}/{part}" if current_dir else part
            
            # Add to parent's children
            if parent_dir not in entries:
                entries[parent_dir] = set()
            
            # Mark as directory if not the last part
            if i < len(parts) - 1:
                entries[parent_dir].add(f"{part}/")
            else:
                entries[parent_dir].add(part)
    
    # Build formatted lines using BFS
    lines: list[str] = []
    queue: list[tuple[str, int]] = [("", 0)]
    
    while queue and len(lines) < max_entries:
        current_dir, level = queue.pop(0)
        
        if current_dir not in entries:
            continue
        
        # Sort: directories first, then alphabetically
        children = sorted(
            entries[current_dir],
            key=lambda x: (not x.endswith("/"), x.lower()),
        )
        
        indent = "  " * level
        for child in children:
            if len(lines) >= max_entries:
                break
            
            lines.append(f"{indent}- {child}")
            
            # Queue subdirectories for traversal
            if child.endswith("/") and level + 1 < depth:
                child_path = f"{current_dir}/{child[:-1]}" if current_dir else child[:-1]
                queue.append((child_path, level + 1))
    
    return lines


async def _read_repo_file_text(
    repository_id: UUID,
    user_id: UUID,
    file_path: str,
    ref: str | None,
    max_chars: int,
) -> tuple[str, str]:
    """Read a repo file using cache first, then GitHub contents API.
    
    Returns:
        Tuple of (content, source) where source is "cache" or "github_api"
        
    **Feature: repo-content-cache**
    **Validates: Requirements 1.2, 1.3, 6.1**
    """
    if not file_path:
        return "", "none"
    if _is_sensitive_repo_path(file_path):
        return "", "blocked"

    # Verify repository ownership and get full_name/default_branch + user token
    from app.core.database import async_session_maker
    from app.core.encryption import decrypt_token_or_none
    from app.models.user import User
    from app.services.repo_content import RepoContentService

    async with async_session_maker() as db:
        result = await db.execute(
            select(Repository).where(
                Repository.id == repository_id,
                Repository.owner_id == user_id,
            )
        )
        repo = result.scalar_one_or_none()
        if not repo:
            return "", "none"

        user_result = await db.execute(select(User).where(User.id == user_id))
        user = user_result.scalar_one_or_none()
        if not user:
            return "", "none"

        github_token = decrypt_token_or_none(user.access_token_encrypted)
        if not github_token:
            return "", "none"

        target_ref = ref or repo.default_branch

        # Try cache first (fast path)
        # **Feature: repo-content-cache**
        # **Validates: Requirements 1.2, 1.3, 6.1**
        if target_ref:
            try:
                repo_content_service = RepoContentService()
                cached_content = await repo_content_service.get_file(
                    db=db,
                    repository_id=repository_id,
                    commit_sha=target_ref,
                    file_path=file_path,
                )
                if cached_content is not None:
                    logger.debug(
                        f"Cache hit for file {file_path} at {target_ref[:7]}"
                    )
                    if len(cached_content) > max_chars:
                        return cached_content[:max_chars] + "\n\n[... truncated ...]", "cache"
                    return cached_content, "cache"
            except Exception as e:
                logger.warning(f"Cache file retrieval failed, falling back to GitHub: {e}")

    # Fall back to GitHub API (slow path)
    github = GitHubService(github_token)
    owner, repo_name = repo.full_name.split("/")

    # Metadata check (size/binary) similar to repositories.py
    try:
        file_info = await github.get_repository_contents(
            owner=owner,
            repo=repo_name,
            path=file_path,
            ref=target_ref,
        )
        if isinstance(file_info, list):
            return "", "github_api"
        file_size = int(file_info.get("size", 0) or 0)
        if file_size > _MAX_FILE_BYTES:
            return "", "github_api"
        file_content = file_info.get("content", "")
        if not file_content and file_size > 0:
            return "", "github_api"
    except Exception:
        # fall back to direct read
        pass

    try:
        content = await github.get_file_content(
            owner=owner,
            repo=repo_name,
            path=file_path,
            ref=target_ref,
        )
    except Exception:
        return "", "github_api"

    if not content:
        return "", "github_api"
    if len(content) > max_chars:
        return content[:max_chars] + "\n\n[... truncated ...]", "github_api"
    return content, "github_api"


class CreateThreadRequest(BaseModel):
    """Create chat thread request."""
    title: str | None = None
    context_file: str | None = None
    context_issue_id: UUID | None = None
    # Default model for this thread (provider-prefixed, e.g. "gemini/gemini-3-pro-preview")
    model: str | None = None


class ChatTreeContext(BaseModel):
    path: str = ""
    depth: int = 4
    max_entries: int = 500


class ChatContext(BaseModel):
    ref: str | None = None
    active_file: str | None = None
    open_files: list[str] | None = None
    tree: ChatTreeContext | None = None


class SendMessageRequest(BaseModel):
    """Send message request."""
    content: str
    stream: bool = True
    # Optional per-message model override (provider-prefixed)
    model: str | None = None
    # IDE context pack (ref, active/open files, tree request)
    context: ChatContext | None = None


@router.post("/repositories/{repository_id}/chat/threads")
async def create_thread(
    repository_id: UUID,
    payload: CreateThreadRequest,
    db: DbSession,
    user: CurrentUser,
    request: Request,
) -> dict:
    """Create a new chat thread for a repository."""
    enforce_rate_limit(
        request,
        user_id=str(user.id),
        limit_per_minute=settings.rate_limit_per_minute,
        scope="chat:create_thread",
    )

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
        model=payload.model,
    )
    db.add(thread)
    await db.commit()
    await db.refresh(thread)

    return {
        "id": str(thread.id),
        "title": thread.title,
        "context_file": thread.context_file,
        "model": thread.model,
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
                "model": t.model,
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
        "model": thread.model,
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
    request: Request,
):
    """Send a message and get AI response (with optional streaming)."""
    enforce_rate_limit(
        request,
        user_id=str(user.id),
        limit_per_minute=settings.rate_limit_chat_per_minute,
        scope="chat:send_message",
    )

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

    # Resolve model: per-message override > thread default > gateway default
    resolved_model = payload.model or thread.model

    if payload.stream:
        # Return streaming response (structured SSE)
        # Context building is done inside _stream_response for real-time visibility
        return StreamingResponse(
            _stream_response(
                thread,
                payload.content,
                db,
                model=resolved_model,
                context=payload.context,
            ),
            media_type="text/event-stream",
        )
    else:
        # Non-streaming response - build context here
        messages = await _build_chat_messages(thread, payload.content, context=payload.context)
        llm = get_llm_gateway()
        response = await llm.chat(messages=messages, model=resolved_model)

        # Save assistant message
        assistant_message = ChatMessage(
            thread_id=thread_id,
            role="assistant",
            content=response["content"],
            tokens_used=response.get("usage", {}).get("total_tokens"),
        )
        db.add(assistant_message)
        thread.message_count += 2
        await db.commit()

        return {
            "message": {
                "id": str(assistant_message.id),
                "role": "assistant",
                "content": response["content"],
                "model": response.get("model"),
            }
        }


async def _stream_response(
    thread: ChatThread,
    user_message: str,
    db,
    model: str | None = None,
    context: ChatContext | None = None,
):
    """Stream LLM response (SSE) and persist assistant message at the end.

    Structured SSE events:
      - event: context_source  data: {"source": "...", "status": "found"|"empty"|"error", "detail": "...", "count": N}
      - event: step            data: {"title": "...", "detail": "..."}
      - event: tool_call       data: {"name": "...", "args": {...}}
      - event: tool_result     data: {"name": "...", "ok": true, "result": {...} | null, "error": "..."}
      - event: token           data: {"delta": "..."}
      - event: done            data: {"message_id": "...", "model": "...", "usage": {...}, "cost": 0.0}
      - event: error           data: {"detail": "..."}
    """
    import json
    import re
    from dataclasses import dataclass
    from typing import Any

    llm = get_llm_gateway()
    full_response: list[str] = []

    # ----------------------------
    # Tool loop configuration
    # ----------------------------
    MAX_TOOL_CALLS = 8
    MAX_TOTAL_TOOL_CHARS = 200_000
    MAX_TOOL_RESULT_CHARS = 50_000

    @dataclass
    class ToolCall:
        name: str
        arguments: dict[str, Any]

    def _sse(event: str, payload: dict) -> str:
        return f"event: {event}\n" + "data: " + json.dumps(payload) + "\n\n"

    def _emit_step(title: str, detail: str | None = None):
        payload = {"title": title}
        if detail:
            payload["detail"] = detail
        return _sse("step", payload)

    def _emit_context_source(
        source: str,
        status: str,
        detail: str | None = None,
        count: int | None = None,
    ):
        """Emit context_source event for agent log visibility.
        
        Args:
            source: "rag", "tree", "active_file", "github_api"
            status: "found", "empty", "error", "searching", "loading"
            detail: human-readable detail
            count: number of items found (if applicable)
        """
        payload: dict[str, Any] = {"source": source, "status": status}
        if detail:
            payload["detail"] = detail
        if count is not None:
            payload["count"] = count
        return _sse("context_source", payload)

    def _parse_tool_calls(content: str) -> list[ToolCall]:
        """Parse tool calls from LLM output, handling nested JSON objects.
        
        Handles:
        - Plain JSON: {"tool":"read_file","arguments":{...}}
        - Markdown code blocks: ```json\n{...}\n```
        - Text before/after JSON
        """
        tool_calls: list[ToolCall] = []
        
        # Strip markdown code blocks if present
        stripped = content.strip()
        if stripped.startswith("```"):
            # Remove opening fence (```json or ```)
            first_newline = stripped.find("\n")
            if first_newline != -1:
                stripped = stripped[first_newline + 1:]
            # Remove closing fence
            if stripped.rstrip().endswith("```"):
                stripped = stripped.rstrip()[:-3].rstrip()
            content = stripped
        
        # Find all potential JSON object starts
        i = 0
        while i < len(content):
            if content[i] == '{':
                # Try to extract a complete JSON object by brace counting
                brace_count = 0
                start = i
                j = i
                while j < len(content):
                    c = content[j]
                    
                    # Handle string literals - skip to avoid counting braces inside strings
                    if c == '"':
                        j += 1
                        while j < len(content):
                            if content[j] == '\\' and j + 1 < len(content):
                                j += 2  # Skip escape sequence
                            elif content[j] == '"':
                                j += 1  # Move past closing quote
                                break
                            else:
                                j += 1
                        continue  # Continue to next character after string
                    
                    if c == '{':
                        brace_count += 1
                    elif c == '}':
                        brace_count -= 1
                        if brace_count == 0:
                            # Found complete JSON object
                            json_str = content[start:j+1]
                            try:
                                data = json.loads(json_str)
                                # Check if this is a tool call
                                if isinstance(data, dict):
                                    tool_name = None
                                    args = None
                                    
                                    if isinstance(data.get("tool_call"), dict):
                                        tc = data["tool_call"]
                                        tool_name = tc.get("name")
                                        args = tc.get("arguments", {})
                                    else:
                                        tool_name = data.get("tool") or data.get("name")
                                        args = data.get("arguments", data.get("params", {}))
                                    
                                    if tool_name and isinstance(args, dict):
                                        logger.debug(
                                            f"[tool_parse] Found tool call: {tool_name}",
                                            extra={"tool": tool_name, "args_keys": list(args.keys())},
                                        )
                                        tool_calls.append(ToolCall(name=str(tool_name), arguments=args))
                                    else:
                                        logger.debug(
                                            f"[tool_parse] JSON object is not a tool call: tool_name={tool_name}, args_type={type(args).__name__}",
                                        )
                            except json.JSONDecodeError as e:
                                logger.debug(f"[tool_parse] JSON decode error: {e}, content={json_str[:100]}")
                            i = j  # Continue after this JSON object
                            break
                    j += 1
            i += 1
        
        if not tool_calls:
            # Log for debugging when no tool calls found
            preview = content[:200] if len(content) > 200 else content
            logger.debug(f"[tool_parse] No tool calls found in content: {preview!r}")
        
        return tool_calls

    async def _tool_list_files(args: dict[str, Any]) -> dict[str, Any]:
        path = str(args.get("path") or "")
        depth = int(args.get("depth") or 2)
        max_entries = int(args.get("max_entries") or 200)
        depth = max(0, min(depth, _MAX_TREE_DEPTH))
        max_entries = max(10, min(max_entries, _MAX_TREE_ENTRIES))

        # IMPORTANT: default to the IDE-selected ref (commit SHA / branch) so tool calls
        # inspect the same snapshot the user is viewing.
        requested_ref = (args.get("ref") or args.get("commit") or args.get("commit_sha"))
        tool_ref = str(requested_ref) if requested_ref else None
        resolved_ref = tool_ref or (context.ref if context else None)

        lines, source = await _get_repo_tree_lines(
            repository_id=thread.repository_id,
            user_id=thread.user_id,
            path=path,
            ref=resolved_ref,
            depth=depth,
            max_entries=max_entries,
        )
        return {
            "path": path,
            "depth": depth,
            "ref": resolved_ref,
            "lines": lines[:_MAX_TREE_LINES],
            "source": source,
        }

    async def _tool_read_file(args: dict[str, Any]) -> dict[str, Any]:
        file_path = str(args.get("path") or args.get("file_path") or "")
        max_chars = int(args.get("max_chars") or 12000)
        max_chars = max(1000, min(max_chars, 50_000))

        requested_ref = (args.get("ref") or args.get("commit") or args.get("commit_sha"))
        tool_ref = str(requested_ref) if requested_ref else None
        resolved_ref = tool_ref or (context.ref if context else None)

        content, source = await _read_repo_file_text(
            repository_id=thread.repository_id,
            user_id=thread.user_id,
            file_path=file_path,
            ref=resolved_ref,
            max_chars=max_chars,
        )
        return {"path": file_path, "ref": resolved_ref, "content": content, "source": source}

    async def _tool_semantic_search(args: dict[str, Any]) -> dict[str, Any]:
        q = str(args.get("query") or args.get("q") or "")
        limit = int(args.get("limit") or 8)
        limit = max(1, min(limit, 20))
        # Use commit_sha resolved for this chat session (commit-aware RAG)
        hits = await _get_rag_context(
            repository_id=thread.repository_id,
            query=q,
            context_file=None,
            limit=limit,
            commit_sha=resolved_commit_sha,  # commit-aware filter
        )
        for h in hits:
            if h.get("content"):
                h["content"] = (h["content"] or "")[:500]
        return {"query": q, "results": hits, "commit_sha": resolved_commit_sha}

    async def _execute_tool(tool_call: ToolCall) -> tuple[bool, dict[str, Any] | None, str | None]:
        name = tool_call.name
        args = tool_call.arguments or {}

        if name == "read_file":
            p = str(args.get("path") or args.get("file_path") or "")
            if _is_sensitive_repo_path(p):
                return False, None, "Blocked sensitive path"

        try:
            if name == "list_files":
                return True, await _tool_list_files(args), None
            if name == "read_file":
                return True, await _tool_read_file(args), None
            if name == "semantic_search":
                return True, await _tool_semantic_search(args), None
            return False, None, f"Unknown tool: {name}"
        except Exception as e:
            return False, None, str(e)

    # ----------------------------
    # Tool loop prompt
    # ----------------------------
    tool_system = """You may call tools to inspect the repository.

When you need to use a tool, output ONLY a single JSON object in one line:
{"tool":"<name>","arguments":{...}}

Available tools:
- list_files(path, depth, max_entries)
- read_file(path, max_chars)
- semantic_search(query, limit)

Rules:
- Do not guess file paths or file contents. Use tools if unsure.
- Keep tool calls minimal.
- IMPORTANT: After you have enough info, answer normally in plain text (NOT JSON).
"""

    try:
        # =====================================================
        # Phase 0: Resolve commit SHA for commit-aware RAG
        # =====================================================
        resolved_commit_sha: str | None = None
        commit_resolution_source = "none"

        if context and context.ref:
            yield _emit_context_source(
                "commit",
                "resolving",
                f"Resolving ref: {context.ref}",
            )
            try:
                from app.core.database import async_session_maker
                async with async_session_maker() as ref_db:
                    vs = VectorStoreService()
                    resolution = await vs.resolve_ref_to_commit_sha_async(
                        db=ref_db,
                        repository_id=thread.repository_id,
                        user_id=thread.user_id,
                        ref=context.ref,
                    )
                    resolved_commit_sha = resolution.resolved_commit_sha
                    commit_resolution_source = resolution.source

                if resolved_commit_sha:
                    yield _emit_context_source(
                        "commit",
                        "found",
                        f"Resolved to {resolved_commit_sha[:7]} (via {commit_resolution_source})",
                    )
                else:
                    yield _emit_context_source(
                        "commit",
                        "empty",
                        "Could not resolve ref; using repo-wide filter",
                    )
            except Exception as e:
                logger.warning(f"Failed to resolve ref to commit SHA: {e}")
                yield _emit_context_source("commit", "error", str(e)[:100])

        # =====================================================
        # Phase 1: Gather context with real-time visibility
        # =====================================================
        # Note: Individual context_source events provide granular visibility,
        # so we don't emit a generic "Gathering context" step here.

        # --- RAG Context (commit-aware) ---
        filter_detail = f"commit={resolved_commit_sha[:7]}" if resolved_commit_sha else "repo-wide"
        yield _emit_context_source("rag", "searching", f"Searching vector database ({filter_detail})")
        rag_chunks = await _get_rag_context(
            repository_id=thread.repository_id,
            query=user_message,
            context_file=thread.context_file,
            commit_sha=resolved_commit_sha,
        )
        if rag_chunks:
            # Calculate average score for detail
            avg_score = sum(c.get("score", 0) or 0 for c in rag_chunks) / len(rag_chunks)
            files_found = list(set(c.get("file_path", "?") for c in rag_chunks))[:3]
            yield _emit_context_source(
                "rag",
                "found",
                f"Found in: {', '.join(files_found)}{'...' if len(files_found) < len(rag_chunks) else ''} (avg score: {avg_score:.2f})",
                count=len(rag_chunks),
            )
        else:
            yield _emit_context_source(
                "rag",
                "empty",
                "No vectors found for this repository/commit. Using GitHub API fallback.",
            )

        # Build RAG context section
        context_section = ""
        if rag_chunks:
            context_section = "\n\n## Relevant Code Context (from vector search):\n"
            for i, chunk in enumerate(rag_chunks, 1):
                context_section += f"\n### {i}. {chunk['file_path']}"
                if chunk['name']:
                    context_section += f" - {chunk['chunk_type']} `{chunk['name']}`"
                if chunk['line_start']:
                    context_section += f" (lines {chunk['line_start']}-{chunk['line_end']})"
                context_section += f"\n```\n{(chunk.get('content') or '')[:1500]}\n```\n"

        # --- IDE Context Pack ---
        ide_section = ""
        if context:
            if context.ref:
                ide_section += f"\n\n## IDE Context\n- ref: {context.ref}"
            if context.active_file:
                ide_section += f"\n- active_file: {context.active_file}"
            if context.open_files:
                open_files = context.open_files[:20]
                ide_section += "\n- open_files:\n" + "\n".join(f"  - {p}" for p in open_files)

            # --- Repository Tree ---
            # **Feature: repo-content-cache**
            # **Validates: Requirements 1.1, 6.1**
            tree_lines: list[str] = []
            tree_source: str = "none"
            if context.tree:
                yield _emit_context_source("tree", "loading", "Fetching repository structure")
                try:
                    tree_lines, tree_source = await _get_repo_tree_lines(
                        repository_id=thread.repository_id,
                        user_id=thread.user_id,
                        path=context.tree.path or "",
                        ref=context.ref,
                        depth=max(0, min(context.tree.depth, _MAX_TREE_DEPTH)),
                        max_entries=max(50, min(context.tree.max_entries, _MAX_TREE_ENTRIES)),
                    )
                    if tree_lines:
                        source_label = "cache" if tree_source == "cache" else "GitHub API"
                        yield _emit_context_source(
                            "tree",
                            "found",
                            f"Loaded {len(tree_lines)} entries from {source_label}",
                            count=len(tree_lines),
                        )
                    else:
                        yield _emit_context_source("tree", "empty", "No tree entries returned")
                except Exception as e:
                    logger.warning(f"Failed to build repo tree context: {e}")
                    yield _emit_context_source("tree", "error", str(e)[:100])
                    tree_lines = []

            if tree_lines:
                source_label = "cache" if tree_source == "cache" else "GitHub API"
                ide_section += f"\n\n## Repository Tree (partial, via {source_label})\n" + "\n".join(tree_lines[:2000])

            # --- Active File Content ---
            # **Feature: repo-content-cache**
            # **Validates: Requirements 1.2, 1.3, 6.1**
            if context.active_file:
                yield _emit_context_source(
                    "active_file",
                    "loading",
                    f"Reading {context.active_file}",
                )
                try:
                    active_content, file_source = await _read_repo_file_text(
                        repository_id=thread.repository_id,
                        user_id=thread.user_id,
                        file_path=context.active_file,
                        ref=context.ref,
                        max_chars=_MAX_ACTIVE_FILE_CHARS,
                    )
                    if active_content:
                        source_label = "cache" if file_source == "cache" else "GitHub API"
                        yield _emit_context_source(
                            "active_file",
                            "found",
                            f"Loaded {len(active_content)} chars from {source_label}",
                            count=len(active_content),
                        )
                        ide_section += (
                            f"\n\n## Active File Content: {context.active_file} (via {source_label})\n"
                            f"```text\n{active_content}\n```"
                        )
                    else:
                        yield _emit_context_source(
                            "active_file",
                            "empty",
                            "File not found or blocked",
                        )
                except Exception as e:
                    logger.warning(f"Failed to read active file for context: {e}")
                    yield _emit_context_source("active_file", "error", str(e)[:100])

        # Build system prompt
        system_prompt = f"""You are n9r, an AI assistant specialized in code analysis and improvement.
You are helping with repository: {thread.repository.full_name}

**CRITICAL RULES:**
- NEVER generate fake/placeholder/example code blocks. If the user asks to "show code", use the read_file tool to get the ACTUAL code.
- Do not guess file paths or file contents. Use the list_files or read_file tools when you need to inspect code.
- If the context below already contains the relevant code, quote it directly instead of inventing code.
- Prefer citing exact file paths and (when available) line ranges.
- Treat retrieved context (below) as source of truth.

Your role is to:
1. Answer questions about the codebase
2. Explain code patterns and issues found
3. Suggest improvements and best practices
4. Help understand technical debt and how to address it

Be concise, technical, and helpful. Reference specific files and line numbers when relevant.
{context_section}{ide_section}
"""

        if thread.context_file:
            system_prompt += f"\nUser is currently viewing: {thread.context_file}"

        # Build messages array
        messages: list[dict[str, str]] = []
        messages.append({"role": "system", "content": system_prompt})

        # Add conversation history (last 10 messages)
        for msg in sorted(thread.messages, key=lambda x: x.created_at)[-10:]:
            messages.append({"role": msg.role, "content": msg.content})

        # Add current message
        messages.append({"role": "user", "content": user_message})

        # =====================================================
        # Phase 2: Tool loop
        # =====================================================
        tool_messages = [{"role": "system", "content": tool_system}] + list(messages)

        tool_calls_used = 0
        total_tool_chars = 0
        final_answer_seed: str | None = None

        while tool_calls_used < MAX_TOOL_CALLS:
            # Emit reasoning step with iteration counter for visibility
            yield _emit_step(
                f"Reasoning{f' ({tool_calls_used + 1})' if tool_calls_used > 0 else ''}",
                "Processing with AI model"
            )
            
            resp = await llm.chat(
                messages=tool_messages,
                model=model,
                temperature=0.2,
                max_tokens=1024,
                fallback=True,  # Enable fallback for resilience against API 500 errors
            )
            content = (resp.get("content") or "").strip()

            # Parse tool calls from anywhere in the content (not just at start)
            # The model may output explanatory text before/after the JSON tool call
            calls = _parse_tool_calls(content)
            if not calls:
                # No tool calls found - this is the final answer
                final_answer_seed = content
                tool_messages.append({"role": "assistant", "content": content})
                break

            # Execute only the first tool call (one at a time)
            call = calls[0]
            tool_calls_used += 1
            yield _sse("tool_call", {"name": call.name, "args": call.arguments})

            ok, result, err = await _execute_tool(call)
            if result is not None:
                result_str = json.dumps(result)
                total_tool_chars += len(result_str)
                if total_tool_chars > MAX_TOTAL_TOOL_CHARS:
                    ok = False
                    result = None
                    err = "Tool budget exceeded"

                if result_str and len(result_str) > MAX_TOOL_RESULT_CHARS:
                    result = {"truncated": True, "preview": result_str[:MAX_TOOL_RESULT_CHARS]}

            yield _sse("tool_result", {"name": call.name, "ok": ok, "result": result, "error": err})

            # Feed tool result back to model as user message (do NOT store tool JSON as assistant content)
            tool_messages.append(
                {
                    "role": "user",
                    "content": (
                        f"Tool result for {call.name}:\n"
                        f"{json.dumps({'ok': ok, 'result': result, 'error': err})}\n\n"
                        "If you have enough info now, answer in plain text. Otherwise, output the next tool JSON."
                    ),
                }
            )

        # If the model already produced a plain-text answer, stream it directly (no second model call)
        if final_answer_seed:
            yield _emit_step("Formatting", "Preparing response")
            for chunk in [final_answer_seed[i:i+200] for i in range(0, len(final_answer_seed), 200)]:
                full_response.append(chunk)
                yield "event: token\n"
                yield f"data: {json.dumps({'delta': chunk})}\n\n"
            content = "".join(full_response)
            final_stats = None
            tokens_used = None
            cost = None
            final_model = model
        else:
            # Otherwise, ask for a final answer explicitly and stream it
            yield _emit_step("Answering", "Streaming final response")
            tool_messages.append(
                {
                    "role": "user",
                    "content": "Provide the final answer now in plain text. Do not output JSON.",
                }
            )
            token_iter, final_stats_future = await llm.chat_stream_with_usage(
                messages=tool_messages,
                model=model,
                max_tokens=16384,  # Large limit for code-heavy responses
            )

            async for chunk in token_iter:
                full_response.append(chunk)
                yield "event: token\n"
                yield f"data: {json.dumps({'delta': chunk})}\n\n"

            content = "".join(full_response)

            final_stats = None
            try:
                final_stats = await final_stats_future
            except Exception:
                final_stats = None

            tokens_used = None
            cost = None
            final_model = None
            if final_stats:
                final_model = final_stats.get("model")
                usage = final_stats.get("usage") or {}
                tokens_used = usage.get("total_tokens")
                cost = final_stats.get("cost")

        assistant_message = ChatMessage(
            thread_id=thread.id,
            role="assistant",
            content=content,
            tokens_used=tokens_used,
        )
        db.add(assistant_message)
        thread.message_count += 1
        await db.commit()

        yield "event: done\n"
        yield (
            "data: "
            + json.dumps(
                {
                    "message_id": str(assistant_message.id),
                    "model": final_model or model,
                    "usage": (final_stats or {}).get("usage") if 'final_stats' in locals() else None,
                    "cost": cost,
                }
            )
            + "\n\n"
        )
    except Exception as e:
        logger.exception("Chat streaming failed")
        yield "event: error\n"
        yield f"data: {json.dumps({'detail': str(e)})}\n\n"


async def _get_rag_context(
    repository_id: UUID,
    query: str,
    context_file: str | None = None,
    limit: int = 5,
    commit_sha: str | None = None,
) -> list[dict]:
    """Retrieve relevant code chunks from Qdrant for RAG.

    Uses Qdrant `query_points` API (compatible with newer qdrant-client versions).

    Args:
        repository_id: UUID of the repository
        query: Search query text
        context_file: Optional file to prioritize in results
        limit: Maximum results to return
        commit_sha: Optional commit SHA for commit-aware filtering

    **Feature: commit-aware-rag**
    """
    try:
        llm = get_llm_gateway()
        qdrant = get_qdrant_client()

        # Generate embedding for query
        query_embedding = await llm.embed([query])

        from qdrant_client.models import FieldCondition, Filter, MatchValue

        # Build commit-aware filter
        must = [
            FieldCondition(key="repository_id", match=MatchValue(value=str(repository_id)))
        ]
        if commit_sha:
            must.append(
                FieldCondition(key="commit_sha", match=MatchValue(value=commit_sha))
            )

        # Optionally prioritize current file context
        if context_file:
            file_results = qdrant.query_points(
                collection_name=COLLECTION_NAME,
                query=query_embedding[0],
                query_filter=Filter(
                    must=must
                    + [FieldCondition(key="file_path", match=MatchValue(value=context_file))]
                ),
                limit=2,
            ).points

            other_results = qdrant.query_points(
                collection_name=COLLECTION_NAME,
                query=query_embedding[0],
                query_filter=Filter(
                    must=must,
                    must_not=[FieldCondition(key="file_path", match=MatchValue(value=context_file))],
                ),
                limit=max(0, limit - len(file_results)),
            ).points

            results = list(file_results) + list(other_results)
        else:
            results = qdrant.query_points(
                collection_name=COLLECTION_NAME,
                query=query_embedding[0],
                query_filter=Filter(must=must),
                limit=limit,
            ).points

        return [
            {
                "file_path": (hit.payload or {}).get("file_path"),
                "name": (hit.payload or {}).get("name"),
                "chunk_type": (hit.payload or {}).get("chunk_type"),
                "line_start": (hit.payload or {}).get("line_start"),
                "line_end": (hit.payload or {}).get("line_end"),
                "content": (hit.payload or {}).get("content"),
                "score": hit.score,
                "commit_sha": (hit.payload or {}).get("commit_sha"),
            }
            for hit in results
        ]
    except Exception as e:
        logger.warning(f"RAG context retrieval failed: {e}")
        return []


async def _build_chat_messages(
    thread: ChatThread,
    user_message: str,
    context: ChatContext | None = None,
) -> list[dict]:
    """Build messages array with RAG context + IDE context pack.

    Note: This function does not run an agent tool loop yet. It can, however,
    include a bounded repository tree snapshot and active file content to reduce
    hallucinations.
    """
    messages = []

    # Get RAG context
    rag_chunks = await _get_rag_context(
        repository_id=thread.repository_id,
        query=user_message,
        context_file=thread.context_file,
    )

    # Build RAG context section
    context_section = ""
    if rag_chunks:
        context_section = "\n\n## Relevant Code Context:\n"
        for i, chunk in enumerate(rag_chunks, 1):
            context_section += f"\n### {i}. {chunk['file_path']}"
            if chunk['name']:
                context_section += f" - {chunk['chunk_type']} `{chunk['name']}`"
            if chunk['line_start']:
                context_section += f" (lines {chunk['line_start']}-{chunk['line_end']})"
            context_section += f"\n```\n{(chunk.get('content') or '')[:1500]}\n```\n"

    # IDE context pack section (Phase A+)
    ide_section = ""
    if context:
        if context.ref:
            ide_section += f"\n\n## IDE Context\n- ref: {context.ref}"
        if context.active_file:
            ide_section += f"\n- active_file: {context.active_file}"
        if context.open_files:
            open_files = context.open_files[:20]
            ide_section += "\n- open_files:\n" + "\n".join(f"  - {p}" for p in open_files)

        # Best-effort: include a bounded tree snapshot to reduce hallucinations
        # **Feature: repo-content-cache**
        # **Validates: Requirements 1.1, 6.1**
        tree_lines: list[str] = []
        tree_source: str = "none"
        if context.tree:
            try:
                tree_lines, tree_source = await _get_repo_tree_lines(
                    repository_id=thread.repository_id,
                    user_id=thread.user_id,
                    path=context.tree.path or "",
                    ref=context.ref,
                    depth=max(0, min(context.tree.depth, _MAX_TREE_DEPTH)),
                    max_entries=max(50, min(context.tree.max_entries, _MAX_TREE_ENTRIES)),
                )
            except Exception as e:
                logger.warning(f"Failed to build repo tree context: {e}")
                tree_lines = []

        if tree_lines:
            source_label = "cache" if tree_source == "cache" else "GitHub API"
            ide_section += f"\n\n## Repository Tree (partial, via {source_label})\n" + "\n".join(tree_lines[:2000])

        # Best-effort: include active file content (bounded) to reduce hallucinations
        # **Feature: repo-content-cache**
        # **Validates: Requirements 1.2, 1.3, 6.1**
        if context.active_file:
            try:
                active_content, file_source = await _read_repo_file_text(
                    repository_id=thread.repository_id,
                    user_id=thread.user_id,
                    file_path=context.active_file,
                    ref=context.ref,
                    max_chars=_MAX_ACTIVE_FILE_CHARS,
                )
                if active_content:
                    source_label = "cache" if file_source == "cache" else "GitHub API"
                    ide_section += (
                        f"\n\n## Active File Content: {context.active_file} (via {source_label})\n"
                        f"```text\n{active_content}\n```"
                    )
            except Exception as e:
                logger.warning(f"Failed to read active file for context: {e}")

    # System prompt with repository context
    system_prompt = f"""You are n9r, an AI assistant specialized in code analysis and improvement.
You are helping with repository: {thread.repository.full_name}

**CRITICAL RULES:**
- NEVER generate fake/placeholder/example code blocks. If asked to "show code", you must quote actual code from the context below.
- Do not guess file paths or file contents. If you are not sure, say you do not know.
- If the context below already contains the relevant code, quote it directly instead of inventing code.
- Prefer citing exact file paths and (when available) line ranges.
- Treat retrieved context (below) as source of truth.

Your role is to:
1. Answer questions about the codebase
2. Explain code patterns and issues found
3. Suggest improvements and best practices
4. Help understand technical debt and how to address it

Be concise, technical, and helpful. Reference specific files and line numbers when relevant.
{context_section}{ide_section}
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
