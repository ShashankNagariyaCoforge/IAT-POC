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
from azure.storage.blob import generate_blob_sas, BlobSasPermissions, ContentSettings

from config import settings

logger = logging.getLogger(__name__)


class BlobStorageService:
    """Async Azure Blob Storage client."""

    def __init__(self):
        if settings.azure_storage_connection_string:
            self._client = BlobServiceClient.from_connection_string(settings.azure_storage_connection_string)
        elif settings.azure_storage_account_url:
            self._credential = DefaultAzureCredential()
            self._client = BlobServiceClient(
                account_url=settings.azure_storage_account_url,
                credential=self._credential,
            )
        else:
            self._client = None
            logger.warning("No Blob Storage credentials configured. Start will fail if dependent.")

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
        await blob_client.upload_blob(
            data, 
            overwrite=True, 
            content_settings=ContentSettings(content_type=content_type)
        )
        logger.info(f"Uploaded blob: {container_name}/{blob_name} ({len(data)} bytes)")
        return f"{container_name}/{blob_name}"

    async def upload_text(
        self,
        container_name: str,
        blob_name: str,
        text: str,
        content_type: str = "text/plain; charset=utf-8",
    ) -> str:
        """
        Upload a text string as a UTF-8 blob.

        Args:
            container_name: Target container.
            blob_name: Blob name within the container.
            text: Text content to upload.
            content_type: Optional MIME type.

        Returns:
            Full blob path.
        """
        data = text.encode("utf-8")
        return await self.upload_bytes(container_name, blob_name, data, content_type=content_type)

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

    async def list_unprocessed_email_folders(self, container_name: str) -> list[str]:
        """
        List all folder prefixes containing an 'email.json' that do NOT have the 'is_processed' metadata.
        
        Using metadata instead of blob tags due to Hierarchical Namespace (ADLS Gen2) restrictions.
        """
        container = self._client.get_container_client(container_name)
        unprocessed_prefixes = []
        
        async for blob in container.list_blobs(name_starts_with=""):
            if blob.name.endswith("email.json"):
                blob_client = container.get_blob_client(blob.name)
                properties = await blob_client.get_blob_properties()
                metadata = properties.metadata or {}
                
                if metadata.get("is_processed") != "true":
                    # Deduce the folder prefix: e.g. "2026/02/19/timestamp_id"
                    prefix = blob.name.rsplit("/", 1)[0]
                    unprocessed_prefixes.append(prefix)
                    
        return unprocessed_prefixes
        
    async def list_blobs_in_folder(self, container_name: str, folder_prefix: str) -> list[str]:
        """List all blobs immediately within a given folder prefix."""
        container = self._client.get_container_client(container_name)
        blobs = []
        async for blob in container.list_blobs(name_starts_with=folder_prefix + "/"):
            # Exclude subfolders like 'unzipped/' from the main list if needed, 
            # but for this we'll just return all nested paths
            blobs.append(blob.name)
        return blobs

    async def mark_as_processed(self, container_name: str, blob_name: str):
        """Add the `is_processed=true` metadata to a specific blob."""
        container = self._client.get_container_client(container_name)
        blob_client = container.get_blob_client(blob_name)
        
        # Merge existing metadata so we don't wipe them
        properties = await blob_client.get_blob_properties()
        existing_metadata = properties.metadata or {}
        existing_metadata["is_processed"] = "true"
        
        await blob_client.set_blob_metadata(metadata=existing_metadata)
        logger.info(f"Marked blob as processed: {container_name}/{blob_name}")

    async def ensure_containers(self):
        """Ensure all required containers exist."""
        if not self._client:
            return
            
        required_containers = [
            settings.blob_container_raw_emails,
            settings.blob_container_attachments,
            settings.blob_container_extracted_text
        ]
        
        for container_name in required_containers:
            container_client = self._client.get_container_client(container_name)
            if not await container_client.exists():
                await container_client.create_container()
                logger.info(f"Created blob container: {container_name}")
            else:
                logger.debug(f"Blob container already exists: {container_name}")

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
        if self._client:
            await self._client.close()
        if hasattr(self, '_credential'):
            await self._credential.close()
