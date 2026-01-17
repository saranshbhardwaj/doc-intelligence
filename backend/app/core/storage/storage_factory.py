"""Storage backend abstraction for documents and templates.

Provides a unified interface for storing files in either Cloudflare R2 or local filesystem.
Enables gradual migration from local storage to cloud storage without breaking existing code.
"""

import os
import shutil
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

from app.config import settings
from app.core.storage.cloudflare_r2 import CloudflareR2Storage, get_r2_storage
from app.utils.logging import logger


class StorageBackend(ABC):
    """Abstract base class for storage backends."""

    @abstractmethod
    def upload(self, local_path: str, storage_key: str) -> str:
        """
        Upload a file to storage.

        Args:
            local_path: Path to local file to upload
            storage_key: Storage key/path (e.g., "documents/user123/doc456.pdf")

        Returns:
            Storage key where file was stored

        Raises:
            FileNotFoundError: If local_path doesn't exist
            Exception: On upload failure
        """
        pass

    @abstractmethod
    def download(self, storage_key: str, local_path: str) -> None:
        """
        Download a file from storage to local path.

        Args:
            storage_key: Storage key/path
            local_path: Local path to save downloaded file

        Raises:
            FileNotFoundError: If storage_key doesn't exist
            Exception: On download failure
        """
        pass

    @abstractmethod
    def generate_presigned_url(self, storage_key: str, expiry_seconds: int = 3600) -> str:
        """
        Generate a time-limited URL for accessing a file.

        Args:
            storage_key: Storage key/path
            expiry_seconds: URL expiration time in seconds

        Returns:
            Presigned URL (for R2) or relative path (for local)

        Raises:
            FileNotFoundError: If storage_key doesn't exist
            Exception: On URL generation failure
        """
        pass

    @abstractmethod
    def exists(self, storage_key: str) -> bool:
        """
        Check if a file exists in storage.

        Args:
            storage_key: Storage key/path

        Returns:
            True if file exists, False otherwise
        """
        pass

    @abstractmethod
    def delete(self, storage_key: str) -> None:
        """
        Delete a file from storage.

        Args:
            storage_key: Storage key/path

        Note:
            Should not raise if file doesn't exist (idempotent)
        """
        pass

    @abstractmethod
    def get_storage_type(self) -> str:
        """Return storage backend type ('r2' or 'local')."""
        pass


class R2StorageBackend(StorageBackend):
    """Cloudflare R2 storage backend (S3-compatible)."""

    def __init__(self, r2_client: Optional[CloudflareR2Storage] = None):
        """
        Initialize R2 storage backend.

        Args:
            r2_client: Optional pre-configured R2 client. If not provided,
                      will use get_r2_storage() singleton.
        """
        self.r2 = r2_client or get_r2_storage()

    def upload(self, local_path: str, storage_key: str) -> str:
        """Upload file to R2."""
        if not os.path.exists(local_path):
            raise FileNotFoundError(f"Local file not found: {local_path}")

        try:
            # Read file bytes
            with open(local_path, "rb") as f:
                file_bytes = f.read()

            # Determine content type
            content_type = self._get_content_type(local_path)

            # Store in R2 (returns presigned URL, but we only need the key)
            self.r2.store_bytes(storage_key, file_bytes, content_type)

            logger.info(f"Uploaded file to R2: {storage_key}")
            return storage_key

        except Exception as e:
            logger.error(f"Failed to upload to R2: {storage_key}", exc_info=True)
            raise

    def download(self, storage_key: str, local_path: str) -> None:
        """Download file from R2."""
        try:
            # Get file bytes from R2
            file_bytes = self.r2.get_bytes(storage_key)

            # Ensure parent directory exists
            os.makedirs(os.path.dirname(local_path), exist_ok=True)

            # Write to local file
            with open(local_path, "wb") as f:
                f.write(file_bytes)

            logger.info(f"Downloaded file from R2: {storage_key} -> {local_path}")

        except FileNotFoundError:
            logger.error(f"File not found in R2: {storage_key}")
            raise
        except Exception as e:
            logger.error(f"Failed to download from R2: {storage_key}", exc_info=True)
            raise

    def generate_presigned_url(self, storage_key: str, expiry_seconds: int = 3600) -> str:
        """Generate presigned URL for R2 object."""
        try:
            if not self.exists(storage_key):
                raise FileNotFoundError(f"File not found in R2: {storage_key}")

            url = self.r2.generate_url(storage_key)
            logger.info(f"Generated presigned URL for: {storage_key}")
            return url

        except FileNotFoundError:
            raise
        except Exception as e:
            logger.error(f"Failed to generate presigned URL: {storage_key}", exc_info=True)
            raise

    def exists(self, storage_key: str) -> bool:
        """Check if file exists in R2."""
        return self.r2.exists(storage_key)

    def delete(self, storage_key: str) -> None:
        """Delete file from R2."""
        self.r2.delete(storage_key)
        logger.info(f"Deleted file from R2: {storage_key}")

    def get_storage_type(self) -> str:
        """Return 'r2'."""
        return "r2"

    def _get_content_type(self, file_path: str) -> str:
        """Determine content type from file extension."""
        extension = Path(file_path).suffix.lower()
        content_types = {
            ".pdf": "application/pdf",
            ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ".xlsm": "application/vnd.ms-excel.sheet.macroEnabled.12",
            ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ".json": "application/json",
            ".txt": "text/plain",
        }
        return content_types.get(extension, "application/octet-stream")


class LocalFilesystemBackend(StorageBackend):
    """Local filesystem storage backend."""

    def __init__(self, base_path: str = "backend/uploads"):
        """
        Initialize local filesystem backend.

        Args:
            base_path: Base directory for storing files (default: backend/uploads)
        """
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)

    def upload(self, local_path: str, storage_key: str) -> str:
        """Copy file to local storage directory."""
        if not os.path.exists(local_path):
            raise FileNotFoundError(f"Local file not found: {local_path}")

        try:
            # Convert storage key to filesystem path
            target_path = self.base_path / storage_key

            # Ensure parent directory exists
            target_path.parent.mkdir(parents=True, exist_ok=True)

            # Copy file
            shutil.copy2(local_path, target_path)

            logger.info(f"Uploaded file to local storage: {storage_key}")
            return storage_key

        except Exception as e:
            logger.error(f"Failed to upload to local storage: {storage_key}", exc_info=True)
            raise

    def download(self, storage_key: str, local_path: str) -> None:
        """Copy file from local storage to target path."""
        source_path = self.base_path / storage_key

        if not source_path.exists():
            raise FileNotFoundError(f"File not found in local storage: {storage_key}")

        try:
            # Ensure parent directory exists
            os.makedirs(os.path.dirname(local_path), exist_ok=True)

            # Copy file
            shutil.copy2(source_path, local_path)

            logger.info(f"Downloaded file from local storage: {storage_key} -> {local_path}")

        except Exception as e:
            logger.error(f"Failed to download from local storage: {storage_key}", exc_info=True)
            raise

    def generate_presigned_url(self, storage_key: str, expiry_seconds: int = 3600) -> str:
        """
        Return local file path (no presigned URLs for local storage).

        Note: For local storage, this returns the actual file path.
        The API endpoint will handle streaming the file directly.
        """
        file_path = self.base_path / storage_key

        if not file_path.exists():
            raise FileNotFoundError(f"File not found in local storage: {storage_key}")

        # Return absolute path
        return str(file_path.absolute())

    def exists(self, storage_key: str) -> bool:
        """Check if file exists in local storage."""
        file_path = self.base_path / storage_key
        return file_path.exists()

    def delete(self, storage_key: str) -> None:
        """Delete file from local storage."""
        file_path = self.base_path / storage_key

        try:
            if file_path.exists():
                file_path.unlink()
                logger.info(f"Deleted file from local storage: {storage_key}")
            else:
                logger.warning(f"Attempted to delete non-existent file: {storage_key}")

        except Exception as e:
            logger.error(f"Failed to delete from local storage: {storage_key}", exc_info=True)
            raise

    def get_storage_type(self) -> str:
        """Return 'local'."""
        return "local"


def get_storage_backend(force_type: Optional[str] = None) -> StorageBackend:
    """
    Get the configured storage backend.

    Args:
        force_type: Optional override for storage type ('r2' or 'local').
                   If not provided, uses settings.use_r2_for_documents.

    Returns:
        StorageBackend instance (either R2 or local filesystem)

    Raises:
        RuntimeError: If R2 is requested but not configured
    """
    # Determine storage type
    if force_type:
        use_r2 = (force_type == "r2")
    else:
        use_r2 = getattr(settings, "use_r2_for_documents", False)

    if use_r2:
        try:
            backend = R2StorageBackend()
            logger.info("Using R2 storage backend for documents")
            return backend
        except RuntimeError as e:
            logger.warning(f"R2 storage not configured: {e}. Falling back to local filesystem.")
            backend = LocalFilesystemBackend()
            logger.info("Using local filesystem storage backend for documents")
            return backend
    else:
        backend = LocalFilesystemBackend()
        logger.info("Using local filesystem storage backend for documents")
        return backend


def is_legacy_path(file_path: str) -> bool:
    """
    Check if a file path is a legacy local path (not R2 storage key).

    Args:
        file_path: File path or storage key

    Returns:
        True if legacy local path, False if R2 storage key
    """
    # R2 storage keys start with specific prefixes
    r2_prefixes = ["documents/", "templates/", "fills/"]

    return not any(file_path.startswith(prefix) for prefix in r2_prefixes)


__all__ = [
    "StorageBackend",
    "R2StorageBackend",
    "LocalFilesystemBackend",
    "get_storage_backend",
    "is_legacy_path",
]
