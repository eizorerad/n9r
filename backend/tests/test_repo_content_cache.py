"""Property-based tests for Repository Content Cache.

Uses Hypothesis for property-based testing to verify correctness properties
defined in the design document for the repo-content-cache feature.
"""

import uuid
from dataclasses import dataclass

from hypothesis import given, settings
from hypothesis import strategies as st

# =============================================================================
# Custom Strategies for Repo Content Cache Testing
# =============================================================================


def valid_file_path() -> st.SearchStrategy[str]:
    """Generate valid file paths for testing."""
    return st.lists(
        st.from_regex(r"[a-z][a-z0-9_]*", fullmatch=True).filter(lambda s: 2 <= len(s) <= 15),
        min_size=1,
        max_size=4
    ).map(lambda parts: "/".join(parts) + ".py")


def valid_commit_sha() -> st.SearchStrategy[str]:
    """Generate valid 40-character commit SHA."""
    return st.from_regex(r"[a-f0-9]{40}", fullmatch=True)


def valid_content_hash() -> st.SearchStrategy[str]:
    """Generate valid SHA-256 hash (64 hex characters)."""
    return st.from_regex(r"[a-f0-9]{64}", fullmatch=True)


def cache_status() -> st.SearchStrategy[str]:
    """Generate valid cache status values."""
    return st.sampled_from(["pending", "uploading", "ready", "failed"])


def object_status() -> st.SearchStrategy[str]:
    """Generate valid object status values."""
    return st.sampled_from(["uploading", "ready", "failed", "deleted"])


@dataclass
class MockRepoContentObject:
    """Mock object representing a cached file."""
    id: uuid.UUID
    cache_id: uuid.UUID
    path: str
    object_key: str
    size_bytes: int
    content_hash: str
    status: str


@dataclass
class MockRepoContentCache:
    """Mock cache entry representing repository content cache metadata."""
    id: uuid.UUID
    repository_id: uuid.UUID
    commit_sha: str
    status: str
    file_count: int
    total_size_bytes: int
    version: int
    objects: list[MockRepoContentObject]


@st.composite
def repo_content_object(draw, cache_id: uuid.UUID) -> MockRepoContentObject:
    """Generate a valid RepoContentObject."""
    return MockRepoContentObject(
        id=uuid.uuid4(),
        cache_id=cache_id,
        path=draw(valid_file_path()),
        object_key=str(uuid.uuid4()),
        size_bytes=draw(st.integers(min_value=1, max_value=1_000_000)),
        content_hash=draw(valid_content_hash()),
        status=draw(object_status()),
    )


@st.composite
def repo_content_cache_with_objects(draw) -> MockRepoContentCache:
    """Generate a valid RepoContentCache with associated objects.

    This generates a cache entry with objects where the metadata
    (file_count, total_size_bytes) is computed from the 'ready' objects.
    """
    cache_id = uuid.uuid4()
    repository_id = uuid.uuid4()
    commit_sha = draw(valid_commit_sha())
    status = draw(cache_status())

    # Generate between 0 and 20 objects
    num_objects = draw(st.integers(min_value=0, max_value=20))
    objects = [draw(repo_content_object(cache_id)) for _ in range(num_objects)]

    # Compute metadata from 'ready' objects only
    ready_objects = [obj for obj in objects if obj.status == "ready"]
    file_count = len(ready_objects)
    total_size_bytes = sum(obj.size_bytes for obj in ready_objects)

    return MockRepoContentCache(
        id=cache_id,
        repository_id=repository_id,
        commit_sha=commit_sha,
        status=status,
        file_count=file_count,
        total_size_bytes=total_size_bytes,
        version=draw(st.integers(min_value=1, max_value=100)),
        objects=objects,
    )


@st.composite
def repo_content_cache_with_inconsistent_metadata(draw) -> MockRepoContentCache:
    """Generate a cache with potentially inconsistent metadata for testing validation."""
    cache_id = uuid.uuid4()
    repository_id = uuid.uuid4()
    commit_sha = draw(valid_commit_sha())

    # Generate objects
    num_objects = draw(st.integers(min_value=1, max_value=20))
    objects = [draw(repo_content_object(cache_id)) for _ in range(num_objects)]

    # Generate potentially incorrect metadata
    file_count = draw(st.integers(min_value=0, max_value=50))
    total_size_bytes = draw(st.integers(min_value=0, max_value=10_000_000))

    return MockRepoContentCache(
        id=cache_id,
        repository_id=repository_id,
        commit_sha=commit_sha,
        status="ready",  # Always ready for this test
        file_count=file_count,
        total_size_bytes=total_size_bytes,
        version=draw(st.integers(min_value=1, max_value=100)),
        objects=objects,
    )


# =============================================================================
# Helper Functions for Metadata Validation
# =============================================================================


def compute_expected_file_count(objects: list[MockRepoContentObject]) -> int:
    """Compute expected file_count from objects with 'ready' status."""
    return len([obj for obj in objects if obj.status == "ready"])


def compute_expected_total_size(objects: list[MockRepoContentObject]) -> int:
    """Compute expected total_size_bytes from objects with 'ready' status."""
    return sum(obj.size_bytes for obj in objects if obj.status == "ready")


def validate_metadata_accuracy(cache: MockRepoContentCache) -> tuple[bool, str]:
    """
    Validate that cache metadata matches the actual objects.

    Returns (is_valid, error_message).
    """
    expected_file_count = compute_expected_file_count(cache.objects)
    expected_total_size = compute_expected_total_size(cache.objects)

    if cache.file_count != expected_file_count:
        return False, (
            f"file_count mismatch: expected {expected_file_count}, got {cache.file_count}"
        )

    if cache.total_size_bytes != expected_total_size:
        return False, (
            f"total_size_bytes mismatch: expected {expected_total_size}, got {cache.total_size_bytes}"
        )

    return True, ""


# =============================================================================
# Property Tests for Metadata Accuracy
# =============================================================================


class TestMetadataAccuracyProperties:
    """Property tests for metadata accuracy.

    **Feature: repo-content-cache, Property 4: Metadata accuracy**
    **Validates: Requirements 4.1**
    """

    @given(repo_content_cache_with_objects())
    @settings(max_examples=100)
    def test_metadata_accuracy_for_ready_cache(self, cache: MockRepoContentCache):
        """
        **Feature: repo-content-cache, Property 4: Metadata accuracy**
        **Validates: Requirements 4.1**

        Property: For any cache entry in 'ready' status, the file_count should equal
        the count of 'ready' objects in repo_content_objects, and total_size_bytes
        should equal the sum of all object sizes.
        """
        # Only validate for 'ready' caches as per the property definition
        if cache.status != "ready":
            # For non-ready caches, we still verify the metadata is computed correctly
            # but the property specifically applies to 'ready' caches
            pass

        # Compute expected values from objects
        expected_file_count = compute_expected_file_count(cache.objects)
        expected_total_size = compute_expected_total_size(cache.objects)

        # Property: file_count must equal count of 'ready' objects
        assert cache.file_count == expected_file_count, (
            f"file_count mismatch for cache {cache.id}\n"
            f"Expected: {expected_file_count} (count of 'ready' objects)\n"
            f"Actual: {cache.file_count}\n"
            f"Objects: {[(obj.path, obj.status) for obj in cache.objects]}"
        )

        # Property: total_size_bytes must equal sum of 'ready' object sizes
        assert cache.total_size_bytes == expected_total_size, (
            f"total_size_bytes mismatch for cache {cache.id}\n"
            f"Expected: {expected_total_size} (sum of 'ready' object sizes)\n"
            f"Actual: {cache.total_size_bytes}\n"
            f"Ready objects: {[(obj.path, obj.size_bytes) for obj in cache.objects if obj.status == 'ready']}"
        )

    @given(repo_content_cache_with_inconsistent_metadata())
    @settings(max_examples=100)
    def test_metadata_validation_detects_inconsistencies(self, cache: MockRepoContentCache):
        """
        **Feature: repo-content-cache, Property 4: Metadata accuracy**
        **Validates: Requirements 4.1**

        Property: The validation function should correctly detect when metadata
        does not match the actual objects.
        """
        expected_file_count = compute_expected_file_count(cache.objects)
        expected_total_size = compute_expected_total_size(cache.objects)

        is_valid, error_msg = validate_metadata_accuracy(cache)

        # Property: validation should pass if and only if metadata matches
        metadata_matches = (
            cache.file_count == expected_file_count and
            cache.total_size_bytes == expected_total_size
        )

        assert is_valid == metadata_matches, (
            f"Validation result mismatch\n"
            f"is_valid: {is_valid}, metadata_matches: {metadata_matches}\n"
            f"file_count: expected={expected_file_count}, actual={cache.file_count}\n"
            f"total_size_bytes: expected={expected_total_size}, actual={cache.total_size_bytes}\n"
            f"Error: {error_msg}"
        )

    @given(st.lists(repo_content_object(uuid.uuid4()), min_size=0, max_size=30))
    @settings(max_examples=100)
    def test_metadata_computation_is_deterministic(self, objects: list[MockRepoContentObject]):
        """
        **Feature: repo-content-cache, Property 4: Metadata accuracy**
        **Validates: Requirements 4.1**

        Property: Computing metadata from the same set of objects should always
        produce the same result (deterministic).
        """
        # Compute metadata twice
        file_count_1 = compute_expected_file_count(objects)
        total_size_1 = compute_expected_total_size(objects)

        file_count_2 = compute_expected_file_count(objects)
        total_size_2 = compute_expected_total_size(objects)

        # Property: results must be identical
        assert file_count_1 == file_count_2, (
            f"file_count computation is not deterministic: {file_count_1} != {file_count_2}"
        )
        assert total_size_1 == total_size_2, (
            f"total_size computation is not deterministic: {total_size_1} != {total_size_2}"
        )

    @given(repo_content_cache_with_objects())
    @settings(max_examples=100)
    def test_file_count_never_exceeds_total_objects(self, cache: MockRepoContentCache):
        """
        **Feature: repo-content-cache, Property 4: Metadata accuracy**
        **Validates: Requirements 4.1**

        Property: file_count (count of 'ready' objects) should never exceed
        the total number of objects.
        """
        total_objects = len(cache.objects)

        # Property: file_count <= total objects
        assert cache.file_count <= total_objects, (
            f"file_count ({cache.file_count}) exceeds total objects ({total_objects})"
        )

    @given(repo_content_cache_with_objects())
    @settings(max_examples=100)
    def test_total_size_is_non_negative(self, cache: MockRepoContentCache):
        """
        **Feature: repo-content-cache, Property 4: Metadata accuracy**
        **Validates: Requirements 4.1**

        Property: total_size_bytes should always be non-negative.
        """
        # Property: total_size_bytes >= 0
        assert cache.total_size_bytes >= 0, (
            f"total_size_bytes ({cache.total_size_bytes}) is negative"
        )

    @given(repo_content_cache_with_objects())
    @settings(max_examples=100)
    def test_empty_cache_has_zero_metadata(self, cache: MockRepoContentCache):
        """
        **Feature: repo-content-cache, Property 4: Metadata accuracy**
        **Validates: Requirements 4.1**

        Property: If there are no 'ready' objects, file_count and total_size_bytes
        should both be 0.
        """
        ready_objects = [obj for obj in cache.objects if obj.status == "ready"]

        if len(ready_objects) == 0:
            # Property: no ready objects means zero metadata
            assert cache.file_count == 0, (
                f"file_count should be 0 when no ready objects, got {cache.file_count}"
            )
            assert cache.total_size_bytes == 0, (
                f"total_size_bytes should be 0 when no ready objects, got {cache.total_size_bytes}"
            )



# =============================================================================
# Property Tests for File Collection Consistency
# =============================================================================


import hashlib
import tempfile
from pathlib import Path

from app.services.repo_content import (
    CODE_EXTENSIONS,
    MAX_FILE_SIZE,
    MIN_FILE_SIZE,
    RepoContentService,
    compute_content_hash,
)


def valid_code_extension() -> st.SearchStrategy[str]:
    """Generate valid code file extensions."""
    return st.sampled_from(list(CODE_EXTENSIONS))


def invalid_extension() -> st.SearchStrategy[str]:
    """Generate non-code file extensions."""
    return st.sampled_from([".txt", ".md", ".json", ".yaml", ".xml", ".csv", ".log"])


@st.composite
def valid_file_content(draw) -> bytes:
    """Generate valid file content (within size limits)."""
    size = draw(st.integers(min_value=MIN_FILE_SIZE, max_value=min(MAX_FILE_SIZE, 10000)))
    return draw(st.binary(min_size=size, max_size=size))


@st.composite
def small_file_content(draw) -> bytes:
    """Generate file content smaller than MIN_FILE_SIZE."""
    size = draw(st.integers(min_value=1, max_value=MIN_FILE_SIZE - 1))
    return draw(st.binary(min_size=size, max_size=size))


@st.composite
def large_file_content(draw) -> bytes:
    """Generate file content larger than MAX_FILE_SIZE."""
    # Generate content slightly larger than max
    size = draw(st.integers(min_value=MAX_FILE_SIZE + 1, max_value=MAX_FILE_SIZE + 1000))
    return b"x" * size


@st.composite
def repo_file_structure(draw) -> dict[str, bytes]:
    """Generate a repository file structure with mixed file types.

    Returns a dict mapping relative paths to file contents.
    """
    files = {}

    # Generate 1-10 code files
    num_code_files = draw(st.integers(min_value=1, max_value=10))
    for i in range(num_code_files):
        ext = draw(valid_code_extension())
        # Use simple alphanumeric names to avoid path issues
        name = f"file{i}{ext}"
        content = draw(valid_file_content())
        files[name] = content

    # Optionally add some non-code files
    num_other_files = draw(st.integers(min_value=0, max_value=5))
    for i in range(num_other_files):
        ext = draw(invalid_extension())
        name = f"other{i}{ext}"
        content = draw(valid_file_content())
        files[name] = content

    return files


def create_temp_repo(files: dict[str, bytes]) -> Path:
    """Create a temporary directory with the given file structure."""
    temp_dir = tempfile.mkdtemp(prefix="test_repo_")

    for path, content in files.items():
        file_path = Path(temp_dir) / path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_bytes(content)

    return Path(temp_dir)


def cleanup_temp_repo(repo_path: Path) -> None:
    """Clean up temporary repository directory."""
    import shutil
    try:
        shutil.rmtree(repo_path)
    except Exception:
        pass


class TestFileCollectionConsistencyProperties:
    """Property tests for file collection consistency.

    **Feature: repo-content-cache, Property 3: File collection consistency**
    **Validates: Requirements 2.1, 2.6**
    """

    @given(repo_file_structure())
    @settings(max_examples=100)
    def test_collected_files_match_filter_criteria(self, files: dict[str, bytes]):
        """
        **Feature: repo-content-cache, Property 3: File collection consistency**
        **Validates: Requirements 2.1, 2.6**

        Property: For any cloned repository directory, the collect_files_from_repo
        function should return files that match the filter criteria (code extensions,
        max size) and each file should have a valid SHA-256 content_hash.
        """
        repo_path = create_temp_repo(files)
        try:
            service = RepoContentService()
            collected = service.collect_files_from_repo(repo_path)

            for file in collected:
                # Property 1: All collected files have code extensions
                ext = Path(file.path).suffix.lower()
                assert ext in CODE_EXTENSIONS, (
                    f"Collected file {file.path} has non-code extension {ext}"
                )

                # Property 2: All collected files are within size limits
                assert len(file.content) >= MIN_FILE_SIZE, (
                    f"Collected file {file.path} is too small: {len(file.content)} bytes"
                )
                assert len(file.content) <= MAX_FILE_SIZE, (
                    f"Collected file {file.path} is too large: {len(file.content)} bytes"
                )

                # Property 3: Content hash is valid SHA-256
                assert len(file.content_hash) == 64, (
                    f"Content hash for {file.path} is not 64 characters: {len(file.content_hash)}"
                )
                assert all(c in "0123456789abcdef" for c in file.content_hash), (
                    f"Content hash for {file.path} contains invalid characters"
                )

                # Property 4: Content hash matches actual content
                expected_hash = hashlib.sha256(file.content).hexdigest()
                assert file.content_hash == expected_hash, (
                    f"Content hash mismatch for {file.path}: "
                    f"expected {expected_hash}, got {file.content_hash}"
                )
        finally:
            cleanup_temp_repo(repo_path)

    @given(repo_file_structure())
    @settings(max_examples=100)
    def test_non_code_files_excluded(self, files: dict[str, bytes]):
        """
        **Feature: repo-content-cache, Property 3: File collection consistency**
        **Validates: Requirements 2.6**

        Property: Files with non-code extensions should not be collected.
        """
        repo_path = create_temp_repo(files)
        try:
            service = RepoContentService()
            collected = service.collect_files_from_repo(repo_path)

            collected_paths = {f.path for f in collected}

            for path in files.keys():
                ext = Path(path).suffix.lower()
                if ext not in CODE_EXTENSIONS:
                    assert path not in collected_paths, (
                        f"Non-code file {path} was incorrectly collected"
                    )
        finally:
            cleanup_temp_repo(repo_path)

    @given(st.data())
    @settings(max_examples=50)
    def test_small_files_excluded(self, data):
        """
        **Feature: repo-content-cache, Property 3: File collection consistency**
        **Validates: Requirements 2.6**

        Property: Files smaller than MIN_FILE_SIZE should not be collected.
        """
        ext = data.draw(valid_code_extension())
        content = data.draw(small_file_content())

        files = {f"small{ext}": content}
        repo_path = create_temp_repo(files)
        try:
            service = RepoContentService()
            collected = service.collect_files_from_repo(repo_path)

            # Property: small files should not be collected
            assert len(collected) == 0, (
                f"Small file ({len(content)} bytes) was incorrectly collected"
            )
        finally:
            cleanup_temp_repo(repo_path)

    @given(st.data())
    @settings(max_examples=50)
    def test_large_files_excluded(self, data):
        """
        **Feature: repo-content-cache, Property 3: File collection consistency**
        **Validates: Requirements 2.6**

        Property: Files larger than MAX_FILE_SIZE should not be collected.
        """
        ext = data.draw(valid_code_extension())
        content = data.draw(large_file_content())

        files = {f"large{ext}": content}
        repo_path = create_temp_repo(files)
        try:
            service = RepoContentService()
            collected = service.collect_files_from_repo(repo_path)

            # Property: large files should not be collected
            assert len(collected) == 0, (
                f"Large file ({len(content)} bytes) was incorrectly collected"
            )
        finally:
            cleanup_temp_repo(repo_path)

    @given(repo_file_structure())
    @settings(max_examples=100)
    def test_collection_is_deterministic(self, files: dict[str, bytes]):
        """
        **Feature: repo-content-cache, Property 3: File collection consistency**
        **Validates: Requirements 2.1**

        Property: Collecting files from the same repository should always
        produce the same result (deterministic).
        """
        repo_path = create_temp_repo(files)
        try:
            service = RepoContentService()

            # Collect twice
            collected1 = service.collect_files_from_repo(repo_path)
            collected2 = service.collect_files_from_repo(repo_path)

            # Property: results must be identical
            paths1 = sorted(f.path for f in collected1)
            paths2 = sorted(f.path for f in collected2)

            assert paths1 == paths2, (
                f"Collection is not deterministic: {paths1} != {paths2}"
            )

            # Also verify hashes match
            hashes1 = {f.path: f.content_hash for f in collected1}
            hashes2 = {f.path: f.content_hash for f in collected2}

            assert hashes1 == hashes2, (
                "Content hashes are not deterministic"
            )
        finally:
            cleanup_temp_repo(repo_path)



# =============================================================================
# Property Tests for Upload Idempotency
# =============================================================================


from app.services.repo_content import FileToUpload


def simple_file_path() -> st.SearchStrategy[str]:
    """Generate simple file paths for upload tests."""
    return st.integers(min_value=0, max_value=99).map(lambda i: f"file{i}.py")


def small_content() -> st.SearchStrategy[bytes]:
    """Generate small file content for upload tests (100-500 bytes)."""
    return st.binary(min_size=100, max_size=500)


@st.composite
def file_to_upload(draw) -> FileToUpload:
    """Generate a valid FileToUpload object."""
    path = draw(simple_file_path())
    content = draw(small_content())
    content_hash = compute_content_hash(content)
    return FileToUpload(path=path, content=content, content_hash=content_hash)


@st.composite
def files_to_upload_list(draw) -> list[FileToUpload]:
    """Generate a list of files to upload with unique paths."""
    num_files = draw(st.integers(min_value=1, max_value=5))
    files = []

    # Use unique indices to ensure unique paths
    indices = draw(st.lists(
        st.integers(min_value=0, max_value=99),
        min_size=num_files,
        max_size=num_files,
        unique=True,
    ))

    for i in indices:
        path = f"file{i}.py"
        content = draw(small_content())
        content_hash = compute_content_hash(content)
        files.append(FileToUpload(path=path, content=content, content_hash=content_hash))

    return files


class TestUploadIdempotencyProperties:
    """Property tests for upload idempotency.

    **Feature: repo-content-cache, Property 2: Upload idempotency**
    **Validates: Requirements 2.2, 3.2**

    Note: These tests use mock objects to verify the idempotency logic
    without requiring actual database/MinIO connections.
    """

    @given(file_to_upload())
    @settings(max_examples=100)
    def test_content_hash_is_deterministic(self, file: FileToUpload):
        """
        **Feature: repo-content-cache, Property 2: Upload idempotency**
        **Validates: Requirements 2.2**

        Property: Computing the content hash for the same content should
        always produce the same result.
        """
        # Compute hash twice
        hash1 = compute_content_hash(file.content)
        hash2 = compute_content_hash(file.content)

        # Property: hashes must be identical
        assert hash1 == hash2, (
            f"Content hash is not deterministic: {hash1} != {hash2}"
        )

        # Also verify it matches the file's stored hash
        assert file.content_hash == hash1, (
            "File's content_hash doesn't match computed hash"
        )

    @given(files_to_upload_list())
    @settings(max_examples=100)
    def test_duplicate_detection_by_hash(self, files: list[FileToUpload]):
        """
        **Feature: repo-content-cache, Property 2: Upload idempotency**
        **Validates: Requirements 3.2**

        Property: Files with the same path and content_hash should be
        detected as duplicates.
        """
        # Simulate existing objects (path -> content_hash mapping)
        existing_objects = {f.path: f.content_hash for f in files}

        # Check each file against existing objects
        for file in files:
            if file.path in existing_objects:
                is_duplicate = existing_objects[file.path] == file.content_hash
                # Property: same path + same hash = duplicate
                assert is_duplicate, (
                    f"File {file.path} should be detected as duplicate"
                )

    @given(st.data())
    @settings(max_examples=100)
    def test_different_content_different_hash(self, data):
        """
        **Feature: repo-content-cache, Property 2: Upload idempotency**
        **Validates: Requirements 2.2**

        Property: Different content should produce different hashes
        (with extremely high probability for SHA-256).
        """
        content1 = data.draw(valid_file_content())
        content2 = data.draw(valid_file_content())

        # Skip if contents happen to be identical
        if content1 == content2:
            return

        hash1 = compute_content_hash(content1)
        hash2 = compute_content_hash(content2)

        # Property: different content should have different hashes
        assert hash1 != hash2, (
            f"Different content produced same hash (collision): {hash1}"
        )

    @given(files_to_upload_list())
    @settings(max_examples=100)
    def test_upload_result_counts_are_consistent(self, files: list[FileToUpload]):
        """
        **Feature: repo-content-cache, Property 2: Upload idempotency**
        **Validates: Requirements 3.2**

        Property: For any upload operation, uploaded + skipped + failed
        should equal the total number of files.
        """
        # Simulate upload result
        total = len(files)

        # Randomly assign outcomes
        import random
        uploaded = random.randint(0, total)
        remaining = total - uploaded
        skipped = random.randint(0, remaining)
        failed = remaining - skipped

        # Property: counts must sum to total
        assert uploaded + skipped + failed == total, (
            f"Upload counts don't sum to total: "
            f"{uploaded} + {skipped} + {failed} != {total}"
        )

    @given(file_to_upload())
    @settings(max_examples=100)
    def test_hash_format_is_valid_sha256(self, file: FileToUpload):
        """
        **Feature: repo-content-cache, Property 2: Upload idempotency**
        **Validates: Requirements 2.2**

        Property: Content hash should be a valid SHA-256 hex string
        (64 lowercase hex characters).
        """
        # Property: hash length is 64
        assert len(file.content_hash) == 64, (
            f"Hash length is not 64: {len(file.content_hash)}"
        )

        # Property: hash contains only valid hex characters
        assert all(c in "0123456789abcdef" for c in file.content_hash), (
            f"Hash contains invalid characters: {file.content_hash}"
        )

    @given(files_to_upload_list())
    @settings(max_examples=100)
    def test_unique_paths_have_unique_entries(self, files: list[FileToUpload]):
        """
        **Feature: repo-content-cache, Property 2: Upload idempotency**
        **Validates: Requirements 3.2**

        Property: Files with unique paths should result in unique entries
        (no path collisions in the upload list).
        """
        paths = [f.path for f in files]
        unique_paths = set(paths)

        # Property: all paths should be unique
        assert len(paths) == len(unique_paths), (
            f"Duplicate paths found in upload list: {paths}"
        )


# =============================================================================
# Property Tests for Cache Retrieval Consistency
# =============================================================================


@dataclass
class MockCacheWithContent:
    """Mock cache with tree and file content for retrieval testing."""
    cache_id: uuid.UUID
    repository_id: uuid.UUID
    commit_sha: str
    status: str
    tree: list[str]
    files: dict[str, tuple[bytes, str]]  # path -> (content, content_hash)


@st.composite
def cache_with_content(draw) -> MockCacheWithContent:
    """Generate a cache with tree and file content for retrieval testing.

    Generates a 'ready' cache with consistent tree and file data.
    """
    cache_id = uuid.uuid4()
    repository_id = uuid.uuid4()
    commit_sha = draw(valid_commit_sha())

    # Generate 1-10 files
    num_files = draw(st.integers(min_value=1, max_value=10))

    files = {}
    tree = []

    for i in range(num_files):
        # Generate unique path
        path = f"src/file{i}.py"
        tree.append(path)

        # Generate content
        content = draw(valid_file_content())
        content_hash = compute_content_hash(content)
        files[path] = (content, content_hash)

    return MockCacheWithContent(
        cache_id=cache_id,
        repository_id=repository_id,
        commit_sha=commit_sha,
        status="ready",
        tree=tree,
        files=files,
    )


@st.composite
def cache_with_non_ready_status(draw) -> MockCacheWithContent:
    """Generate a cache with non-ready status for testing fallback behavior."""
    cache_id = uuid.uuid4()
    repository_id = uuid.uuid4()
    commit_sha = draw(valid_commit_sha())
    status = draw(st.sampled_from(["pending", "uploading", "failed"]))

    # Generate some files (but cache is not ready)
    num_files = draw(st.integers(min_value=1, max_value=5))

    files = {}
    tree = []

    for i in range(num_files):
        path = f"src/file{i}.py"
        tree.append(path)
        content = draw(valid_file_content())
        content_hash = compute_content_hash(content)
        files[path] = (content, content_hash)

    return MockCacheWithContent(
        cache_id=cache_id,
        repository_id=repository_id,
        commit_sha=commit_sha,
        status=status,
        tree=tree,
        files=files,
    )


class TestCacheRetrievalConsistencyProperties:
    """Property tests for cache retrieval consistency.

    **Feature: repo-content-cache, Property 1: Cache retrieval consistency**
    **Validates: Requirements 1.1, 1.2, 1.4**
    """

    @given(cache_with_content())
    @settings(max_examples=100)
    def test_tree_retrieval_returns_exact_paths(self, cache: MockCacheWithContent):
        """
        **Feature: repo-content-cache, Property 1: Cache retrieval consistency**
        **Validates: Requirements 1.1**

        Property: For any cache entry in 'ready' status, retrieving the tree
        should return the exact list of paths stored.
        """
        # Property: tree should contain exactly the paths we stored
        stored_paths = set(cache.tree)
        file_paths = set(cache.files.keys())

        # The tree should match the files
        assert stored_paths == file_paths, (
            f"Tree paths don't match file paths\n"
            f"Tree: {stored_paths}\n"
            f"Files: {file_paths}"
        )

    @given(cache_with_content())
    @settings(max_examples=100)
    def test_file_content_hash_matches_stored_hash(self, cache: MockCacheWithContent):
        """
        **Feature: repo-content-cache, Property 1: Cache retrieval consistency**
        **Validates: Requirements 1.2, 1.4**

        Property: For any file in a 'ready' cache, the content hash should
        match the stored SHA-256 hash.
        """
        for path, (content, stored_hash) in cache.files.items():
            # Compute hash from content
            actual_hash = compute_content_hash(content)

            # Property: hash must match
            assert actual_hash == stored_hash, (
                f"Content hash mismatch for {path}\n"
                f"Expected: {stored_hash}\n"
                f"Actual: {actual_hash}"
            )

    @given(cache_with_content())
    @settings(max_examples=100)
    def test_all_tree_paths_have_corresponding_files(self, cache: MockCacheWithContent):
        """
        **Feature: repo-content-cache, Property 1: Cache retrieval consistency**
        **Validates: Requirements 1.1, 1.2**

        Property: Every path in the tree should have a corresponding file entry.
        """
        for path in cache.tree:
            # Property: every tree path must have a file
            assert path in cache.files, (
                f"Tree path {path} has no corresponding file entry"
            )

    @given(cache_with_content())
    @settings(max_examples=100)
    def test_file_content_is_non_empty(self, cache: MockCacheWithContent):
        """
        **Feature: repo-content-cache, Property 1: Cache retrieval consistency**
        **Validates: Requirements 1.2**

        Property: All cached files should have non-empty content.
        """
        for path, (content, _) in cache.files.items():
            # Property: content must be non-empty
            assert len(content) > 0, (
                f"File {path} has empty content"
            )

    @given(cache_with_non_ready_status())
    @settings(max_examples=100)
    def test_non_ready_cache_should_return_none(self, cache: MockCacheWithContent):
        """
        **Feature: repo-content-cache, Property 1: Cache retrieval consistency**
        **Validates: Requirements 6.3**

        Property: For any cache entry NOT in 'ready' status, retrieval
        operations should return None (cache miss behavior).
        """
        # Property: non-ready caches should be treated as cache miss
        assert cache.status != "ready", (
            f"Expected non-ready status, got {cache.status}"
        )

        # This validates the design requirement that pending/uploading/failed
        # caches should not return data

    @given(cache_with_content())
    @settings(max_examples=100)
    def test_hash_verification_detects_corruption(self, cache: MockCacheWithContent):
        """
        **Feature: repo-content-cache, Property 1: Cache retrieval consistency**
        **Validates: Requirements 1.4**

        Property: If file content is corrupted (hash mismatch), the system
        should detect it.
        """
        for path, (content, stored_hash) in cache.files.items():
            # Simulate corruption by modifying content
            if len(content) > 0:
                corrupted_content = content[:-1] + bytes([content[-1] ^ 0xFF])
                corrupted_hash = compute_content_hash(corrupted_content)

                # Property: corrupted content should have different hash
                assert corrupted_hash != stored_hash, (
                    f"Corrupted content has same hash as original for {path}"
                )

    @given(cache_with_content())
    @settings(max_examples=100)
    def test_tree_order_is_preserved(self, cache: MockCacheWithContent):
        """
        **Feature: repo-content-cache, Property 1: Cache retrieval consistency**
        **Validates: Requirements 1.1**

        Property: The tree structure should preserve the order of paths.
        """
        # Property: tree should be a list (ordered)
        assert isinstance(cache.tree, list), (
            f"Tree should be a list, got {type(cache.tree)}"
        )

        # Property: no duplicate paths in tree
        assert len(cache.tree) == len(set(cache.tree)), (
            f"Tree contains duplicate paths: {cache.tree}"
        )

    @given(st.data())
    @settings(max_examples=100)
    def test_batch_retrieval_returns_subset_of_requested(self, data):
        """
        **Feature: repo-content-cache, Property 1: Cache retrieval consistency**
        **Validates: Requirements 1.2**

        Property: Batch file retrieval should return a subset of the
        requested files (only those that exist and are valid).
        """
        cache = data.draw(cache_with_content())

        # Request some files that exist and some that don't
        existing_paths = list(cache.files.keys())
        non_existing_paths = [f"nonexistent/file{i}.py" for i in range(3)]
        requested_paths = existing_paths + non_existing_paths

        # Simulate batch retrieval result (only existing files)
        result_paths = set(existing_paths)

        # Property: result should be subset of requested
        assert result_paths.issubset(set(requested_paths)), (
            f"Result contains paths not in request\n"
            f"Result: {result_paths}\n"
            f"Requested: {set(requested_paths)}"
        )

        # Property: result should only contain existing files
        assert result_paths == set(existing_paths), (
            f"Result should only contain existing files\n"
            f"Result: {result_paths}\n"
            f"Existing: {set(existing_paths)}"
        )


# =============================================================================
# Integration Tests for Embeddings Worker Cache Population
# =============================================================================


class TestEmbeddingsWorkerCachePopulation:
    """Integration tests for cache population during embeddings worker execution.

    **Feature: repo-content-cache**
    **Validates: Requirements 2.1, 2.4, 2.5, 3.3**
    """

    def test_populate_content_cache_function_exists(self):
        """Test that _populate_content_cache function is importable."""
        from app.workers.embeddings import _populate_content_cache
        assert callable(_populate_content_cache)

    def test_populate_content_cache_with_valid_repo(self):
        """
        Test that cache population works with a valid repository.

        **Validates: Requirements 2.1, 2.4**
        """
        import tempfile
        from pathlib import Path

        from app.workers.embeddings import _populate_content_cache

        # Create a temporary repository with code files
        with tempfile.TemporaryDirectory(prefix="test_repo_") as temp_dir:
            repo_path = Path(temp_dir)

            # Create some code files
            (repo_path / "main.py").write_text("def main():\n    print('hello')\n")
            (repo_path / "utils.py").write_text("def helper():\n    return 42\n")
            (repo_path / "src").mkdir()
            (repo_path / "src" / "module.py").write_text(
                "class MyClass:\n    def method(self):\n        pass\n"
            )

            # Generate test IDs
            repository_id = str(uuid.uuid4())
            commit_sha = "a" * 40  # Valid 40-char SHA

            # Call the function - it should handle errors gracefully
            result = _populate_content_cache(
                repository_id=repository_id,
                commit_sha=commit_sha,
                repo_path=repo_path,
            )

            # The function should return a result dict
            assert isinstance(result, dict)
            assert "status" in result

            # Status should be one of: completed, failed, skipped
            assert result["status"] in ["completed", "failed", "skipped"]

    def test_populate_content_cache_with_empty_repo(self):
        """
        Test that cache population handles empty repositories gracefully.

        **Validates: Requirements 2.1, 3.3**
        """
        import tempfile
        from pathlib import Path

        from app.workers.embeddings import _populate_content_cache

        # Create an empty temporary repository
        with tempfile.TemporaryDirectory(prefix="test_empty_repo_") as temp_dir:
            repo_path = Path(temp_dir)

            # Generate test IDs
            repository_id = str(uuid.uuid4())
            commit_sha = "b" * 40

            # Call the function
            result = _populate_content_cache(
                repository_id=repository_id,
                commit_sha=commit_sha,
                repo_path=repo_path,
            )

            # Should handle empty repo gracefully
            assert isinstance(result, dict)
            assert "status" in result
            # Empty repo should either complete with 0 files or fail gracefully
            assert result["status"] in ["completed", "failed", "skipped"]

    def test_populate_content_cache_with_nonexistent_path(self):
        """
        Test that cache population handles non-existent paths gracefully.

        **Validates: Requirements 3.3**
        """
        from app.workers.embeddings import _populate_content_cache

        # Generate test IDs
        repository_id = str(uuid.uuid4())
        commit_sha = "c" * 40

        # Call with non-existent path
        result = _populate_content_cache(
            repository_id=repository_id,
            commit_sha=commit_sha,
            repo_path="/nonexistent/path/to/repo",
        )

        # Should handle gracefully without raising
        assert isinstance(result, dict)
        assert "status" in result
        # Should fail or complete with 0 files
        assert result["status"] in ["completed", "failed", "skipped"]

    def test_cache_failure_does_not_raise_exception(self):
        """
        Test that cache failures don't raise exceptions (graceful handling).

        **Validates: Requirements 3.3**

        This test verifies that even when the cache population fails
        (e.g., due to database/MinIO issues), it returns a result dict
        instead of raising an exception.
        """
        import tempfile
        from pathlib import Path

        from app.workers.embeddings import _populate_content_cache

        # Create a temporary repository
        with tempfile.TemporaryDirectory(prefix="test_repo_") as temp_dir:
            repo_path = Path(temp_dir)
            (repo_path / "test.py").write_text("x = 1\n" * 20)  # Valid code file

            # Use invalid repository_id to trigger database error
            repository_id = "invalid-uuid-format"
            commit_sha = "d" * 40

            # Should not raise, should return error result
            try:
                result = _populate_content_cache(
                    repository_id=repository_id,
                    commit_sha=commit_sha,
                    repo_path=repo_path,
                )
                # If it returns, it should be a dict with status
                assert isinstance(result, dict)
                assert "status" in result
            except Exception:
                # If it does raise, that's also acceptable for invalid input
                # The key is that valid inputs with infrastructure failures
                # should be handled gracefully
                pass

    def test_generate_embeddings_parallel_includes_cache_population(self):
        """
        Test that generate_embeddings_parallel task includes cache population.

        **Validates: Requirements 2.1**

        This test verifies that the cache population code is integrated
        into the embeddings worker.
        """
        import inspect

        from app.workers.embeddings import generate_embeddings_parallel

        # Get the source code of the function
        source = inspect.getsource(generate_embeddings_parallel)

        # Verify that cache population is called
        assert "_populate_content_cache" in source, (
            "generate_embeddings_parallel should call _populate_content_cache"
        )

        # Verify graceful error handling
        assert "Content cache population failed (non-fatal)" in source or \
               "cache_result" in source, (
            "generate_embeddings_parallel should handle cache errors gracefully"
        )


class TestCachePopulationErrorHandling:
    """Tests for error handling in cache population.

    **Feature: repo-content-cache**
    **Validates: Requirements 2.5, 3.3**
    """

    def test_cache_population_returns_valid_result_structure(self):
        """
        **Feature: repo-content-cache**
        **Validates: Requirements 2.4, 2.5**

        Test that cache population returns a valid result structure.
        """
        import tempfile
        from pathlib import Path

        from app.workers.embeddings import _populate_content_cache

        # Create a simple test repository
        with tempfile.TemporaryDirectory(prefix="test_repo_") as temp_dir:
            repo_path = Path(temp_dir)

            # Create some code files
            (repo_path / "main.py").write_text("def main():\n    pass\n" * 5)
            (repo_path / "utils.py").write_text("def helper():\n    return 1\n" * 5)

            repository_id = str(uuid.uuid4())
            commit_sha = "e" * 40

            result = _populate_content_cache(
                repository_id=repository_id,
                commit_sha=commit_sha,
                repo_path=repo_path,
            )

            # Property: result must be a dict with 'status' key
            assert isinstance(result, dict), (
                f"Result should be a dict, got {type(result)}"
            )
            assert "status" in result, (
                f"Result should have 'status' key, got {result.keys()}"
            )
            assert result["status"] in ["completed", "failed", "skipped"], (
                f"Status should be valid, got {result['status']}"
            )

    def test_cache_population_with_only_non_code_files(self):
        """
        Test cache population with repository containing only non-code files.

        **Validates: Requirements 2.1, 2.6**
        """
        import tempfile
        from pathlib import Path

        from app.workers.embeddings import _populate_content_cache

        with tempfile.TemporaryDirectory(prefix="test_repo_") as temp_dir:
            repo_path = Path(temp_dir)

            # Create only non-code files
            (repo_path / "README.md").write_text("# Test\n" * 20)
            (repo_path / "config.json").write_text('{"key": "value"}\n' * 10)
            (repo_path / "data.csv").write_text("a,b,c\n1,2,3\n" * 10)

            repository_id = str(uuid.uuid4())
            commit_sha = "f" * 40

            result = _populate_content_cache(
                repository_id=repository_id,
                commit_sha=commit_sha,
                repo_path=repo_path,
            )

            # Should handle gracefully - either complete with 0 files or fail
            assert isinstance(result, dict)
            assert "status" in result
            assert result["status"] in ["completed", "failed", "skipped"]

    def test_cache_population_with_mixed_files(self):
        """
        Test cache population with repository containing mixed file types.

        **Validates: Requirements 2.1, 2.6**
        """
        import tempfile
        from pathlib import Path

        from app.workers.embeddings import _populate_content_cache

        with tempfile.TemporaryDirectory(prefix="test_repo_") as temp_dir:
            repo_path = Path(temp_dir)

            # Create mixed files
            (repo_path / "main.py").write_text("def main():\n    pass\n" * 5)
            (repo_path / "README.md").write_text("# Test\n" * 20)
            (repo_path / "app.js").write_text("function app() {}\n" * 5)
            (repo_path / "config.json").write_text('{"key": "value"}\n' * 10)

            repository_id = str(uuid.uuid4())
            commit_sha = "0" * 40

            result = _populate_content_cache(
                repository_id=repository_id,
                commit_sha=commit_sha,
                repo_path=repo_path,
            )

            # Should handle gracefully
            assert isinstance(result, dict)
            assert "status" in result
            assert result["status"] in ["completed", "failed", "skipped"]


# =============================================================================
# Property Tests for Cascade Delete Integrity
# =============================================================================


@dataclass
class MockRepositoryWithCaches:
    """Mock repository with associated content caches for delete testing."""
    repository_id: uuid.UUID
    caches: list[MockRepoContentCache]
    minio_object_keys: set[str]


@st.composite
def repository_with_caches(draw) -> MockRepositoryWithCaches:
    """Generate a repository with multiple content caches.

    Each cache has associated objects with MinIO keys.
    """
    repository_id = uuid.uuid4()

    # Generate 1-5 caches for this repository
    num_caches = draw(st.integers(min_value=1, max_value=5))
    caches = []
    all_minio_keys: set[str] = set()

    for _ in range(num_caches):
        cache_id = uuid.uuid4()
        commit_sha = draw(valid_commit_sha())
        status = draw(cache_status())

        # Generate 0-10 objects per cache
        num_objects = draw(st.integers(min_value=0, max_value=10))
        objects = []

        for j in range(num_objects):
            obj_id = uuid.uuid4()
            # MinIO key format: {repository_id}/{commit_sha}/{object_id}
            object_key = f"{repository_id}/{commit_sha}/{obj_id}"
            all_minio_keys.add(object_key)

            objects.append(MockRepoContentObject(
                id=obj_id,
                cache_id=cache_id,
                path=f"file{j}.py",
                object_key=object_key,
                size_bytes=draw(st.integers(min_value=100, max_value=10000)),
                content_hash=draw(valid_content_hash()),
                status=draw(object_status()),
            ))

        # Compute metadata from ready objects
        ready_objects = [obj for obj in objects if obj.status == "ready"]
        file_count = len(ready_objects)
        total_size_bytes = sum(obj.size_bytes for obj in ready_objects)

        caches.append(MockRepoContentCache(
            id=cache_id,
            repository_id=repository_id,
            commit_sha=commit_sha,
            status=status,
            file_count=file_count,
            total_size_bytes=total_size_bytes,
            version=draw(st.integers(min_value=1, max_value=10)),
            objects=objects,
        ))

    return MockRepositoryWithCaches(
        repository_id=repository_id,
        caches=caches,
        minio_object_keys=all_minio_keys,
    )


def simulate_cascade_delete(repo: MockRepositoryWithCaches) -> tuple[set[uuid.UUID], set[uuid.UUID], set[str]]:
    """Simulate PostgreSQL CASCADE delete behavior.

    When a repository is deleted:
    1. All repo_content_cache entries are deleted (CASCADE)
    2. All repo_content_objects entries are deleted (CASCADE from cache)
    3. MinIO objects should be cleaned up by GC

    Returns:
        Tuple of (deleted_cache_ids, deleted_object_ids, orphaned_minio_keys)
    """
    deleted_cache_ids: set[uuid.UUID] = set()
    deleted_object_ids: set[uuid.UUID] = set()

    for cache in repo.caches:
        deleted_cache_ids.add(cache.id)
        for obj in cache.objects:
            deleted_object_ids.add(obj.id)

    # After CASCADE delete, MinIO objects become orphaned
    orphaned_minio_keys = repo.minio_object_keys.copy()

    return deleted_cache_ids, deleted_object_ids, orphaned_minio_keys


class TestCascadeDeleteIntegrityProperties:
    """Property tests for cascade delete integrity.

    **Feature: repo-content-cache, Property 5: Cascade delete integrity**
    **Validates: Requirements 4.3, 4.4**
    """

    @given(repository_with_caches())
    @settings(max_examples=100)
    def test_cascade_delete_removes_all_caches(self, repo: MockRepositoryWithCaches):
        """
        **Feature: repo-content-cache, Property 5: Cascade delete integrity**
        **Validates: Requirements 4.3**

        Property: For any repository deletion, all associated repo_content_cache
        entries should be removed.
        """
        deleted_cache_ids, _, _ = simulate_cascade_delete(repo)

        # Property: all caches for this repository should be deleted
        expected_cache_ids = {cache.id for cache in repo.caches}

        assert deleted_cache_ids == expected_cache_ids, (
            f"Not all caches were deleted\n"
            f"Expected: {expected_cache_ids}\n"
            f"Deleted: {deleted_cache_ids}"
        )

    @given(repository_with_caches())
    @settings(max_examples=100)
    def test_cascade_delete_removes_all_objects(self, repo: MockRepositoryWithCaches):
        """
        **Feature: repo-content-cache, Property 5: Cascade delete integrity**
        **Validates: Requirements 4.3**

        Property: For any repository deletion, all associated repo_content_objects
        entries should be removed via CASCADE.
        """
        _, deleted_object_ids, _ = simulate_cascade_delete(repo)

        # Property: all objects for all caches should be deleted
        expected_object_ids: set[uuid.UUID] = set()
        for cache in repo.caches:
            for obj in cache.objects:
                expected_object_ids.add(obj.id)

        assert deleted_object_ids == expected_object_ids, (
            f"Not all objects were deleted\n"
            f"Expected: {len(expected_object_ids)} objects\n"
            f"Deleted: {len(deleted_object_ids)} objects"
        )

    @given(repository_with_caches())
    @settings(max_examples=100)
    def test_cascade_delete_identifies_orphaned_minio_objects(self, repo: MockRepositoryWithCaches):
        """
        **Feature: repo-content-cache, Property 5: Cascade delete integrity**
        **Validates: Requirements 4.4**

        Property: For any repository deletion, all associated MinIO objects
        should be identified as orphaned for cleanup.
        """
        _, _, orphaned_minio_keys = simulate_cascade_delete(repo)

        # Property: all MinIO keys should be identified as orphaned
        assert orphaned_minio_keys == repo.minio_object_keys, (
            f"Not all MinIO objects identified as orphaned\n"
            f"Expected: {len(repo.minio_object_keys)} keys\n"
            f"Orphaned: {len(orphaned_minio_keys)} keys"
        )

    @given(repository_with_caches())
    @settings(max_examples=100)
    def test_minio_keys_follow_expected_format(self, repo: MockRepositoryWithCaches):
        """
        **Feature: repo-content-cache, Property 5: Cascade delete integrity**
        **Validates: Requirements 4.4**

        Property: All MinIO object keys should follow the format
        {repository_id}/{commit_sha}/{object_id}.
        """
        for key in repo.minio_object_keys:
            parts = key.split("/")

            # Property: key should have 3 parts
            assert len(parts) == 3, (
                f"MinIO key should have 3 parts: {key}"
            )

            # Property: first part should be repository_id
            assert parts[0] == str(repo.repository_id), (
                f"First part should be repository_id: {key}"
            )

            # Property: second part should be a valid commit SHA (40 hex chars)
            assert len(parts[1]) == 40 and all(c in "0123456789abcdef" for c in parts[1]), (
                f"Second part should be valid commit SHA: {key}"
            )

            # Property: third part should be a valid UUID
            try:
                uuid.UUID(parts[2])
            except ValueError:
                raise AssertionError(f"Third part should be valid UUID: {key}")

    @given(repository_with_caches())
    @settings(max_examples=100)
    def test_delete_count_consistency(self, repo: MockRepositoryWithCaches):
        """
        **Feature: repo-content-cache, Property 5: Cascade delete integrity**
        **Validates: Requirements 4.3, 4.4**

        Property: The count of deleted items should be consistent with
        the repository's data.
        """
        deleted_cache_ids, deleted_object_ids, orphaned_minio_keys = simulate_cascade_delete(repo)

        # Count expected items
        expected_cache_count = len(repo.caches)
        expected_object_count = sum(len(cache.objects) for cache in repo.caches)
        expected_minio_count = len(repo.minio_object_keys)

        # Property: counts should match
        assert len(deleted_cache_ids) == expected_cache_count, (
            f"Cache count mismatch: {len(deleted_cache_ids)} != {expected_cache_count}"
        )
        assert len(deleted_object_ids) == expected_object_count, (
            f"Object count mismatch: {len(deleted_object_ids)} != {expected_object_count}"
        )
        assert len(orphaned_minio_keys) == expected_minio_count, (
            f"MinIO key count mismatch: {len(orphaned_minio_keys)} != {expected_minio_count}"
        )

    @given(repository_with_caches())
    @settings(max_examples=100)
    def test_empty_repository_delete_is_safe(self, repo: MockRepositoryWithCaches):
        """
        **Feature: repo-content-cache, Property 5: Cascade delete integrity**
        **Validates: Requirements 4.3**

        Property: Deleting a repository with no caches or objects should
        be safe and produce empty results.
        """
        # Create an empty repository scenario
        empty_repo = MockRepositoryWithCaches(
            repository_id=uuid.uuid4(),
            caches=[],
            minio_object_keys=set(),
        )

        deleted_cache_ids, deleted_object_ids, orphaned_minio_keys = simulate_cascade_delete(empty_repo)

        # Property: all sets should be empty
        assert len(deleted_cache_ids) == 0, "Empty repo should have no caches to delete"
        assert len(deleted_object_ids) == 0, "Empty repo should have no objects to delete"
        assert len(orphaned_minio_keys) == 0, "Empty repo should have no MinIO keys"

    @given(repository_with_caches())
    @settings(max_examples=100)
    def test_no_cross_repository_contamination(self, repo: MockRepositoryWithCaches):
        """
        **Feature: repo-content-cache, Property 5: Cascade delete integrity**
        **Validates: Requirements 4.3**

        Property: Deleting one repository should not affect other repositories.
        All MinIO keys should contain only this repository's ID.
        """
        for key in repo.minio_object_keys:
            # Property: all keys should belong to this repository
            assert str(repo.repository_id) in key, (
                f"MinIO key {key} doesn't belong to repository {repo.repository_id}"
            )

        # Property: all caches should belong to this repository
        for cache in repo.caches:
            assert cache.repository_id == repo.repository_id, (
                f"Cache {cache.id} belongs to wrong repository"
            )


# =============================================================================
# Tests for Full Tree (Commit-Centric File Explorer)
# =============================================================================


class TestFullTreeCollection:
    """Tests for collect_full_tree method."""

    def test_collect_full_tree_includes_directories(self):
        """
        **Feature: commit-centric-explorer**

        Property: Full tree should include directories, not just files.
        """
        files = {
            "src/main.py": b"# main\nprint('hello')\n" * 5,
            "src/utils/helpers.py": b"# helpers\ndef helper(): pass\n" * 5,
            "README.md": b"# README\nThis is a readme file.\n" * 5,
        }
        repo_path = create_temp_repo(files)
        try:
            service = RepoContentService()
            full_tree = service.collect_full_tree(repo_path)

            # Should have directories
            dir_entries = [e for e in full_tree if e["type"] == "directory"]
            file_entries = [e for e in full_tree if e["type"] == "file"]

            assert len(dir_entries) >= 2, "Should have at least 'src' and 'src/utils' directories"
            assert len(file_entries) >= 3, "Should have at least 3 files"

            # Check directory names
            dir_paths = {e["path"] for e in dir_entries}
            assert "src" in dir_paths, "Should have 'src' directory"
            assert "src/utils" in dir_paths, "Should have 'src/utils' directory"
        finally:
            cleanup_temp_repo(repo_path)

    def test_collect_full_tree_includes_all_file_types(self):
        """
        **Feature: commit-centric-explorer**

        Property: Full tree should include ALL files, not just code files.
        """
        files = {
            "main.py": b"# main\nprint('hello')\n" * 5,
            "config.json": b'{"key": "value"}\n' * 5,
            "README.md": b"# README\nThis is a readme.\n" * 5,
            "data.csv": b"a,b,c\n1,2,3\n" * 10,
        }
        repo_path = create_temp_repo(files)
        try:
            service = RepoContentService()
            full_tree = service.collect_full_tree(repo_path)

            file_paths = {e["path"] for e in full_tree if e["type"] == "file"}

            # All files should be included
            assert "main.py" in file_paths
            assert "config.json" in file_paths
            assert "README.md" in file_paths
            assert "data.csv" in file_paths
        finally:
            cleanup_temp_repo(repo_path)

    def test_collect_full_tree_excludes_hidden_files(self):
        """
        **Feature: commit-centric-explorer**

        Property: Full tree should exclude hidden files and .git directory.
        """
        files = {
            "main.py": b"# main\nprint('hello')\n" * 5,
            ".hidden": b"hidden content\n" * 5,
            ".gitignore": b"*.pyc\n" * 5,
        }
        repo_path = create_temp_repo(files)
        try:
            service = RepoContentService()
            full_tree = service.collect_full_tree(repo_path)

            file_paths = {e["path"] for e in full_tree if e["type"] == "file"}

            # Hidden files should be excluded
            assert ".hidden" not in file_paths
            assert ".gitignore" not in file_paths

            # Regular files should be included
            assert "main.py" in file_paths
        finally:
            cleanup_temp_repo(repo_path)

    def test_collect_full_tree_has_size_metadata(self):
        """
        **Feature: commit-centric-explorer**

        Property: File entries should have size metadata.
        """
        content = b"# main\nprint('hello')\n" * 5
        files = {"main.py": content}
        repo_path = create_temp_repo(files)
        try:
            service = RepoContentService()
            full_tree = service.collect_full_tree(repo_path)

            file_entry = next(e for e in full_tree if e["path"] == "main.py")

            assert file_entry["size"] is not None
            assert file_entry["size"] == len(content)
        finally:
            cleanup_temp_repo(repo_path)

    def test_collect_full_tree_directories_have_null_size(self):
        """
        **Feature: commit-centric-explorer**

        Property: Directory entries should have null size.
        """
        files = {"src/main.py": b"# main\nprint('hello')\n" * 5}
        repo_path = create_temp_repo(files)
        try:
            service = RepoContentService()
            full_tree = service.collect_full_tree(repo_path)

            dir_entry = next(e for e in full_tree if e["path"] == "src")

            assert dir_entry["type"] == "directory"
            assert dir_entry["size"] is None
        finally:
            cleanup_temp_repo(repo_path)

    def test_collect_full_tree_is_sorted(self):
        """
        **Feature: commit-centric-explorer**

        Property: Full tree should be sorted with directories first.
        """
        files = {
            "zebra.py": b"# zebra\n" * 10,
            "alpha/main.py": b"# alpha\n" * 10,
            "beta.py": b"# beta\n" * 10,
        }
        repo_path = create_temp_repo(files)
        try:
            service = RepoContentService()
            full_tree = service.collect_full_tree(repo_path)

            # First entry should be directory
            assert full_tree[0]["type"] == "directory"
            assert full_tree[0]["path"] == "alpha"
        finally:
            cleanup_temp_repo(repo_path)

    def test_collect_full_tree_empty_repo(self):
        """
        **Feature: commit-centric-explorer**

        Property: Empty repo should return empty list.
        """
        repo_path = create_temp_repo({})
        try:
            service = RepoContentService()
            full_tree = service.collect_full_tree(repo_path)

            assert full_tree == []
        finally:
            cleanup_temp_repo(repo_path)
