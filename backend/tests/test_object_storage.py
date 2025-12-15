"""Unit tests for ObjectStorageClient and MinIOClient.

Tests cover:
- put_object, get_object, delete_object operations
- Error handling for unavailable MinIO
- Requirements: 3.3, 3.4
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from io import BytesIO

from minio.error import S3Error

from app.services.object_storage import (
    MinIOClient,
    ObjectStorageError,
    get_object_storage_client,
)


# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def mock_minio_client():
    """Create a mock Minio client."""
    with patch("app.services.object_storage.Minio") as mock_minio_class:
        mock_client = MagicMock()
        mock_minio_class.return_value = mock_client
        yield mock_client


@pytest.fixture
def minio_client(mock_minio_client):
    """Create a MinIOClient with mocked underlying Minio client."""
    client = MinIOClient(
        endpoint="localhost:9000",
        access_key="test_access",
        secret_key="test_secret",
        secure=False,
    )
    # Replace the internal client with our mock
    client._client = mock_minio_client
    return client


# =============================================================================
# Test put_object
# =============================================================================


class TestPutObject:
    """Tests for MinIOClient.put_object operation."""

    @pytest.mark.asyncio
    async def test_put_object_success(self, minio_client, mock_minio_client):
        """Test successful object upload."""
        mock_minio_client.put_object.return_value = None
        
        await minio_client.put_object(
            bucket="test-bucket",
            key="test/key.txt",
            data=b"test content",
            content_type="text/plain",
        )
        
        # Verify put_object was called with correct arguments
        mock_minio_client.put_object.assert_called_once()
        call_args = mock_minio_client.put_object.call_args
        assert call_args[0][0] == "test-bucket"
        assert call_args[0][1] == "test/key.txt"
        # Third arg is BytesIO, verify content
        assert call_args[0][2].read() == b"test content"
        assert call_args[0][3] == 12  # length of "test content"
        assert call_args[1]["content_type"] == "text/plain"

    @pytest.mark.asyncio
    async def test_put_object_default_content_type(self, minio_client, mock_minio_client):
        """Test upload with default content type."""
        mock_minio_client.put_object.return_value = None
        
        await minio_client.put_object(
            bucket="test-bucket",
            key="test/key.bin",
            data=b"\x00\x01\x02",
        )
        
        call_args = mock_minio_client.put_object.call_args
        assert call_args[1]["content_type"] == "application/octet-stream"

    @pytest.mark.asyncio
    async def test_put_object_s3_error(self, minio_client, mock_minio_client):
        """Test handling of S3Error during upload."""
        mock_minio_client.put_object.side_effect = S3Error(
            code="InternalError",
            message="Internal server error",
            resource="/test-bucket/test/key.txt",
            request_id="test-request-id",
            host_id="test-host-id",
            response=MagicMock(),
        )
        
        with pytest.raises(ObjectStorageError) as exc_info:
            await minio_client.put_object(
                bucket="test-bucket",
                key="test/key.txt",
                data=b"test content",
            )
        
        assert "Failed to upload object" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_put_object_connection_error(self, minio_client, mock_minio_client):
        """Test handling of connection error during upload."""
        mock_minio_client.put_object.side_effect = Exception("Connection refused")
        
        with pytest.raises(ObjectStorageError) as exc_info:
            await minio_client.put_object(
                bucket="test-bucket",
                key="test/key.txt",
                data=b"test content",
            )
        
        assert "Failed to upload object" in str(exc_info.value)


# =============================================================================
# Test get_object
# =============================================================================


class TestGetObject:
    """Tests for MinIOClient.get_object operation."""

    @pytest.mark.asyncio
    async def test_get_object_success(self, minio_client, mock_minio_client):
        """Test successful object download."""
        mock_response = MagicMock()
        mock_response.read.return_value = b"test content"
        mock_minio_client.get_object.return_value = mock_response
        
        result = await minio_client.get_object(
            bucket="test-bucket",
            key="test/key.txt",
        )
        
        assert result == b"test content"
        mock_minio_client.get_object.assert_called_once_with("test-bucket", "test/key.txt")
        mock_response.close.assert_called_once()
        mock_response.release_conn.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_object_not_found(self, minio_client, mock_minio_client):
        """Test handling of non-existent object."""
        mock_minio_client.get_object.side_effect = S3Error(
            code="NoSuchKey",
            message="The specified key does not exist",
            resource="/test-bucket/test/key.txt",
            request_id="test-request-id",
            host_id="test-host-id",
            response=MagicMock(),
        )
        
        result = await minio_client.get_object(
            bucket="test-bucket",
            key="test/key.txt",
        )
        
        assert result is None

    @pytest.mark.asyncio
    async def test_get_object_s3_error(self, minio_client, mock_minio_client):
        """Test handling of S3Error during download."""
        mock_minio_client.get_object.side_effect = S3Error(
            code="InternalError",
            message="Internal server error",
            resource="/test-bucket/test/key.txt",
            request_id="test-request-id",
            host_id="test-host-id",
            response=MagicMock(),
        )
        
        with pytest.raises(ObjectStorageError) as exc_info:
            await minio_client.get_object(
                bucket="test-bucket",
                key="test/key.txt",
            )
        
        assert "Failed to download object" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_get_object_connection_error(self, minio_client, mock_minio_client):
        """Test handling of connection error during download."""
        mock_minio_client.get_object.side_effect = Exception("Connection refused")
        
        with pytest.raises(ObjectStorageError) as exc_info:
            await minio_client.get_object(
                bucket="test-bucket",
                key="test/key.txt",
            )
        
        assert "Failed to download object" in str(exc_info.value)


# =============================================================================
# Test delete_object
# =============================================================================


class TestDeleteObject:
    """Tests for MinIOClient.delete_object operation."""

    @pytest.mark.asyncio
    async def test_delete_object_success(self, minio_client, mock_minio_client):
        """Test successful object deletion."""
        mock_minio_client.remove_object.return_value = None
        
        await minio_client.delete_object(
            bucket="test-bucket",
            key="test/key.txt",
        )
        
        mock_minio_client.remove_object.assert_called_once_with("test-bucket", "test/key.txt")

    @pytest.mark.asyncio
    async def test_delete_object_not_found_is_idempotent(self, minio_client, mock_minio_client):
        """Test that deleting non-existent object doesn't raise error."""
        mock_minio_client.remove_object.side_effect = S3Error(
            code="NoSuchKey",
            message="The specified key does not exist",
            resource="/test-bucket/test/key.txt",
            request_id="test-request-id",
            host_id="test-host-id",
            response=MagicMock(),
        )
        
        # Should not raise
        await minio_client.delete_object(
            bucket="test-bucket",
            key="test/key.txt",
        )

    @pytest.mark.asyncio
    async def test_delete_object_s3_error(self, minio_client, mock_minio_client):
        """Test handling of S3Error during deletion."""
        mock_minio_client.remove_object.side_effect = S3Error(
            code="AccessDenied",
            message="Access denied",
            resource="/test-bucket/test/key.txt",
            request_id="test-request-id",
            host_id="test-host-id",
            response=MagicMock(),
        )
        
        with pytest.raises(ObjectStorageError) as exc_info:
            await minio_client.delete_object(
                bucket="test-bucket",
                key="test/key.txt",
            )
        
        assert "Failed to delete object" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_delete_object_connection_error(self, minio_client, mock_minio_client):
        """Test handling of connection error during deletion."""
        mock_minio_client.remove_object.side_effect = Exception("Connection refused")
        
        with pytest.raises(ObjectStorageError) as exc_info:
            await minio_client.delete_object(
                bucket="test-bucket",
                key="test/key.txt",
            )
        
        assert "Failed to delete object" in str(exc_info.value)


# =============================================================================
# Test object_exists
# =============================================================================


class TestObjectExists:
    """Tests for MinIOClient.object_exists operation."""

    @pytest.mark.asyncio
    async def test_object_exists_true(self, minio_client, mock_minio_client):
        """Test checking existence of existing object."""
        mock_minio_client.stat_object.return_value = MagicMock()
        
        result = await minio_client.object_exists(
            bucket="test-bucket",
            key="test/key.txt",
        )
        
        assert result is True
        mock_minio_client.stat_object.assert_called_once_with("test-bucket", "test/key.txt")

    @pytest.mark.asyncio
    async def test_object_exists_false(self, minio_client, mock_minio_client):
        """Test checking existence of non-existent object."""
        mock_minio_client.stat_object.side_effect = S3Error(
            code="NoSuchKey",
            message="The specified key does not exist",
            resource="/test-bucket/test/key.txt",
            request_id="test-request-id",
            host_id="test-host-id",
            response=MagicMock(),
        )
        
        result = await minio_client.object_exists(
            bucket="test-bucket",
            key="test/key.txt",
        )
        
        assert result is False

    @pytest.mark.asyncio
    async def test_object_exists_s3_error(self, minio_client, mock_minio_client):
        """Test handling of S3Error during existence check."""
        mock_minio_client.stat_object.side_effect = S3Error(
            code="InternalError",
            message="Internal server error",
            resource="/test-bucket/test/key.txt",
            request_id="test-request-id",
            host_id="test-host-id",
            response=MagicMock(),
        )
        
        with pytest.raises(ObjectStorageError) as exc_info:
            await minio_client.object_exists(
                bucket="test-bucket",
                key="test/key.txt",
            )
        
        assert "Failed to check object existence" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_object_exists_connection_error(self, minio_client, mock_minio_client):
        """Test handling of connection error during existence check."""
        mock_minio_client.stat_object.side_effect = Exception("Connection refused")
        
        with pytest.raises(ObjectStorageError) as exc_info:
            await minio_client.object_exists(
                bucket="test-bucket",
                key="test/key.txt",
            )
        
        assert "Failed to check object existence" in str(exc_info.value)


# =============================================================================
# Test MinIO Unavailable Scenarios
# =============================================================================


class TestMinIOUnavailable:
    """Tests for handling MinIO unavailability.
    
    Requirements: 3.3, 3.4
    """

    @pytest.mark.asyncio
    async def test_put_object_minio_unavailable(self, minio_client, mock_minio_client):
        """Test that upload fails gracefully when MinIO is unavailable."""
        mock_minio_client.put_object.side_effect = Exception(
            "Failed to establish a new connection: [Errno 111] Connection refused"
        )
        
        with pytest.raises(ObjectStorageError) as exc_info:
            await minio_client.put_object(
                bucket="test-bucket",
                key="test/key.txt",
                data=b"test content",
            )
        
        assert "Failed to upload object" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_get_object_minio_unavailable(self, minio_client, mock_minio_client):
        """Test that download fails gracefully when MinIO is unavailable."""
        mock_minio_client.get_object.side_effect = Exception(
            "Failed to establish a new connection: [Errno 111] Connection refused"
        )
        
        with pytest.raises(ObjectStorageError) as exc_info:
            await minio_client.get_object(
                bucket="test-bucket",
                key="test/key.txt",
            )
        
        assert "Failed to download object" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_delete_object_minio_unavailable(self, minio_client, mock_minio_client):
        """Test that deletion fails gracefully when MinIO is unavailable."""
        mock_minio_client.remove_object.side_effect = Exception(
            "Failed to establish a new connection: [Errno 111] Connection refused"
        )
        
        with pytest.raises(ObjectStorageError) as exc_info:
            await minio_client.delete_object(
                bucket="test-bucket",
                key="test/key.txt",
            )
        
        assert "Failed to delete object" in str(exc_info.value)


# =============================================================================
# Test Singleton Pattern
# =============================================================================


class TestSingleton:
    """Tests for get_object_storage_client singleton."""

    def test_get_object_storage_client_returns_same_instance(self):
        """Test that get_object_storage_client returns singleton."""
        # Reset the singleton for testing
        import app.services.object_storage as module
        module._default_client = None
        
        with patch("app.services.object_storage.Minio"):
            client1 = get_object_storage_client()
            client2 = get_object_storage_client()
            
            assert client1 is client2

    def test_get_object_storage_client_creates_minio_client(self):
        """Test that get_object_storage_client creates MinIOClient."""
        import app.services.object_storage as module
        module._default_client = None
        
        with patch("app.services.object_storage.Minio"):
            client = get_object_storage_client()
            
            assert isinstance(client, MinIOClient)
