"""
Cases API endpoints (Step 15).
Provides all read-only endpoints for the React UI.
All routes require JWT authentication (enforced by middleware).

DEMO MODE: When DEMO_MODE=true in .env, uses LocalDBService (TinyDB) instead
           of CosmosDBService, and reads extracted text from local files.
"""

import logging
import os
from typing import Optional, Union

from fastapi import APIRouter, HTTPException, Query

from config import settings

logger = logging.getLogger(__name__)
router = APIRouter()


def _get_cosmos() -> Union["CosmosDBService", "LocalDBService"]:  # type: ignore[name-defined]
    """Dependency: returns DB service — LocalDB in demo mode, Cosmos otherwise."""
    if settings.demo_mode:
        from services.local_db import LocalDBService
        return LocalDBService()
    from services.cosmos_db import CosmosDBService
    return CosmosDBService()


@router.get("/cases")
async def list_cases(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    search: Optional[str] = Query(default=None, description="Search by Case ID, sender, or subject"),
    category: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    requires_human_review: Optional[bool] = Query(default=None),
    date_from: Optional[str] = Query(default=None, description="ISO date string"),
    date_to: Optional[str] = Query(default=None, description="ISO date string"),
    sort_by: str = Query(default="created_at"),
    sort_order: str = Query(default="DESC", pattern="^(ASC|DESC)$"),
):
    """
    List cases with filtering, sorting, and pagination.

    Returns paginated case list for the UI home screen.
    """
    cosmos = _get_cosmos()
    result = await cosmos.list_cases(
        page=page,
        page_size=page_size,
        search=search,
        category=category,
        status=status,
        requires_human_review=requires_human_review,
        date_from=date_from,
        date_to=date_to,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    return result


@router.get("/cases/{case_id}")
async def get_case(case_id: str):
    """
    Get full case detail by Case ID.
    Used for the Case Detail page.
    """
    cosmos = _get_cosmos()
    case = await cosmos.get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail=f"Case not found: {case_id}")
    return case


@router.get("/cases/{case_id}/emails")
async def get_case_emails(case_id: str):
    """
    Get all emails in a case chain, ordered chronologically.
    Note: email bodies are PII-masked before being stored.
    """
    cosmos = _get_cosmos()
    case = await cosmos.get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail=f"Case not found: {case_id}")
    emails = await cosmos.get_emails_for_case(case_id)
    return {"emails": emails, "total": len(emails)}


@router.get("/cases/{case_id}/documents")
async def get_case_documents(case_id: str):
    """
    Get all documents associated with a case.
    Includes extracted text previews (PII masked) and processing metadata.
    """
    cosmos = _get_cosmos()
    case = await cosmos.get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail=f"Case not found: {case_id}")

    docs = await cosmos.get_documents_for_case(case_id)

    # Fetch text previews
    enriched = []
    for doc in docs:
        preview = None
        if settings.demo_mode:
            # Read from local extracted_text folder
            local_path = doc.get("extracted_text_local_path")
            if local_path and os.path.exists(local_path):
                try:
                    with open(local_path, "r", encoding="utf-8") as fp:
                        preview = fp.read(500)
                except Exception:
                    pass
        else:
            # Read from Azure Blob
            from services.blob_storage import BlobStorageService
            blob = BlobStorageService()
            text_path = doc.get("extracted_text_blob_path")
            if text_path:
                try:
                    container, blob_name = text_path.split("/", 1)
                    text = await blob.download_text(container, blob_name)
                    preview = text[:500]
                except Exception:
                    pass
        enriched.append({**doc, "extracted_text_preview": preview})

    return {"documents": enriched, "total": len(enriched)}


@router.get("/cases/{case_id}/classification")
async def get_case_classification(case_id: str):
    """
    Get the classification result for a case.
    Includes confidence score, category, summary, and notification status.
    """
    cosmos = _get_cosmos()
    case = await cosmos.get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail=f"Case not found: {case_id}")
    result = await cosmos.get_classification_for_case(case_id)
    if not result:
        return {"classification": None, "message": "Classification not yet available."}
    return {"classification": result}


@router.get("/cases/{case_id}/timeline")
async def get_case_timeline(case_id: str):
    """
    Get the processing event timeline for a case.
    Events: email received, processed, classified, notified.
    """
    cosmos = _get_cosmos()
    case = await cosmos.get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail=f"Case not found: {case_id}")
    timeline = await cosmos.get_timeline_for_case(case_id)
    return {"timeline": timeline}
