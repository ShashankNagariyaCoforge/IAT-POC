"""
UW Worksheet API endpoints.

POST   /api/cases/{case_id}/uw-worksheet/generate  — stream SSE generation
GET    /api/cases/{case_id}/uw-worksheet            — fetch saved worksheet
PATCH  /api/cases/{case_id}/uw-worksheet            — save edits
GET    /api/cases/{case_id}/uw-worksheet/download   — download Word .docx
"""

import logging
from datetime import datetime

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse, Response

from config import settings
from models.uw_worksheet import UWWorksheetPatch

logger = logging.getLogger(__name__)
router = APIRouter()


def _get_db():
    if settings.demo_mode:
        from services.local_db import LocalDBService
        return LocalDBService()
    from services.cosmos_db import CosmosDBService
    return CosmosDBService()


@router.post("/cases/{case_id}/uw-worksheet/generate")
async def generate_uw_worksheet(case_id: str):
    """
    Generate (or re-generate) a UW worksheet for a case.
    Returns an SSE stream; each event is a JSON payload.
    """
    db = _get_db()

    # Load case + classification + docs + enrichment
    case = await db.get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail=f"Case not found: {case_id}")

    cls = await db.get_classification_for_case(case_id) or {}

    docs_resp = await db.get_documents_for_case(case_id)
    # Normalise file_name across both field name conventions
    docs = []
    for d in docs_resp:
        d = dict(d)
        if "filename" in d and "file_name" not in d:
            d["file_name"] = d["filename"]
        docs.append(d)

    # Enrichment (optional)
    enrichment = None
    try:
        enr_doc = await db.get_enrichment_for_case(case_id)
        if enr_doc:
            raw = enr_doc.get("enrichment")
            # The stored enrichment may be nested: {enrichment: {enrichment: {...}}}
            if raw and isinstance(raw, dict) and "enrichment" in raw:
                enrichment = raw["enrichment"]
            else:
                enrichment = raw
    except Exception as e:
        logger.warning(f"[UWWorksheet] Could not load enrichment for {case_id}: {e}")

    from services.uw_worksheet_service import generate_worksheet_stream

    async def event_stream():
        try:
            async for chunk in generate_worksheet_stream(case_id, case, cls, docs, enrichment):
                yield chunk
        except Exception as e:
            import json
            logger.error(f"[UWWorksheet] Stream error for {case_id}: {e}")
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.get("/cases/{case_id}/uw-worksheet")
async def get_uw_worksheet(case_id: str):
    """Fetch the saved UW worksheet for a case (if it exists)."""
    db = _get_db()
    worksheet = await db.get_uw_worksheet(case_id)
    if not worksheet:
        raise HTTPException(status_code=404, detail="No worksheet generated yet for this case.")
    worksheet.pop("_id", None)
    return worksheet


@router.patch("/cases/{case_id}/uw-worksheet")
async def patch_uw_worksheet(case_id: str, payload: UWWorksheetPatch):
    """Save edited worksheet sections back to DB."""
    db = _get_db()
    existing = await db.get_uw_worksheet(case_id)
    if not existing:
        raise HTTPException(status_code=404, detail="No worksheet found for this case.")

    from models.uw_worksheet import UWWorksheet
    worksheet = UWWorksheet(
        case_id=case_id,
        generated_at=existing.get("generated_at", datetime.utcnow()),
        last_edited_at=datetime.utcnow(),
        sections=payload.sections,
        generation_status=existing.get("generation_status", "complete"),
    )
    await db.save_uw_worksheet(worksheet)
    return {"status": "saved"}


@router.get("/cases/{case_id}/uw-worksheet/download")
async def download_uw_worksheet(case_id: str):
    """Download the UW worksheet as a Word .docx file."""
    db = _get_db()
    raw = await db.get_uw_worksheet(case_id)
    if not raw:
        raise HTTPException(status_code=404, detail="No worksheet found for this case.")

    from models.uw_worksheet import UWWorksheet, UWSection
    sections = [UWSection(**s) for s in raw.get("sections", [])]
    worksheet = UWWorksheet(
        case_id=case_id,
        generated_at=raw.get("generated_at", datetime.utcnow()),
        sections=sections,
        generation_status=raw.get("generation_status", "complete"),
    )

    from services.uw_worksheet_service import build_word_document
    try:
        doc_bytes = build_word_document(worksheet, case_id)
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))

    filename = f"UW_Worksheet_{case_id[:8]}.docx"
    return Response(
        content=doc_bytes,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
