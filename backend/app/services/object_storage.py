"""Object storage abstraction for MinIO (dev) and S3 (prod).

This module provides an abstract interface for object storage operations,
with a concrete MinIO implementation for development and local deployments.

The abstraction allows easy migration to AWS S3 in production by implementing
the same interface.
"""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from io import BytesIO
from typing import TYPE_CHECKING

from minio import Minio
from minio.error import S3Error

from app.core.config import settings

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# Thread pool for running sync MinIO operations in async context
_executor = ThreadPoolExecutor(max_workers=10, thread_name_prefix="minio_")


class ObjectStorageClient(ABC):
    """Abstract interface for object storage operations.

    Implementations: MinIOClient (dev), S3Client (prod - future).
    """

    @abstractmethod
    async def put_object(
        self,
        bucket: str,
        key: str,
        data: bytes,
        content_type: str = "application/octet-stream",
    ) -> None:
        """Upload object to storage.

        Args:
            bucket: Bucket name
            key: Object key (path in storage)
            data: File content as bytes
            content_type: MIME type of the content

        Raises:
            ObjectStorageError: If upload fails
        """
        ...

    @abstractmethod
    async def get_object(
        self,
        bucket: str,
        key: str,
    ) -> bytes | None:
        """Download object from storage.

        Args:
            bucket: Bucket name
            key: Object key

        Returns:
            File content as bytes, or None if not found

        Raises:
            ObjectStorageError: If download fails (except not found)
        """
        ...

    @abstractmethod
    async def delete_object(
        self,
        bucket: str,
        key: str,
    ) -> None:
        """Delete object from storage.

        Args:
            bucket: Bucket name
            key: Object key

        Note:
            Does not raise if object doesn't exist (idempotent)
        """
        ...

    @abstractmethod
    async def object_exists(
        self,
        bucket: str,
        key: str,
    ) -> bool:
        """Check if object exists in storage.

        Args:
            bucket: Bucket name
            key: Object key

        Returns:
            True if object exists, False otherwise
        """
        ...

    @abstractmethod
    async def list_objects(
        self,
        bucket: str,
        prefix: str = "",
    ) -> list[str]:
        """List objects in storage with optional prefix filter.

        Args:
            bucket: Bucket name
            prefix: Optional prefix to filter objects (e.g., "repo_id/")

        Returns:
            List of object keys matching the prefix
        """
        ...


class ObjectStorageError(Exception):
    """Base exception for object storage operations."""
    pass


class MinIOClient(ObjectStorageClient):
    """MinIO implementation of ObjectStorageClient.

    Uses sync minio SDK with async wrappers via ThreadPoolExecutor.
    """

    def __init__(
        self,
        endpoint: str | None = None,
        access_key: str | None = None,
        secret_key: str | None = None,
        secure: bool | None = None,
    ):
        """Initialize MinIO client.

        Args:
            endpoint: MinIO endpoint (default from settings)
            access_key: Access key (default from settings)
            secret_key: Secret key (default from settings)
            secure: Use HTTPS (default from settings)
        """
        self._client = Minio(
            endpoint or settings.minio_endpoint,
            access_key=access_key or settings.minio_access_key,
            secret_key=secret_key or settings.minio_secret_key,
            secure=secure if secure is not None else settings.minio_secure,
        )

    def _run_sync(self, func, *args, **kwargs):
        """Run a sync function in the thread pool."""
        loop = asyncio.get_event_loop()
        return loop.run_in_executor(_executor, partial(func, *args, **kwargs))

    async def put_object(
        self,
        bucket: str,
        key: str,
        data: bytes,
        content_type: str = "application/octet-stream",
    ) -> None:
        """Upload object to MinIO."""
        try:
            await self._run_sync(
                self._client.put_object,
                bucket,
                key,
                BytesIO(data),
                len(data),
                content_type=content_type,
            )
            logger.debug(f"Uploaded object: {bucket}/{key} ({len(data)} bytes)")
        except S3Error as e:
            logger.error(f"Failed to upload {bucket}/{key}: {e}")
            raise ObjectStorageError(f"Failed to upload object: {e}") from e
        except Exception as e:
            logger.error(f"Unexpected error uploading {bucket}/{key}: {e}")
            raise ObjectStorageError(f"Failed to upload object: {e}") from e

    async def get_object(
        self,
        bucket: str,
        key: str,
    ) -> bytes | None:
        """Download object from MinIO."""
        try:
            response = await self._run_sync(
                self._client.get_object,
                bucket,
                key,
            )
            try:
                data = response.read()
                logger.debug(f"Downloaded object: {bucket}/{key} ({len(data)} bytes)")
                return data
            finally:
                response.close()
                response.release_conn()
        except S3Error as e:
            if e.code == "NoSuchKey":
                logger.debug(f"Object not found: {bucket}/{key}")
                return None
            logger.error(f"Failed to download {bucket}/{key}: {e}")
            raise ObjectStorageError(f"Failed to download object: {e}") from e
        except Exception as e:
            logger.error(f"Unexpected error downloading {bucket}/{key}: {e}")
            raise ObjectStorageError(f"Failed to download object: {e}") from e

    async def delete_object(
        self,
        bucket: str,
        key: str,
    ) -> None:
        """Delete object from MinIO (idempotent)."""
        try:
            await self._run_sync(
                self._client.remove_object,
                bucket,
                key,
            )
            logger.debug(f"Deleted object: {bucket}/{key}")
        except S3Error as e:
            # MinIO remove_object doesn't raise on missing object,
            # but handle it just in case
            if e.code == "NoSuchKey":
                logger.debug(f"Object already deleted: {bucket}/{key}")
                return
            logger.error(f"Failed to delete {bucket}/{key}: {e}")
            raise ObjectStorageError(f"Failed to delete object: {e}") from e
        except Exception as e:
            logger.error(f"Unexpected error deleting {bucket}/{key}: {e}")
            raise ObjectStorageError(f"Failed to delete object: {e}") from e

    async def object_exists(
        self,
        bucket: str,
        key: str,
    ) -> bool:
        """Check if object exists in MinIO."""
        try:
            await self._run_sync(
                self._client.stat_object,
                bucket,
                key,
            )
            return True
        except S3Error as e:
            if e.code == "NoSuchKey":
                return False
            logger.error(f"Failed to check existence of {bucket}/{key}: {e}")
            raise ObjectStorageError(f"Failed to check object existence: {e}") from e
        except Exception as e:
            logger.error(f"Unexpected error checking {bucket}/{key}: {e}")
            raise ObjectStorageError(f"Failed to check object existence: {e}") from e

    async def list_objects(
        self,
        bucket: str,
        prefix: str = "",
    ) -> list[str]:
        """List objects in MinIO with optional prefix filter."""
        try:
            def _list_objects():
                objects = self._client.list_objects(bucket, prefix=prefix, recursive=True)
                return [obj.object_name for obj in objects]

            result = await self._run_sync(_list_objects)
            logger.debug(f"Listed {len(result)} objects in {bucket}/{prefix}")
            return result
        except S3Error as e:
            logger.error(f"Failed to list objects in {bucket}/{prefix}: {e}")
            raise ObjectStorageError(f"Failed to list objects: {e}") from e
        except Exception as e:
            logger.error(f"Unexpected error listing {bucket}/{prefix}: {e}")
            raise ObjectStorageError(f"Failed to list objects: {e}") from e


# Singleton instance for convenience
_default_client: MinIOClient | None = None


def get_object_storage_client() -> MinIOClient:
    """Get the default object storage client (singleton)."""
    global _default_client
    if _default_client is None:
        _default_client = MinIOClient()
    return _default_client
