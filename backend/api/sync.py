"""
Sync API — Manual trigger endpoint for the email pipeline.

The actual pipeline logic lives in services/email_poller.py and is shared with
the background auto-polling task started at server boot.
"""

import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services.email_poller import run_email_sync_pipeline, _sync_lock

logger = logging.getLogger(__name__)
router = APIRouter()


class SyncResult(BaseModel):
    new_cases_processed: int
    failed: int
    message: str


@router.post("/cases/sync", response_model=SyncResult)
async def sync_emails_from_blob():
    """
    Manually trigger the two-step email sync pipeline:
      - Step 0: Fetch unread emails from the mailbox via Graph API → upload to Blob Storage
      - Step 1: Process unprocessed blob folders → PII mask → classify → save to DB

    Returns 409 if an auto-poll sync is already in progress.
    """
    if _sync_lock.locked():
        raise HTTPException(
            status_code=409,
            detail="A sync is already in progress (triggered by auto-poller). Please try again shortly."
        )

    async with _sync_lock:
        result = await run_email_sync_pipeline()
        return SyncResult(**result)
