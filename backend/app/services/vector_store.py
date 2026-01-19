"""VectorStoreService: single-source-of-truth for Qdrant access + commit-aware filtering.

Goal:
- Centralize how we build Qdrant filters (repository_id + optional commit_sha + optional file_path)
- Provide ref -> commit SHA resolution, with safe fallbacks
- Provide reusable Qdrant operations for chat RAG, semantic endpoints, and cluster analysis

Notes:
- This module is intentionally *sync-friendly*: Qdrant client is sync.
- DB access may be either AsyncSession (FastAPI) or Session (Celery/sync paths).
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol
from uuid import UUID

from qdrant_client import QdrantClient
from qdrant_client.models import (
    FieldCondition,
    Filter,
    FilterSelector,
    MatchValue,
)

from app.core.config import settings

logger = logging.getLogger(__name__)

COLLECTION_NAME = "code_embeddings"

_SHA40_RE = re.compile(r"^[0-9a-f]{40}$", re.IGNORECASE)


class _HasExecute(Protocol):
    """Protocol for both SQLAlchemy Session and AsyncSession."""

    # AsyncSession.execute is async; Session.execute is sync.
    # We keep two code paths.


@dataclass(frozen=True)
class RefResolution:
    requested_ref: str | None
    resolved_commit_sha: str | None
    source: str  # "sha", "github_branch", "db_latest_analysis", "none"
    cached: bool = False


class _InMemoryRefCache:
    """Very small TTL cache to reduce GitHub API pressure.

    This is intentionally per-process. For multi-worker deployments you may
    want to replace with Redis.
    """

    def __init__(self, ttl_seconds: int = 300, max_size: int = 4096):
        self._ttl = timedelta(seconds=max(30, ttl_seconds))
        self._max_size = max(128, max_size)
        self._data: dict[tuple[str, str], tuple[str, datetime]] = {}

    def get(self, repository_id: str, ref: str) -> str | None:
        key = (repository_id, ref)
        hit = self._data.get(key)
        if not hit:
            return None
        value, expires_at = hit
        if datetime.now(UTC) >= expires_at:
            self._data.pop(key, None)
            return None
        return value

    def set(self, repository_id: str, ref: str, sha: str) -> None:
        # naive size control
        if len(self._data) >= self._max_size:
            # drop oldest-ish by iteration order (good enough)
            for k in list(self._data.keys())[: max(1, self._max_size // 10)]:
                self._data.pop(k, None)
        self._data[(repository_id, ref)] = (sha, datetime.now(UTC) + self._ttl)


_ref_cache = _InMemoryRefCache(ttl_seconds=300)


def stable_int64_hash(text: str) -> int:
    """Deterministic 64-bit integer ID.

    We cannot use Python's built-in hash() for point IDs because it is salted per
    process (PYTHONHASHSEED) and therefore not stable across restarts.

    This returns a *signed* int64 in the range [0, 2**63-1].
    """

    digest = hashlib.blake2b(text.encode("utf-8"), digest_size=8).digest()  # 64-bit
    unsigned = int.from_bytes(digest, byteorder="big", signed=False)
    return unsigned & ((1 << 63) - 1)


def get_qdrant_client() -> QdrantClient:
    return QdrantClient(
        host=settings.qdrant_host,
        port=settings.qdrant_port,
        timeout=settings.qdrant_timeout,
    )


def normalize_ref(ref: str | None) -> str | None:
    """Normalize common git ref formats.

    Supported:
    - 40-hex SHA
    - branch name
    - refs/heads/<branch> (GitHub push payload style)

    Not supported (for now): tags, PR refs.
    """

    if not ref:
        return None
    r = ref.strip()
    if not r:
        return None

    # strip common GitHub ref prefix
    if r.startswith("refs/heads/"):
        return r[len("refs/heads/") :]

    return r


class VectorStoreService:
    """Shared service for commit-aware vector operations."""

    def __init__(
        self,
        qdrant: QdrantClient | None = None,
        collection_name: str = COLLECTION_NAME,
    ):
        self.qdrant = qdrant or get_qdrant_client()
        self.collection_name = collection_name

    # ---------------------------------------------------------------------
    # Filters
    # ---------------------------------------------------------------------

    @staticmethod
    def build_filter(
        repository_id: str | UUID,
        commit_sha: str | None,
        *,
        file_path: str | None = None,
        exclude_file_path: str | None = None,
    ) -> Filter:
        rid = str(repository_id)

        must: list[FieldCondition] = [
            FieldCondition(key="repository_id", match=MatchValue(value=rid))
        ]
        if commit_sha:
            must.append(FieldCondition(key="commit_sha", match=MatchValue(value=commit_sha)))

        if file_path:
            must.append(FieldCondition(key="file_path", match=MatchValue(value=file_path)))

        must_not: list[FieldCondition] = []
        if exclude_file_path:
            must_not.append(FieldCondition(key="file_path", match=MatchValue(value=exclude_file_path)))

        return Filter(must=must, must_not=must_not or None)

    # ---------------------------------------------------------------------
    # Commit selection / ref resolution
    # ---------------------------------------------------------------------

    async def get_default_commit_sha_async(self, db, repository_id: UUID) -> str | None:
        """Return latest completed analysis commit for repo (AsyncSession)."""
        from sqlalchemy import select

        from app.models.analysis import Analysis

        result = await db.execute(
            select(Analysis.commit_sha)
            .where(
                Analysis.repository_id == repository_id,
                Analysis.status == "completed",
            )
            .order_by(Analysis.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    def get_default_commit_sha_sync(self, db, repository_id: UUID) -> str | None:
        """Return latest completed analysis commit for repo (Session)."""
        from sqlalchemy import select

        from app.models.analysis import Analysis

        result = db.execute(
            select(Analysis.commit_sha)
            .where(
                Analysis.repository_id == repository_id,
                Analysis.status == "completed",
            )
            .order_by(Analysis.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def resolve_ref_to_commit_sha_async(
        self,
        *,
        db,
        repository_id: UUID,
        user_id: UUID,
        ref: str | None,
    ) -> RefResolution:
        """Resolve a ref (SHA or branch) to commit SHA.

        Resolution priority:
        1) If ref is 40-hex SHA: return it
        2) If ref is branch name: GitHub API -> sha (requires user token)
        3) Fallback: latest completed analysis commit sha
        4) Else: None

        Args:
            db: AsyncSession
            repository_id: repo UUID
            user_id: used to retrieve GitHub token + repo full_name
            ref: commit SHA or branch name
        """
        from sqlalchemy import select

        from app.core.encryption import decrypt_token_or_none
        from app.models.repository import Repository
        from app.models.user import User
        from app.services.github import GitHubService

        normalized = normalize_ref(ref)
        if not normalized:
            # fallback to latest analysis
            sha = await self.get_default_commit_sha_async(db, repository_id)
            return RefResolution(requested_ref=ref, resolved_commit_sha=sha, source="db_latest_analysis" if sha else "none")

        if _SHA40_RE.match(normalized):
            return RefResolution(requested_ref=ref, resolved_commit_sha=normalized, source="sha")

        # Cache check
        cached_sha = _ref_cache.get(str(repository_id), normalized)
        if cached_sha:
            return RefResolution(requested_ref=ref, resolved_commit_sha=cached_sha, source="github_branch", cached=True)

        # Fetch repo + user token
        result = await db.execute(
            select(Repository).where(Repository.id == repository_id)
        )
        repo = result.scalar_one_or_none()
        if not repo:
            sha = await self.get_default_commit_sha_async(db, repository_id)
            return RefResolution(requested_ref=ref, resolved_commit_sha=sha, source="db_latest_analysis" if sha else "none")

        user_result = await db.execute(select(User).where(User.id == user_id))
        user = user_result.scalar_one_or_none()
        token = decrypt_token_or_none(user.access_token_encrypted) if user else None

        if token:
            try:
                github = GitHubService(token)
                owner, repo_name = repo.full_name.split("/")
                branch_info = await github.get_branch(owner, repo_name, normalized)
                sha = (branch_info.get("commit") or {}).get("sha")
                if sha and _SHA40_RE.match(sha):
                    _ref_cache.set(str(repository_id), normalized, sha)
                    return RefResolution(requested_ref=ref, resolved_commit_sha=sha, source="github_branch")
            except Exception as e:
                logger.info(f"ref->sha resolution via GitHub failed (repo={repository_id}, ref={normalized}): {e}")

        sha = await self.get_default_commit_sha_async(db, repository_id)
        return RefResolution(requested_ref=ref, resolved_commit_sha=sha, source="db_latest_analysis" if sha else "none")

    # ---------------------------------------------------------------------
    # Vector operations (with telemetry)
    # ---------------------------------------------------------------------

    def query_similar_chunks(
        self,
        *,
        repository_id: str | UUID,
        commit_sha: str | None,
        query_vector: list[float],
        limit: int = 10,
        file_path: str | None = None,
        exclude_file_path: str | None = None,
    ):
        q_filter = self.build_filter(
            repository_id=repository_id,
            commit_sha=commit_sha,
            file_path=file_path,
            exclude_file_path=exclude_file_path,
        )

        points = self.qdrant.query_points(
            collection_name=self.collection_name,
            query=query_vector,
            query_filter=q_filter,
            limit=limit,
        ).points

        # Telemetry: log query details
        avg_score = sum(p.score for p in points) / len(points) if points else 0.0
        filter_mode = "repo+commit" if commit_sha else "repo_only"
        logger.info(
            "vector_query",
            extra={
                "telemetry": True,
                "operation": "query_similar_chunks",
                "repository_id": str(repository_id),
                "commit_sha": commit_sha[:8] if commit_sha else None,
                "filter_mode": filter_mode,
                "limit": limit,
                "hits": len(points),
                "avg_score": round(avg_score, 4),
            },
        )

        return points

    def scroll_vectors(
        self,
        *,
        repository_id: str | UUID,
        commit_sha: str | None,
        limit: int = 100,
        offset: int | str | None = None,
        with_vectors: bool = True,
    ):
        q_filter = self.build_filter(
            repository_id=repository_id,
            commit_sha=commit_sha,
        )
        results, next_offset = self.qdrant.scroll(
            collection_name=self.collection_name,
            scroll_filter=q_filter,
            limit=limit,
            offset=offset,
            with_vectors=with_vectors,
        )

        # Telemetry: log scroll details
        filter_mode = "repo+commit" if commit_sha else "repo_only"
        logger.debug(
            "vector_scroll",
            extra={
                "telemetry": True,
                "operation": "scroll_vectors",
                "repository_id": str(repository_id),
                "commit_sha": commit_sha[:8] if commit_sha else None,
                "filter_mode": filter_mode,
                "limit": limit,
                "returned": len(results),
                "has_more": next_offset is not None,
            },
        )

        return results, next_offset

    def count_vectors(
        self,
        *,
        repository_id: str | UUID,
        commit_sha: str | None,
    ) -> int:
        q_filter = self.build_filter(
            repository_id=repository_id,
            commit_sha=commit_sha,
        )
        result = self.qdrant.count(
            collection_name=self.collection_name,
            count_filter=q_filter,
        )
        count = int(result.count or 0)

        # Telemetry: log count details
        filter_mode = "repo+commit" if commit_sha else "repo_only"
        logger.debug(
            "vector_count",
            extra={
                "telemetry": True,
                "operation": "count_vectors",
                "repository_id": str(repository_id),
                "commit_sha": commit_sha[:8] if commit_sha else None,
                "filter_mode": filter_mode,
                "count": count,
            },
        )

        return count

    def delete_vectors(
        self,
        *,
        repository_id: str | UUID,
        commit_sha: str,
    ) -> int:
        """Delete vectors for a specific (repository, commit) pair.

        Returns:
            Number of vectors deleted (counted before deletion)
        """
        if not commit_sha:
            raise ValueError("commit_sha is required for delete_vectors")

        # Count before deletion for telemetry
        count_before = self.count_vectors(repository_id=repository_id, commit_sha=commit_sha)

        q_filter = self.build_filter(
            repository_id=repository_id,
            commit_sha=commit_sha,
        )
        self.qdrant.delete(
            collection_name=self.collection_name,
            points_selector=FilterSelector(filter=q_filter),
        )

        # Telemetry: log delete details
        logger.info(
            "vector_delete",
            extra={
                "telemetry": True,
                "operation": "delete_vectors",
                "repository_id": str(repository_id),
                "commit_sha": commit_sha[:8],
                "vectors_deleted": count_before,
            },
        )

        return count_before

    # ---------------------------------------------------------------------
    # Telemetry helper for ref resolution logging
    # ---------------------------------------------------------------------

    def log_ref_resolution(self, resolution: RefResolution, repository_id: UUID) -> None:
        """Log ref resolution result for telemetry."""
        logger.info(
            "ref_resolution",
            extra={
                "telemetry": True,
                "operation": "resolve_ref_to_commit_sha",
                "repository_id": str(repository_id),
                "requested_ref": resolution.requested_ref,
                "resolved_sha": resolution.resolved_commit_sha[:8] if resolution.resolved_commit_sha else None,
                "source": resolution.source,
                "cached": resolution.cached,
            },
        )
