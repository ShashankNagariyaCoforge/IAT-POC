"""
Azure Blob Storage service.
Handles upload and download of:
  - raw-emails: email metadata JSON
  - raw-attachments: attachment binary files
  - extracted-text: parsed and OCR-extracted text blobs
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from azure.identity.aio import DefaultAzureCredential
from azure.storage.blob.aio import BlobServiceClient
from azure.storage.blob import generate_blob_sas, BlobSasPermissions

from config import settings

logger = logging.getLogger(__name__)


class BlobStorageService:
    """Async Azure Blob Storage client."""

    def __init__(self):
        self._credential = DefaultAzureCredential()
        self._client = BlobServiceClient(
            account_url=settings.azure_storage_account_url,
            credential=self._credential,
        )

    async def upload_bytes(
        self,
        container_name: str,
        blob_name: str,
        data: bytes,
        content_type: str = "application/octet-stream",
    ) -> str:
        """
        Upload raw bytes to blob storage.

        Args:
            container_name: Target container (e.g. "raw-emails").
            blob_name: Blob path/name inside the container.
            data: Bytes to upload.
            content_type: MIME type of the content.

        Returns:
            Full blob path (container/blob_name) for reference.
        """
        container = self._client.get_container_client(container_name)
        blob_client = container.get_blob_client(blob_name)
        await blob_client.upload_blob(data, overwrite=True, content_settings={"content_type": content_type})
        logger.info(f"Uploaded blob: {container_name}/{blob_name} ({len(data)} bytes)")
        return f"{container_name}/{blob_name}"

    async def upload_text(
        self,
        container_name: str,
        blob_name: str,
        text: str,
    ) -> str:
        """
        Upload a text string as a UTF-8 blob.

        Args:
            container_name: Target container.
            blob_name: Blob name within the container.
            text: Text content to upload.

        Returns:
            Full blob path.
        """
        data = text.encode("utf-8")
        return await self.upload_bytes(container_name, blob_name, data, content_type="text/plain; charset=utf-8")

    async def download_bytes(self, container_name: str, blob_name: str) -> bytes:
        """
        Download a blob as bytes.

        Args:
            container_name: Source container.
            blob_name: Blob name within the container.

        Returns:
            Raw bytes of the blob content.
        """
        container = self._client.get_container_client(container_name)
        blob_client = container.get_blob_client(blob_name)
        stream = await blob_client.download_blob()
        data = await stream.readall()
        logger.debug(f"Downloaded blob: {container_name}/{blob_name} ({len(data)} bytes)")
        return data

    async def download_text(self, container_name: str, blob_name: str) -> str:
        """
        Download a text blob and decode as UTF-8.

        Args:
            container_name: Source container.
            blob_name: Blob name.

        Returns:
            Decoded string content.
        """
        data = await self.download_bytes(container_name, blob_name)
        return data.decode("utf-8")

    async def blob_exists(self, container_name: str, blob_name: str) -> bool:
        """Check if a blob exists."""
        container = self._client.get_container_client(container_name)
        blob_client = container.get_blob_client(blob_name)
        return await blob_client.exists()

    def build_blob_name(self, case_id: str, filename: str, prefix: str = "") -> str:
        """
        Build a consistent blob name with case_id and timestamp.

        Args:
            case_id: The case identifier.
            filename: Original filename.
            prefix: Optional sub-directory prefix.

        Returns:
            Blob name e.g. "IAT-2026-000001/2026-02-25T12-00-00/attachment.pdf"
        """
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S")
        parts = [case_id, ts]
        if prefix:
            parts.append(prefix)
        parts.append(filename)
        return "/".join(parts)

    async def close(self):
        """Close the blob service client."""
        await self._client.close()
        await self._credential.close()
