"""
Blob Client — thin wrapper over existing BlobStorageService for pipeline v2.
Uploads go to the v2 container. Downloads can come from any existing container.
"""

import logging
from typing import Optional

from services.blob_storage import BlobStorageService
from pipeline_v2.config import v2_settings

logger = logging.getLogger(__name__)

_svc: Optional[BlobStorageService] = None


def _get_svc() -> BlobStorageService:
    global _svc
    if _svc is None:
        _svc = BlobStorageService()
    return _svc


async def upload_bytes(blob_name: str, data: bytes, content_type: str = "application/octet-stream") -> str:
    """Upload bytes to the v2 container. Returns full blob path."""
    return await _get_svc().upload_bytes(v2_settings.v2_blob_container_name, blob_name, data, content_type)


async def upload_text(blob_name: str, text: str, content_type: str = "text/plain; charset=utf-8") -> str:
    """Upload text to the v2 container."""
    return await _get_svc().upload_text(v2_settings.v2_blob_container_name, blob_name, text, content_type)


async def download_bytes(container: str, blob_name: str) -> bytes:
    """Download from any container (used to read existing attachments)."""
    return await _get_svc().download_bytes(container, blob_name)


async def download_bytes_multi_container(blob_path: str, containers: list) -> tuple:
    """
    Try downloading blob_path from each container in order.
    Returns (bytes, container_name) or raises the last exception.
    """
    svc = _get_svc()
    last_err = None
    for container in containers:
        try:
            data = await svc.download_bytes(container, blob_path)
            return data, container
        except Exception as e:
            last_err = e
    # Last fallback: blob_path might be "container/blob"
    if "/" in blob_path:
        c, b = blob_path.split("/", 1)
        try:
            data = await svc.download_bytes(c, b)
            return data, c
        except Exception as e:
            last_err = e
    raise last_err or Exception(f"Blob not found: {blob_path}")


async def ensure_v2_container():
    """Create the v2 blob container if it doesn't exist."""
    svc = _get_svc()
    if not svc._client:
        return
    container_client = svc._client.get_container_client(v2_settings.v2_blob_container_name)
    if not await container_client.exists():
        await container_client.create_container()
        logger.info(f"Created v2 blob container: {v2_settings.v2_blob_container_name}")
