"""Unit tests for VectorStoreService.

Tests:
- Filter building (repo-only vs repo+commit)
- Deterministic ID hashing (stable_int64_hash)
- Ref->sha resolution behavior

**Feature: commit-aware-rag**
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest
from qdrant_client.models import Filter

from app.services.vector_store import (
    _SHA40_RE,
    RefResolution,
    VectorStoreService,
    normalize_ref,
    stable_int64_hash,
)

# -----------------------------------------------------------------------------
# Tests for stable_int64_hash
# -----------------------------------------------------------------------------

class TestStableInt64Hash:
    """Test deterministic ID hashing."""

    def test_deterministic_same_input(self):
        """Same input should always produce same hash."""
        text = "repo1:abc123:src/main.py:10"
        h1 = stable_int64_hash(text)
        h2 = stable_int64_hash(text)
        assert h1 == h2

    def test_deterministic_across_calls(self):
        """Hash should be consistent across multiple calls."""
        inputs = [
            "repo1:commit1:file.py:1",
            "repo1:commit1:file.py:100",
            "repo2:commit1:file.py:1",
            "repo1:commit2:file.py:1",
        ]
        hashes1 = [stable_int64_hash(t) for t in inputs]
        hashes2 = [stable_int64_hash(t) for t in inputs]
        assert hashes1 == hashes2

    def test_different_inputs_different_hashes(self):
        """Different inputs should produce different hashes."""
        h1 = stable_int64_hash("repo1:commit1:file.py:1")
        h2 = stable_int64_hash("repo1:commit1:file.py:2")
        h3 = stable_int64_hash("repo2:commit1:file.py:1")
        assert h1 != h2
        assert h2 != h3
        assert h1 != h3

    def test_returns_int64_range(self):
        """Hash should be in valid int64 range."""
        texts = [
            "short",
            "a" * 1000,
            "unicode: 日本語テスト",
            "special: !@#$%^&*()",
        ]
        for text in texts:
            h = stable_int64_hash(text)
            assert isinstance(h, int)
            assert 0 <= h < (1 << 63)

    def test_commit_sha_in_key_changes_hash(self):
        """Including commit_sha in key should change the hash."""
        base = "repo1:file.py:10"
        with_commit_a = "repo1:abc123:file.py:10"
        with_commit_b = "repo1:def456:file.py:10"

        h_base = stable_int64_hash(base)
        h_commit_a = stable_int64_hash(with_commit_a)
        h_commit_b = stable_int64_hash(with_commit_b)

        assert h_base != h_commit_a
        assert h_base != h_commit_b
        assert h_commit_a != h_commit_b


# -----------------------------------------------------------------------------
# Tests for normalize_ref
# -----------------------------------------------------------------------------

class TestNormalizeRef:
    """Test ref normalization."""

    def test_none_returns_none(self):
        assert normalize_ref(None) is None

    def test_empty_string_returns_none(self):
        assert normalize_ref("") is None
        assert normalize_ref("   ") is None

    def test_strips_whitespace(self):
        assert normalize_ref("  main  ") == "main"

    def test_strips_refs_heads_prefix(self):
        assert normalize_ref("refs/heads/main") == "main"
        assert normalize_ref("refs/heads/feature/foo") == "feature/foo"

    def test_preserves_sha(self):
        sha = "abc123def456789012345678901234567890abcd"
        assert normalize_ref(sha) == sha

    def test_preserves_branch_name(self):
        assert normalize_ref("main") == "main"
        assert normalize_ref("feature/test") == "feature/test"


# -----------------------------------------------------------------------------
# Tests for SHA40 regex
# -----------------------------------------------------------------------------

class TestSha40Regex:
    """Test 40-hex SHA detection."""

    def test_valid_sha(self):
        assert _SHA40_RE.match("abc123def456789012345678901234567890abcd")
        assert _SHA40_RE.match("ABC123DEF456789012345678901234567890ABCD")
        assert _SHA40_RE.match("0" * 40)
        assert _SHA40_RE.match("f" * 40)

    def test_invalid_sha(self):
        assert not _SHA40_RE.match("abc123")  # too short
        assert not _SHA40_RE.match("a" * 39)  # too short
        assert not _SHA40_RE.match("a" * 41)  # too long
        assert not _SHA40_RE.match("ghij" + "a" * 36)  # invalid chars


# -----------------------------------------------------------------------------
# Tests for VectorStoreService.build_filter
# -----------------------------------------------------------------------------

class TestBuildFilter:
    """Test filter construction."""

    def test_repo_only_filter(self):
        """When commit_sha is None, filter only by repository_id."""
        f = VectorStoreService.build_filter(
            repository_id="repo-uuid-123",
            commit_sha=None,
        )
        assert isinstance(f, Filter)
        assert len(f.must) == 1
        assert f.must[0].key == "repository_id"
        assert f.must[0].match.value == "repo-uuid-123"
        assert f.must_not is None

    def test_repo_and_commit_filter(self):
        """When commit_sha is provided, filter by both."""
        f = VectorStoreService.build_filter(
            repository_id="repo-uuid-123",
            commit_sha="abc123def456789012345678901234567890abcd",
        )
        assert isinstance(f, Filter)
        assert len(f.must) == 2
        keys = {cond.key for cond in f.must}
        assert keys == {"repository_id", "commit_sha"}

    def test_with_file_path(self):
        """file_path should add another must condition."""
        f = VectorStoreService.build_filter(
            repository_id="repo-uuid-123",
            commit_sha="abc123def456789012345678901234567890abcd",
            file_path="src/main.py",
        )
        assert len(f.must) == 3
        keys = {cond.key for cond in f.must}
        assert keys == {"repository_id", "commit_sha", "file_path"}

    def test_with_exclude_file_path(self):
        """exclude_file_path should add a must_not condition."""
        f = VectorStoreService.build_filter(
            repository_id="repo-uuid-123",
            commit_sha="abc123def456789012345678901234567890abcd",
            exclude_file_path="test/test_main.py",
        )
        assert len(f.must) == 2
        assert f.must_not is not None
        assert len(f.must_not) == 1
        assert f.must_not[0].key == "file_path"
        assert f.must_not[0].match.value == "test/test_main.py"

    def test_uuid_converted_to_string(self):
        """UUID repository_id should be converted to string."""
        uuid_val = UUID("12345678-1234-5678-1234-567812345678")
        f = VectorStoreService.build_filter(
            repository_id=uuid_val,
            commit_sha=None,
        )
        assert f.must[0].match.value == "12345678-1234-5678-1234-567812345678"


# -----------------------------------------------------------------------------
# Tests for ref -> sha resolution
# -----------------------------------------------------------------------------

class TestRefResolution:
    """Test RefResolution dataclass."""

    def test_sha_passthrough(self):
        """40-hex SHA should be returned as-is with source='sha'."""
        sha = "abc123def456789012345678901234567890abcd"
        res = RefResolution(
            requested_ref=sha,
            resolved_commit_sha=sha,
            source="sha",
        )
        assert res.resolved_commit_sha == sha
        assert res.source == "sha"
        assert res.cached is False

    def test_cached_flag(self):
        res = RefResolution(
            requested_ref="main",
            resolved_commit_sha="abc123def456789012345678901234567890abcd",
            source="github_branch",
            cached=True,
        )
        assert res.cached is True


@pytest.mark.asyncio
class TestResolveRefToCommitSha:
    """Test resolve_ref_to_commit_sha_async method."""

    async def test_sha_passthrough_skips_db_and_github(self):
        """40-hex SHA should return immediately without DB/GitHub calls."""
        sha = "abc123def456789012345678901234567890abcd"
        vs = VectorStoreService(qdrant=MagicMock())

        # Mock the async session
        mock_db = MagicMock()
        mock_db.execute = AsyncMock()

        result = await vs.resolve_ref_to_commit_sha_async(
            db=mock_db,
            repository_id=UUID("12345678-1234-5678-1234-567812345678"),
            user_id=UUID("12345678-1234-5678-1234-567812345679"),
            ref=sha,
        )

        assert result.resolved_commit_sha == sha
        assert result.source == "sha"
        # DB should not be called for SHA passthrough
        mock_db.execute.assert_not_called()

    async def test_none_ref_uses_db_fallback(self):
        """None ref should fall back to latest analysis commit."""
        vs = VectorStoreService(qdrant=MagicMock())

        # Mock DB to return a commit SHA
        mock_db = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = "dbfallbacksha12345678901234567890ab"
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await vs.resolve_ref_to_commit_sha_async(
            db=mock_db,
            repository_id=UUID("12345678-1234-5678-1234-567812345678"),
            user_id=UUID("12345678-1234-5678-1234-567812345679"),
            ref=None,
        )

        assert result.resolved_commit_sha == "dbfallbacksha12345678901234567890ab"
        assert result.source == "db_latest_analysis"

    async def test_branch_resolves_via_github(self):
        """Branch name should be resolved via GitHub API."""
        vs = VectorStoreService(qdrant=MagicMock())

        mock_db = AsyncMock()
        # First call: get Repository
        # Second call: get User
        mock_repo = MagicMock()
        mock_repo.full_name = "owner/repo"
        mock_repo_result = MagicMock()
        mock_repo_result.scalar_one_or_none.return_value = mock_repo

        mock_user = MagicMock()
        mock_user.access_token_encrypted = "encrypted_token"
        mock_user_result = MagicMock()
        mock_user_result.scalar_one_or_none.return_value = mock_user

        call_count = 0

        async def mock_execute(query):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return mock_repo_result
            elif call_count == 2:
                return mock_user_result
            return MagicMock(scalar_one_or_none=MagicMock(return_value=None))

        mock_db.execute = mock_execute

        # Clear the ref cache to ensure we hit GitHub
        from app.services.vector_store import _ref_cache
        _ref_cache._data.clear()

        # Mock GitHub service - patch at the module where it's imported
        mock_github = MagicMock()
        mock_github.get_branch = AsyncMock(return_value={
            "commit": {"sha": "abcd1234567890abcdef1234567890abcdef1234"}
        })

        with patch("app.core.encryption.decrypt_token_or_none") as mock_decrypt, \
             patch("app.services.github.GitHubService") as mock_github_service:
            mock_decrypt.return_value = "decrypted_token"
            mock_github_service.return_value = mock_github

            result = await vs.resolve_ref_to_commit_sha_async(
                db=mock_db,
                repository_id=UUID("12345678-1234-5678-1234-567812345678"),
                user_id=UUID("12345678-1234-5678-1234-567812345679"),
                ref="main",
            )

        assert result.resolved_commit_sha == "abcd1234567890abcdef1234567890abcdef1234"
        assert result.source == "github_branch"


# -----------------------------------------------------------------------------
# Property tests (optional, if hypothesis is available)
# -----------------------------------------------------------------------------

try:
    from hypothesis import given
    from hypothesis import strategies as st

    class TestStableHashProperties:
        """Property-based tests for stable_int64_hash."""

        @given(st.text(min_size=1, max_size=1000))
        def test_always_returns_valid_int64(self, text: str):
            """Hash should always be in valid int64 range."""
            h = stable_int64_hash(text)
            assert isinstance(h, int)
            assert 0 <= h < (1 << 63)

        @given(st.text(min_size=1))
        def test_deterministic(self, text: str):
            """Same input should always produce same output."""
            assert stable_int64_hash(text) == stable_int64_hash(text)

except ImportError:
    # hypothesis not installed, skip property tests
    pass
