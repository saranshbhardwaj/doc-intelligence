"""Cloudflare R2 storage service (S3-compatible) for exporting workflow artifacts.

Implements a minimal interface for storing bytes and generating a presigned URL.
"""
from __future__ import annotations
import boto3
from botocore.client import Config
from botocore.exceptions import ClientError
from typing import Optional
from app.config import settings
from app.utils.logging import logger


class CloudflareR2Storage:
    def __init__(self, *, access_key_id: str, secret_access_key: str, endpoint_url: str, bucket: str, presign_expiry: int = 3600):
        self.bucket = bucket
        self.presign_expiry = presign_expiry
        # region_name can be 'auto' for R2; disable signature version guessing
        self.client = boto3.client(
            's3',
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
            region_name='auto',
            config=Config(signature_version='s3v4')
        )

    def store_bytes(self, key: str, data: bytes, content_type: str) -> str:
        """Store bytes at key and return a presigned GET URL."""
        try:
            self.client.put_object(Bucket=self.bucket, Key=key, Body=data, ContentType=content_type)
            url = self.client.generate_presigned_url(
                'get_object',
                Params={'Bucket': self.bucket, 'Key': key},
                ExpiresIn=self.presign_expiry
            )
            logger.info("Stored export in R2", extra={"bucket": self.bucket, "key": key})
            return url
        except Exception as e:
            logger.exception("Failed to store bytes in R2", extra={"bucket": self.bucket, "key": key})
            raise

    def get_bytes(self, key: str) -> bytes:
        """Get object bytes from R2."""
        try:
            resp = self.client.get_object(Bucket=self.bucket, Key=key)
            data = resp['Body'].read()
            logger.info("Retrieved object from R2", extra={"bucket": self.bucket, "key": key})
            return data
        except ClientError as e:
            if e.response['Error']['Code'] == 'NoSuchKey':
                logger.error("Object not found in R2", extra={"bucket": self.bucket, "key": key})
                raise FileNotFoundError(f"Object not found in R2: {key}") from e
            logger.exception("Failed to retrieve object from R2", extra={"bucket": self.bucket, "key": key})
            raise
        except Exception as e:
            logger.exception("Failed to retrieve object from R2", extra={"bucket": self.bucket, "key": key})
            raise

    def generate_url(self, key: str) -> str:
        """Generate a presigned URL for an existing object."""
        try:
            url = self.client.generate_presigned_url(
                'get_object',
                Params={'Bucket': self.bucket, 'Key': key},
                ExpiresIn=self.presign_expiry
            )
            logger.info("Generated presigned URL for R2 object", extra={"bucket": self.bucket, "key": key})
            return url
        except Exception as e:
            logger.exception("Failed to generate presigned URL", extra={"bucket": self.bucket, "key": key})
            raise

    def delete(self, key: str) -> None:
        """Delete object from R2. Gracefully handles non-existent objects."""
        try:
            self.client.delete_object(Bucket=self.bucket, Key=key)
            logger.info("Deleted object from R2", extra={"bucket": self.bucket, "key": key})
        except ClientError as e:
            if e.response['Error']['Code'] == 'NoSuchKey':
                # Object doesn't exist - log warning but don't raise
                logger.warning("Attempted to delete non-existent object from R2", extra={"bucket": self.bucket, "key": key})
            else:
                logger.exception("Failed to delete object from R2", extra={"bucket": self.bucket, "key": key})
                raise
        except Exception as e:
            logger.exception("Failed to delete object from R2", extra={"bucket": self.bucket, "key": key})
            raise

    def exists(self, key: str) -> bool:
        """Check if an object exists in R2."""
        try:
            self.client.head_object(Bucket=self.bucket, Key=key)
            return True
        except ClientError as e:
            if e.response['Error']['Code'] == '404':
                return False
            logger.exception("Failed to check if object exists in R2", extra={"bucket": self.bucket, "key": key})
            raise
        except Exception as e:
            logger.exception("Failed to check if object exists in R2", extra={"bucket": self.bucket, "key": key})
            raise


_R2_CACHE: Optional[CloudflareR2Storage] = None


def get_r2_storage() -> CloudflareR2Storage:
    """Get or create a singleton CloudflareR2Storage instance."""
    global _R2_CACHE
    if _R2_CACHE is None:
        if not (settings.r2_access_key_id and settings.r2_secret_access_key and settings.r2_bucket and settings.r2_endpoint_url):
            raise RuntimeError("R2 storage not configured")
        _R2_CACHE = CloudflareR2Storage(
            access_key_id=settings.r2_access_key_id,
            secret_access_key=settings.r2_secret_access_key,
            endpoint_url=settings.r2_endpoint_url,
            bucket=settings.r2_bucket,
            presign_expiry=settings.r2_presign_expiry,
        )
    return _R2_CACHE


__all__ = ["CloudflareR2Storage", "get_r2_storage"]