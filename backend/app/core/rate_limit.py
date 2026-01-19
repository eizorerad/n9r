"""Basic in-memory rate limiting utilities.

This is intentionally simple and dependency-free.

Notes:
- This is per-process memory. In multi-instance deployments, use a shared store
  (e.g., Redis) to enforce global limits.
- Keys should be stable and privacy-safe (user id preferred; fallback to IP).
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from fastapi import HTTPException, Request, status

from app.core.config import settings


@dataclass
class _Bucket:
    window_start: float
    count: int


# (key, window_seconds) -> bucket
_BUCKETS: dict[tuple[str, int], _Bucket] = {}


def _now() -> float:
    return time.time()


def _get_client_key(request: Request, user_id: str | None) -> str:
    if user_id:
        return f"user:{user_id}"
    # Best-effort IP extraction (works behind proxies if X-Forwarded-For is set)
    xff = request.headers.get("x-forwarded-for")
    if xff:
        ip = xff.split(",")[0].strip()
    else:
        ip = request.client.host if request.client else "unknown"
    return f"ip:{ip}"


def enforce_rate_limit(
    request: Request,
    *,
    user_id: str | None,
    limit_per_minute: int,
    scope: str,
) -> None:
    """Enforce a fixed-window rate limit.

    Raises:
        HTTPException(429) when exceeded.
    """
    if not settings.rate_limit_enabled:
        return

    window_seconds = 60
    key = f"{scope}:{_get_client_key(request, user_id)}"
    bucket_key = (key, window_seconds)

    now = _now()
    bucket = _BUCKETS.get(bucket_key)
    if bucket is None or now - bucket.window_start >= window_seconds:
        _BUCKETS[bucket_key] = _Bucket(window_start=now, count=1)
        return

    if bucket.count >= limit_per_minute:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded",
            headers={
                "Retry-After": str(int(window_seconds - (now - bucket.window_start))),
            },
        )

    bucket.count += 1
