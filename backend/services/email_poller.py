"""
Email Auto-Poller Service

Runs the email sync pipeline on a configurable interval (default: 10s).
Shared by both the background polling task (auto) and the manual /api/cases/sync endpoint.
A threading.Lock prevents concurrent runs — if one sync is already in progress,
the next poll iteration is simply skipped.
"""

import asyncio
import logging

logger = logging.getLogger(__name__)

# Prevent concurrent sync runs
_sync_lock = asyncio.Lock()


async def run_email_sync_pipeline() -> dict:
    """
    Core email sync pipeline — callable by both the HTTP endpoint
    and the background auto-polling task.

    Returns a dict: {new_cases_processed, failed, message}
    Raises: HTTPException on config errors, generic Exception on pipeline errors.
    """
    from config import settings
    from services.blob_storage import BlobStorageService
    from services.classifier import Classifier
    from services.content_safety import ContentSafetyService
    from services.email_fetcher import EmailFetcherService
    from services.document_parser import DocumentParser
    from fastapi import HTTPException
    import json, uuid
    from datetime import datetime

    def _get_db():
        if settings.demo_mode:
            from services.local_db import LocalDBService
            return LocalDBService()
        from services.cosmos_db import CosmosDBService
        return CosmosDBService()

    blob_service = BlobStorageService()
    db_service = _get_db()
    classifier = Classifier()
    parser = DocumentParser()
    safety_svc = ContentSafetyService()

    # ── Step 0: Validate credentials ──────────────────────────────────────────
    missing = []
    if not settings.graph_client_id or not settings.graph_tenant_id or not settings.graph_client_secret:
        missing.append("GRAPH_CLIENT_ID / GRAPH_TENANT_ID / GRAPH_CLIENT_SECRET")
    if not settings.target_mailbox:
        missing.append("TARGET_MAILBOX")
    if not settings.azure_storage_connection_string:
        missing.append("AZURE_STORAGE_CONNECTION_STRING")

    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"Email sync not configured. Missing: {', '.join(missing)}"
        )

    # ── Step 0: Fetch new emails from mailbox → blob ───────────────────────────
    try:
        fetcher = EmailFetcherService()
        emails_fetched = await fetcher.fetch_and_upload()
        logger.info(f"[Poller] Fetched {emails_fetched} new email(s) from mailbox.")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Poller] Email fetch failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to fetch emails: {e}")

    # ── Step 1: Process unprocessed blob folders ───────────────────────────────
    success_count = 0
    failure_count = 0

    try:
        container = settings.blob_container_raw_emails
        unprocessed_folders = await blob_service.list_unprocessed_email_folders(container)

        if not unprocessed_folders:
            return {
                "new_cases_processed": 0,
                "failed": 0,
                "message": f"Fetched {emails_fetched} email(s). No unprocessed folders found.",
            }

        logger.info(f"[Poller] Processing {len(unprocessed_folders)} folder(s).")

        for folder in unprocessed_folders:
            case_id = None
            try:
                email_json_path = f"{folder}/email.json"
                email_text = await blob_service.download_text(container, email_json_path)
                email_data = json.loads(email_text)

                from services.case_manager import CaseManager
                case_mgr = CaseManager(db_service)
                case_id = await case_mgr.resolve_case(email_data)

                email_record = {
                    "email_id": str(uuid.uuid4()),
                    "case_id": case_id,
                    "message_id": email_data.get("messageId") or email_data.get("internetMessageId") or "unknown",
                    "sender": email_data.get("from", "unknown"),
                    "recipient": ", ".join(email_data.get("to", [])),
                    "subject": email_data.get("subject", "No Subject"),
                    "body_masked": "",
                    "received_at": email_data.get("receivedDateTime", datetime.utcnow().isoformat()),
                    "has_attachments": email_data.get("hasAttachments", False),
                }
                await db_service.create_email(email_record)

                blobs_in_folder = await blob_service.list_blobs_in_folder(container, folder)
                attachment_paths = [b for b in blobs_in_folder if b != email_json_path and "/unzipped/" not in b]

                combined_text = email_data.get("body", "") + " \n\n "
                SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".doc", ".xlsx", ".xls", ".txt", ".csv", ".png", ".jpg", ".jpeg", ".gif"}
                
                attachment_count = 0
                for att_path in attachment_paths:
                    att_filename = att_path.split("/")[-1]
                    ext = "." + att_filename.rsplit(".", 1)[-1].lower() if "." in att_filename else ""
                    
                    if ext not in SUPPORTED_EXTENSIONS:
                        logger.info(f"[Poller] Skipping unsupported extension: {att_filename}")
                        continue
                        
                    att_bytes = await blob_service.download_bytes(container, att_path)
                    
                    # Size filter for images (signature icons/tracking pixels are usually < 10KB)
                    if ext in {".png", ".jpg", ".jpeg", ".gif"} and len(att_bytes) < 10240:
                        logger.info(f"[Poller] Skipping small image (likely signature icon): {att_filename} ({len(att_bytes)} bytes)")
                        continue
                    
                    attachment_count += 1
                    parse_result = await parser.parse(att_filename, att_bytes)
                    combined_text += f"\n\n--- Attachment: {att_filename} ---\n{parse_result.raw_text}"

                    doc_record = {
                        "document_id": str(uuid.uuid4()),
                        "email_id": email_record["email_id"],
                        "case_id": case_id,
                        "filename": att_filename,
                        "file_name": att_filename, # Compatibility
                        "blob_path": att_path,
                        "extracted_text": parse_result.raw_text,
                        "processing_status": "DONE",
                        "created_at": datetime.utcnow().isoformat(),
                    }
                    await db_service.create_document(doc_record)

                email_record["attachment_count"] = attachment_count

                # Preserve raw HTML in body, use cleaned text for body_masked preview
                from utils.html_utils import clean_html
                raw_body_html = email_data.get("body", "")
                cleaned_body_text = clean_html(raw_body_html)
                
                email_record["body"] = raw_body_html
                email_record["body_masked"] = cleaned_body_text[:2000] # Plain text preview for sidebar
                if settings.demo_mode:
                    from tinydb import Query
                    from services.local_db import _get_db as get_tinydb
                    db = get_tinydb()
                    E = Query()
                    db.table("emails").upsert(email_record, E.email_id == email_record["email_id"])
                    db.storage.flush()
                else:
                    container_client = await db_service._get_container("emails")
                    await container_client.upsert_item(email_record)

                # Skip Safety and AI Classification during background polling.
                # Just mark the blob as processed and log success.
                # The CaseStatus remains 'RECEIVED' so the user can manually process it in the UI.

                await blob_service.mark_as_processed(container, email_json_path)
                success_count += 1
                logger.info(f"[Poller] ✅ Ingested case {case_id} from {folder} (Pending Manual Review)")

            except Exception as e:
                logger.error(f"[Poller] Failed folder {folder}: {e}", exc_info=True)
                if case_id:
                    try:
                        await db_service.delete_case_data(case_id)
                    except Exception:
                        pass
                failure_count += 1

    finally:
        await blob_service.close()

    return {
        "new_cases_processed": success_count,
        "failed": failure_count,
        "message": f"Synced {success_count} email(s). {failure_count} failed.",
    }


async def start_email_poll_loop(interval_seconds: int = 10):
    """
    Background task: polls for new emails every `interval_seconds`.
    Uses a lock to prevent overlapping runs.
    Safe to call in demo mode — will gracefully skip if credentials are missing.
    """
    logger.info(f"[Poller] Auto-poll started — checking every {interval_seconds}s.")
    while True:
        await asyncio.sleep(interval_seconds)
        if _sync_lock.locked():
            logger.debug("[Poller] Previous sync still running, skipping this tick.")
            continue
        async with _sync_lock:
            try:
                result = await run_email_sync_pipeline()
                if result["new_cases_processed"] > 0 or result["failed"] > 0:
                    logger.info(
                        f"[Poller] Tick complete — processed={result['new_cases_processed']}, "
                        f"failed={result['failed']}"
                    )
            except Exception as e:
                # Don't crash the loop on errors (config missing, network blip, etc.)
                logger.debug(f"[Poller] Tick skipped: {e}")
