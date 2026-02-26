"""
Microsoft Graph API webhook endpoint.
Handles:
  - Validation handshake (GET with validationToken)
  - Email notification processing (POST with JSON payload)
  - Triggers the background processing pipeline for each new email
"""

import base64
import json
import logging
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request, Response

from config import settings
from services.graph_client import GraphClient
from services.pipeline import run_pipeline

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/email")
async def webhook_email(
    request: Request,
    background_tasks: BackgroundTasks,
    validationToken: Optional[str] = Query(default=None),
):
    """
    Microsoft Graph API webhook endpoint.

    - When Graph sends ?validationToken=xxx (subscription creation handshake),
      we must return the token as plain text with HTTP 200.
    - When Graph sends a notification payload, we extract the message ID and
      trigger the background processing pipeline.

    Args:
        request: The incoming HTTP request.
        background_tasks: FastAPI background task runner.
        validationToken: Query parameter for subscription validation.
    """
    # --- Subscription validation handshake ---
    if validationToken:
        logger.info("Graph webhook validation handshake received.")
        return Response(content=validationToken, media_type="text/plain", status_code=200)

    # --- Email notification ---
    try:
        body = await request.json()
    except Exception:
        logger.error("Webhook: failed to parse request body.")
        raise HTTPException(status_code=400, detail="Invalid JSON body.")

    # Validate client state (basic security check)
    client_state = body.get("value", [{}])[0].get("clientState", "")
    if settings.webhook_secret and client_state != settings.webhook_secret:
        logger.warning("Webhook: invalid clientState received. Ignoring.")
        raise HTTPException(status_code=401, detail="Invalid client state.")

    notifications = body.get("value", [])
    if not notifications:
        logger.warning("Webhook: received empty notification payload.")
        return {"status": "ok"}

    graph = GraphClient()
    for notification in notifications:
        resource_data = notification.get("resourceData", {})
        message_id = resource_data.get("id")
        if not message_id:
            logger.warning(f"Webhook notification missing message ID: {notification}")
            continue

        logger.info(f"Webhook: queuing pipeline for message {message_id}")
        # Trigger background processing pipeline — must return 200 to Graph within 3 seconds
        background_tasks.add_task(run_pipeline, message_id=message_id)

    return {"status": "accepted"}
