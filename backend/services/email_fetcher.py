"""
Email Fetcher Service.

Fetches unread emails (and their attachments) from the configured mailbox
via Microsoft Graph API and uploads them to Azure Blob Storage in the format
expected by the sync pipeline:

    {YYYY/MM/DD}/{YYYYMMDD_HHMMSS}_{message_id}/email.json
    {YYYY/MM/DD}/{YYYYMMDD_HHMMSS}_{message_id}/{attachment_name}
    {YYYY/MM/DD}/{YYYYMMDD_HHMMSS}_{message_id}/unzipped/{unzipped_file}

This is Step 0 of the sync flow and runs before the blob-listing pipeline.
"""

import io
import json
import base64
import zipfile
import logging
from datetime import datetime, timezone
from typing import List, Dict

import httpx

from config import settings
from services.graph_client import GraphClient

logger = logging.getLogger(__name__)

GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"


def _guess_content_type(name: str) -> str:
    lname = name.lower()
    mapping = {
        ".json": "application/json",
        ".txt": "text/plain",
        ".log": "text/plain",
        ".csv": "text/csv",
        ".pdf": "application/pdf",
        ".zip": "application/zip",
        ".xml": "application/xml",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    }
    for ext, ctype in mapping.items():
        if lname.endswith(ext):
            return ctype
    return "application/octet-stream"


class EmailFetcherService:
    """
    Fetches unread emails from the inbox via Graph API and uploads them
    to Azure Blob Storage so the existing sync pipeline can process them.
    """

    def __init__(self):
        self._graph = GraphClient()
        self._mailbox = settings.target_mailbox
        self._container = settings.blob_container_raw_emails
        self._connection_string = settings.azure_storage_connection_string

    def _get_blob_client(self, blob_path: str):
        """Create a BlobClient for the given path using the connection string."""
        from azure.storage.blob import BlobServiceClient, ContentSettings
        blob_service = BlobServiceClient.from_connection_string(self._connection_string)
        return blob_service.get_blob_client(container=self._container, blob=blob_path)

    def _upload_bytes(self, blob_path: str, data: bytes, overwrite: bool = True) -> None:
        """Upload raw bytes to blob storage."""
        from azure.storage.blob import ContentSettings
        blob_client = self._get_blob_client(blob_path)
        content_settings = ContentSettings(content_type=_guess_content_type(blob_path))
        blob_client.upload_blob(data, overwrite=overwrite, content_settings=content_settings)
        logger.debug(f"[EmailFetcher] Uploaded: {blob_path}")

    def _upload_text(self, blob_path: str, text: str) -> None:
        """Upload UTF-8 text to blob storage."""
        self._upload_bytes(blob_path, text.encode("utf-8"))

    async def _fetch_unread_emails(self, token: str) -> List[Dict]:
        """Fetch unread emails with attachments expanded."""
        if not self._mailbox:
            raise RuntimeError("target_mailbox is not configured in settings.")

        url = (
            f"{GRAPH_BASE_URL}/users/{self._mailbox}/mailFolders/inbox/messages"
            "?$filter=isRead eq false"
            "&$expand=attachments"
            "&$top=50"
        )
        headers = {"Authorization": f"Bearer {token}"}
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            return response.json().get("value", [])

    async def _mark_as_read(self, token: str, message_id: str) -> None:
        """Mark a message as read."""
        url = f"{GRAPH_BASE_URL}/users/{self._mailbox}/messages/{message_id}"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.patch(url, headers=headers, json={"isRead": True})
            response.raise_for_status()

    def _save_email_metadata(self, email: Dict, base_blob_folder: str) -> None:
        """Build and upload email.json to the blob folder."""
        metadata = {
            "subject": email.get("subject"),
            "from": email.get("from", {}).get("emailAddress", {}).get("address"),
            "to": [
                r.get("emailAddress", {}).get("address")
                for r in (email.get("toRecipients") or [])
            ],
            "cc": [
                r.get("emailAddress", {}).get("address")
                for r in (email.get("ccRecipients") or [])
            ],
            "receivedDateTime": email.get("receivedDateTime"),
            "messageId": email.get("id"),
            "internetMessageId": email.get("internetMessageId"),
            "conversationId": email.get("conversationId"),
            "bodyPreview": email.get("bodyPreview"),
            "body": email.get("body", {}).get("content"),
            "hasAttachments": email.get("hasAttachments"),
        }
        blob_path = f"{base_blob_folder}/email.json"
        self._upload_text(blob_path, json.dumps(metadata, indent=4))
        logger.info(f"[EmailFetcher] Saved email metadata: {blob_path}")

    def _save_attachments(self, email: Dict, base_blob_folder: str) -> None:
        """Upload attachments (and unzip any ZIP files) to blob storage."""
        attachments = email.get("attachments") or []
        for att in attachments:
            if att.get("@odata.type") != "#microsoft.graph.fileAttachment":
                continue

            file_name = att["name"]
            file_bytes = base64.b64decode(att.get("contentBytes", ""))
            blob_path = f"{base_blob_folder}/{file_name}"
            self._upload_bytes(blob_path, file_bytes)
            logger.info(f"[EmailFetcher] Uploaded attachment: {blob_path}")

            # If ZIP → unzip each member in-memory and upload
            if file_name.lower().endswith(".zip"):
                unzip_prefix = f"{base_blob_folder}/unzipped"
                try:
                    with zipfile.ZipFile(io.BytesIO(file_bytes)) as zf:
                        for member in zf.infolist():
                            if member.is_dir():
                                continue
                            extracted = zf.read(member.filename)
                            clean_name = member.filename.replace("\\", "/").lstrip("/")
                            upload_path = f"{unzip_prefix}/{clean_name}"
                            self._upload_bytes(upload_path, extracted)
                            logger.info(f"[EmailFetcher] Uploaded unzipped: {upload_path}")
                except zipfile.BadZipFile:
                    logger.warning(f"[EmailFetcher] Could not unzip {file_name} — skipping unzip step.")

    async def fetch_and_upload(self) -> int:
        """
        Main entry point: fetch all unread emails and upload them to blob storage.

        Returns:
            Number of emails successfully fetched and uploaded.
        """
        if not self._connection_string:
            raise RuntimeError(
                "AZURE_STORAGE_CONNECTION_STRING is not configured. "
                "Email fetching requires blob storage access."
            )

        logger.info("[EmailFetcher] Starting inbox fetch...")
        token = await self._graph._get_access_token()
        emails = await self._fetch_unread_emails(token)

        if not emails:
            logger.info("[EmailFetcher] No unread emails found in inbox.")
            return 0

        logger.info(f"[EmailFetcher] Found {len(emails)} unread email(s).")
        fetched_count = 0

        for email in emails:
            message_id = email.get("id", "unknown")
            subject = email.get("subject", "(No Subject)")
            try:
                # Build folder path:  YYYY/MM/DD/YYYYMMDD_HHMMSS_{message_id}
                dt_str = email.get("receivedDateTime") or datetime.now(timezone.utc).isoformat()
                try:
                    dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
                except Exception:
                    dt = datetime.now(timezone.utc)

                partition_prefix = dt.strftime("%Y/%m/%d")
                timestamp = dt.strftime("%Y%m%d_%H%M%S")
                base_blob_folder = f"{partition_prefix}/{timestamp}_{message_id}"

                # Upload email metadata + attachments
                self._save_email_metadata(email, base_blob_folder)
                self._save_attachments(email, base_blob_folder)

                # Mark as read so it's not fetched again next sync
                await self._mark_as_read(token, message_id)

                fetched_count += 1
                logger.info(f"[EmailFetcher] ✅ Processed email: '{subject}' → {base_blob_folder}")

            except Exception as e:
                logger.error(f"[EmailFetcher] ❌ Failed to process email '{subject}' ({message_id}): {e}", exc_info=True)

        logger.info(f"[EmailFetcher] Done. {fetched_count}/{len(emails)} emails uploaded to blob.")
        return fetched_count
