"""Redis client for application-wide caching and state storage."""

import json
import logging
from collections.abc import AsyncGenerator
from contextlib import contextmanager
from typing import Any, Generator

import redis as sync_redis
import redis.asyncio as aioredis

from app.core.config import settings

logger = logging.getLogger(__name__)

# Async Redis pool for FastAPI
async_redis_pool = aioredis.ConnectionPool.from_url(
    str(settings.redis_url),
    decode_responses=True,
)

# Sync Redis pool for Celery workers
# Using ConnectionPool prevents connection leaks by reusing connections
sync_redis_pool = sync_redis.ConnectionPool.from_url(
    str(settings.redis_url),
    decode_responses=True,
    max_connections=50,  # Limit max connections to prevent exhaustion
)


async def get_redis() -> AsyncGenerator[aioredis.Redis, None]:
    """Dependency for getting async Redis client."""
    client = aioredis.Redis(connection_pool=async_redis_pool)
    try:
        yield client
    finally:
        await client.aclose()


def get_sync_redis() -> sync_redis.Redis:
    """Get sync Redis client from connection pool.
    
    Uses a shared connection pool to prevent connection leaks.
    Connections are automatically returned to the pool when the client
    is garbage collected or when used with get_sync_redis_context().
    """
    return sync_redis.Redis(connection_pool=sync_redis_pool)


@contextmanager
def get_sync_redis_context() -> Generator[sync_redis.Redis, None, None]:
    """Context manager for sync Redis client (recommended usage).
    
    Ensures the connection is properly returned to the pool after use.
    
    Usage:
        with get_sync_redis_context() as redis_client:
            redis_client.set("key", "value")
    """
    client = sync_redis.Redis(connection_pool=sync_redis_pool)
    try:
        yield client
    finally:
        client.close()


async def close_redis_pool() -> None:
    """Close Redis connection pools on shutdown."""
    await async_redis_pool.disconnect()
    sync_redis_pool.disconnect()


# OAuth state storage constants
OAUTH_STATE_PREFIX = "oauth:state:"
OAUTH_STATE_TTL = 600  # 10 minutes


async def store_oauth_state(state: str, redirect_uri: str) -> None:
    """Store OAuth state in Redis with TTL."""
    async with aioredis.Redis(connection_pool=async_redis_pool) as client:
        await client.setex(
            f"{OAUTH_STATE_PREFIX}{state}",
            OAUTH_STATE_TTL,
            redirect_uri,
        )


async def get_oauth_state(state: str) -> str | None:
    """Get OAuth state from Redis."""
    async with aioredis.Redis(connection_pool=async_redis_pool) as client:
        result = await client.get(f"{OAUTH_STATE_PREFIX}{state}")
        return str(result) if result is not None else None


async def delete_oauth_state(state: str) -> None:
    """Delete OAuth state from Redis."""
    async with aioredis.Redis(connection_pool=async_redis_pool) as client:
        await client.delete(f"{OAUTH_STATE_PREFIX}{state}")


# Analysis progress Pub/Sub
ANALYSIS_PROGRESS_PREFIX = "analysis:progress:"


def get_analysis_channel(analysis_id: str) -> str:
    """Get Redis channel name for analysis progress."""
    return f"{ANALYSIS_PROGRESS_PREFIX}{analysis_id}"


# State storage key for last progress (for late SSE subscribers)
ANALYSIS_STATE_PREFIX = "analysis:state:"
ANALYSIS_STATE_TTL = 3600  # 1 hour


def get_analysis_state_key(analysis_id: str) -> str:
    """Get Redis key for storing last analysis progress state."""
    return f"{ANALYSIS_STATE_PREFIX}{analysis_id}"


def publish_analysis_progress(
    analysis_id: str,
    stage: str,
    progress: int,
    message: str | None = None,
    status: str = "running",
    vci_score: float | None = None,
) -> None:
    """Publish analysis progress to Redis channel and store last state (sync, for Celery).
    
    This function does two things:
    1. Publishes to Pub/Sub channel for real-time SSE streaming
    2. Stores the last state in Redis so late subscribers can get current progress
    
    Uses connection pool to prevent connection leaks.
    """
    with get_sync_redis_context() as redis_client:
        channel = get_analysis_channel(analysis_id)
        state_key = get_analysis_state_key(analysis_id)
        
        payload_dict = {
            "analysis_id": analysis_id,
            "stage": stage,
            "progress": progress,
            "message": message,
            "status": status,
        }
        if vci_score is not None:
            payload_dict["vci_score"] = vci_score
        
        payload = json.dumps(payload_dict)
        
        # Store last state for late subscribers (with TTL)
        redis_client.setex(state_key, ANALYSIS_STATE_TTL, payload)
        
        # Publish for real-time updates
        redis_client.publish(channel, payload)
        logger.debug(f"Published progress to {channel}: {stage} {progress}%")


async def get_analysis_last_state(analysis_id: str) -> str | None:
    """Get the last stored analysis progress state (async, for FastAPI).
    
    Returns JSON string of last progress update, or None if not found.
    """
    async with aioredis.Redis(connection_pool=async_redis_pool) as client:
        state_key = get_analysis_state_key(analysis_id)
        result = await client.get(state_key)
        return str(result) if result else None


async def subscribe_analysis_progress(analysis_id: str, timeout_seconds: int = 600):
    """
    Subscribe to analysis progress updates (async generator for SSE).
    
    Yields JSON-encoded progress updates.
    
    Args:
        analysis_id: The analysis ID to subscribe to
        timeout_seconds: Max time to wait for updates (default 10 minutes)
    
    Note: Includes keepalive pings every 30 seconds to detect dead connections.
    """
    import asyncio
    
    client = aioredis.Redis(connection_pool=async_redis_pool)
    pubsub = client.pubsub()
    channel = get_analysis_channel(analysis_id)
    
    start_time = asyncio.get_event_loop().time()
    last_message_time = start_time
    keepalive_interval = 30  # Send keepalive every 30 seconds
    
    try:
        await pubsub.subscribe(channel)
        logger.info(f"Subscribed to channel: {channel}")
        
        while True:
            current_time = asyncio.get_event_loop().time()
            
            # Check overall timeout
            if current_time - start_time > timeout_seconds:
                logger.warning(f"Analysis {analysis_id} subscription timed out after {timeout_seconds}s")
                # Send timeout message to client
                timeout_data = json.dumps({
                    "analysis_id": analysis_id,
                    "stage": "timeout",
                    "progress": 0,
                    "message": "Connection timed out. Refresh to check status.",
                    "status": "failed",
                })
                yield timeout_data
                break
            
            # Calculate time until next keepalive
            time_since_last = current_time - last_message_time
            wait_timeout = max(0.1, keepalive_interval - time_since_last)
            
            try:
                # Wait for message with timeout
                message = await asyncio.wait_for(
                    pubsub.get_message(ignore_subscribe_messages=True, timeout=wait_timeout),
                    timeout=wait_timeout + 1
                )
                
                if message and message["type"] == "message":
                    last_message_time = asyncio.get_event_loop().time()
                    data = message["data"]
                    if isinstance(data, bytes):
                        data = data.decode("utf-8")
                    yield data
                    
                    # Check if analysis completed or failed
                    try:
                        parsed = json.loads(data)
                        if parsed.get("status") in ("completed", "failed"):
                            logger.info(f"Analysis {analysis_id} finished with status: {parsed.get('status')}")
                            return
                    except json.JSONDecodeError:
                        pass
                        
                elif current_time - last_message_time >= keepalive_interval:
                    # Send keepalive ping (SSE comment)
                    last_message_time = current_time
                    # Note: We yield a comment that the SSE parser will ignore
                    # This keeps the connection alive through proxies
                    yield ": keepalive\n"
                    
            except asyncio.TimeoutError:
                # No message received, check if we need keepalive
                if current_time - last_message_time >= keepalive_interval:
                    last_message_time = current_time
                    yield ": keepalive\n"
                continue
                
    finally:
        await pubsub.unsubscribe(channel)
        await pubsub.aclose()
        await client.aclose()


async def subscribe_to_channel(channel: str):
    """
    Generic subscribe to Redis Pub/Sub channel (async generator for SSE).
    
    Args:
        channel: Redis channel name to subscribe to
        
    Yields:
        JSON-encoded messages from the channel
    """
    client = aioredis.Redis(connection_pool=async_redis_pool)
    pubsub = client.pubsub()
    
    try:
        await pubsub.subscribe(channel)
        logger.info(f"Subscribed to channel: {channel}")
        
        async for message in pubsub.listen():
            if message["type"] == "message":
                data = message["data"]
                if isinstance(data, bytes):
                    data = data.decode("utf-8")
                yield data
    finally:
        await pubsub.unsubscribe(channel)
        await pubsub.aclose()
        await client.aclose()


# =============================================================================
# Embedding Progress Tracking
# =============================================================================

EMBEDDING_PROGRESS_PREFIX = "embedding:progress:"
EMBEDDING_STATE_PREFIX = "embedding:state:"
EMBEDDING_STATE_TTL = 3600  # 1 hour


def get_embedding_channel(repository_id: str) -> str:
    """Get Redis channel name for embedding progress."""
    return f"{EMBEDDING_PROGRESS_PREFIX}{repository_id}"


def get_embedding_state_key(repository_id: str) -> str:
    """Get Redis key for storing embedding progress state."""
    return f"{EMBEDDING_STATE_PREFIX}{repository_id}"


def publish_embedding_progress(
    repository_id: str,
    stage: str,
    progress: int,
    message: str | None = None,
    status: str = "running",
    chunks_processed: int = 0,
    vectors_stored: int = 0,
) -> None:
    """Publish embedding progress to Redis channel and store state.
    
    Used by embeddings worker to report progress.
    """
    with get_sync_redis_context() as redis_client:
        channel = get_embedding_channel(repository_id)
        state_key = get_embedding_state_key(repository_id)
        
        payload_dict = {
            "repository_id": repository_id,
            "stage": stage,
            "progress": progress,
            "message": message,
            "status": status,
            "chunks_processed": chunks_processed,
            "vectors_stored": vectors_stored,
        }
        
        payload = json.dumps(payload_dict)
        
        # Store state for polling/late subscribers
        redis_client.setex(state_key, EMBEDDING_STATE_TTL, payload)
        
        # Publish for real-time updates
        redis_client.publish(channel, payload)
        logger.debug(f"Published embedding progress: {stage} {progress}%")


async def get_embedding_state(repository_id: str) -> dict | None:
    """Get current embedding progress state (async, for FastAPI).
    
    Returns dict with progress info, or None if no embedding in progress.
    """
    async with aioredis.Redis(connection_pool=async_redis_pool) as client:
        state_key = get_embedding_state_key(repository_id)
        result = await client.get(state_key)
        if result:
            return json.loads(result)
        return None


async def subscribe_embedding_progress(repository_id: str, timeout_seconds: int = 300):
    """
    Subscribe to embedding progress updates (async generator for SSE).
    
    Yields JSON-encoded progress updates.
    """
    import asyncio
    
    client = aioredis.Redis(connection_pool=async_redis_pool)
    pubsub = client.pubsub()
    channel = get_embedding_channel(repository_id)
    
    start_time = asyncio.get_event_loop().time()
    
    try:
        await pubsub.subscribe(channel)
        logger.info(f"Subscribed to embedding channel: {channel}")
        
        while True:
            current_time = asyncio.get_event_loop().time()
            
            if current_time - start_time > timeout_seconds:
                yield json.dumps({
                    "repository_id": repository_id,
                    "stage": "timeout",
                    "status": "timeout",
                    "message": "Embedding progress timed out",
                })
                break
            
            try:
                message = await asyncio.wait_for(
                    pubsub.get_message(ignore_subscribe_messages=True, timeout=5.0),
                    timeout=6.0
                )
                
                if message and message["type"] == "message":
                    data = message["data"]
                    if isinstance(data, bytes):
                        data = data.decode("utf-8")
                    yield data
                    
                    # Check if completed or failed
                    try:
                        parsed = json.loads(data)
                        if parsed.get("status") in ("completed", "failed", "error"):
                            return
                    except json.JSONDecodeError:
                        pass
                        
            except asyncio.TimeoutError:
                continue
                
    finally:
        await pubsub.unsubscribe(channel)
        await pubsub.aclose()
        await client.aclose()


# =============================================================================
# Playground Scan Storage (for multi-worker scalability)
# =============================================================================

PLAYGROUND_SCAN_PREFIX = "playground:scan:"
PLAYGROUND_SCAN_TTL = 3600  # 1 hour


def store_playground_scan(scan_id: str, data: dict) -> None:
    """Store playground scan state in Redis.
    
    Args:
        scan_id: Unique scan identifier
        data: Scan state dict (will be JSON serialized)
    """
    with get_sync_redis_context() as client:
        client.setex(
            f"{PLAYGROUND_SCAN_PREFIX}{scan_id}",
            PLAYGROUND_SCAN_TTL,
            json.dumps(data),
        )


def get_playground_scan(scan_id: str) -> dict | None:
    """Get playground scan state from Redis.
    
    Args:
        scan_id: Unique scan identifier
        
    Returns:
        Scan state dict or None if not found
    """
    with get_sync_redis_context() as client:
        result = client.get(f"{PLAYGROUND_SCAN_PREFIX}{scan_id}")
        return json.loads(result) if result else None


def update_playground_scan(scan_id: str, updates: dict) -> None:
    """Update playground scan state (merge with existing).
    
    Args:
        scan_id: Unique scan identifier
        updates: Dict of fields to update/add
    """
    with get_sync_redis_context() as client:
        key = f"{PLAYGROUND_SCAN_PREFIX}{scan_id}"
        existing = client.get(key)
        if existing:
            data = json.loads(existing)
            data.update(updates)
            client.setex(key, PLAYGROUND_SCAN_TTL, json.dumps(data))


def check_playground_rate_limit(client_ip: str, max_requests: int = 5) -> bool:
    """Check if client has exceeded playground rate limit.
    
    Args:
        client_ip: Client IP address
        max_requests: Maximum requests per hour (default 5)
        
    Returns:
        True if under limit, False if exceeded
    """
    with get_sync_redis_context() as client:
        key = f"playground:rate:{client_ip}"
        
        current = client.get(key)
        if current and int(current) >= max_requests:
            return False
        
        pipe = client.pipeline()
        pipe.incr(key)
        pipe.expire(key, 3600)  # 1 hour TTL
        pipe.execute()
        
        return True
