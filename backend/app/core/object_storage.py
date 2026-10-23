"""
Cloudflare R2 / S3-compatible Object Storage service for TrustVault.

Provides persistent, encrypted, durable document storage across server
restarts and deployments. Files are organized by owner ID prefix:
    {owner_id}/{uuid}{extension}

If R2 credentials are not configured (e.g. local offline development or unit tests),
storage operations fall back to the local private filesystem directory.
In production (APP_ENV == "production"), R2 configuration is strictly required
and missing credentials will raise a configuration error.
"""

import asyncio
import logging
from pathlib import Path
from typing import Any

from app.core.config import settings

logger = logging.getLogger("trustvault.storage")

_r2_client = None


def is_r2_configured(settings_obj=None) -> bool:
    """
    Return True only if Cloudflare R2 / S3 credentials and bucket are configured with non-empty strings,
    or if is_r2_configured is explicitly set to boolean True on settings.
    Handles settings mock instances safely in unit tests.
    """
    cfg = settings_obj if settings_obj is not None else settings
    flag = getattr(cfg, "is_r2_configured", None)
    if flag is True:
        return True
    if flag is False:
        return False

    account_id = getattr(cfg, "R2_ACCOUNT_ID", None)
    endpoint = getattr(cfg, "R2_ENDPOINT_URL", None)
    access_key = getattr(cfg, "R2_ACCESS_KEY_ID", None)
    secret_key = getattr(cfg, "R2_SECRET_ACCESS_KEY", None)
    bucket = getattr(cfg, "R2_BUCKET_NAME", None)

    has_target = (isinstance(account_id, str) and bool(account_id.strip())) or (
        isinstance(endpoint, str) and bool(endpoint.strip())
    )
    return bool(
        has_target
        and isinstance(access_key, str) and bool(access_key.strip())
        and isinstance(secret_key, str) and bool(secret_key.strip())
        and isinstance(bucket, str) and bool(bucket.strip())
    )


def get_r2_client():
    """Return a cached or new boto3 S3 client configured for Cloudflare R2 / S3."""
    global _r2_client
    if _r2_client is not None:
        return _r2_client

    import boto3
    from botocore.config import Config

    endpoint_url = getattr(settings, "R2_ENDPOINT_URL", "")
    account_id = getattr(settings, "R2_ACCOUNT_ID", "")
    if not endpoint_url and account_id:
        endpoint_url = f"https://{account_id}.r2.cloudflarestorage.com"

    boto_config = Config(
        retries={"max_attempts": 3, "mode": "standard"},
        connect_timeout=5,
        read_timeout=15,
    )

    _r2_client = boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        aws_access_key_id=getattr(settings, "R2_ACCESS_KEY_ID", ""),
        aws_secret_access_key=getattr(settings, "R2_SECRET_ACCESS_KEY", ""),
        region_name="auto",
        config=boto_config,
    )
    return _r2_client


def _resolve_local_root() -> Path:
    storage_root = Path(getattr(settings, "STORAGE_PATH", "storage"))
    if not storage_root.is_absolute():
        storage_root = Path(__file__).resolve().parent.parent.parent / getattr(settings, "STORAGE_PATH", "storage")
    storage_root.mkdir(parents=True, exist_ok=True)
    return storage_root


def _sync_upload_r2(object_key: str, content: bytes, content_type: str) -> None:
    client = get_r2_client()
    bucket_name = getattr(settings, "R2_BUCKET_NAME", "trustvault-documents")
    client.put_object(
        Bucket=bucket_name,
        Key=object_key,
        Body=content,
        ContentType=content_type,
    )


def _sync_download_r2(object_key: str) -> bytes:
    client = get_r2_client()
    bucket_name = getattr(settings, "R2_BUCKET_NAME", "trustvault-documents")
    resp = client.get_object(
        Bucket=bucket_name,
        Key=object_key,
    )
    return resp["Body"].read()


def _sync_delete_r2(object_key: str) -> None:
    client = get_r2_client()
    bucket_name = getattr(settings, "R2_BUCKET_NAME", "trustvault-documents")
    client.delete_object(
        Bucket=bucket_name,
        Key=object_key,
    )


async def upload_to_r2(object_key: str, content: bytes, content_type: str) -> None:
    """
    Persist document content to Cloudflare R2 object storage (or local fallback in dev).
    Executes in a worker thread to prevent blocking FastAPI's async event loop.
    """
    if is_r2_configured():
        await asyncio.to_thread(_sync_upload_r2, object_key, content, content_type)
        return

    if getattr(settings, "APP_ENV", "") == "production":
        raise RuntimeError(
            "Cloudflare R2 object storage is required in production, but credentials are not configured."
        )

    # Local fallback for development/testing without cloud credentials
    local_path = _resolve_local_root() / object_key
    local_path.parent.mkdir(parents=True, exist_ok=True)
    await asyncio.to_thread(local_path.write_bytes, content)


async def download_from_r2(storage_path_or_key: str) -> bytes:
    """
    Retrieve document content from Cloudflare R2 (or local fallback in dev).
    Raises FileNotFoundError if object does not exist.
    """
    if is_r2_configured():
        try:
            return await asyncio.to_thread(_sync_download_r2, storage_path_or_key)
        except Exception as exc:
            # Check if a local file exists (legacy migration support)
            local_file = Path(storage_path_or_key)
            if local_file.is_file():
                return await asyncio.to_thread(local_file.read_bytes)
            candidate = _resolve_local_root() / storage_path_or_key
            if candidate.is_file():
                return await asyncio.to_thread(candidate.read_bytes)
                
            raise FileNotFoundError(f"Document {storage_path_or_key} not found.") from exc

    # Local fallback
    local_file = Path(storage_path_or_key)
    if not local_file.is_file():
        candidate = _resolve_local_root() / storage_path_or_key
        if candidate.is_file():
            local_file = candidate
        else:
            raise FileNotFoundError(f"Document file {storage_path_or_key} not found.")

    return await asyncio.to_thread(local_file.read_bytes)


async def delete_from_r2(storage_path_or_key: str) -> None:
    """
    Delete document content from Cloudflare R2 object storage.
    Errors are suppressed or logged safely to ensure soft-deletion proceeds.
    Does NOT touch the local filesystem (handled with strict authorization by endpoint).
    """
    if is_r2_configured():
        try:
            await asyncio.to_thread(_sync_delete_r2, storage_path_or_key)
        except Exception as exc:
            logger.warning("Failed to delete object %s from R2: %s", storage_path_or_key, exc)


upload_to_storage = upload_to_r2
download_from_storage = download_from_r2
delete_from_storage = delete_from_r2
