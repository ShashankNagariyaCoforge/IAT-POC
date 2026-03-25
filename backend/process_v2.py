"""
Process V2 — Staged insurance document processing pipeline.

Routes:
  POST /api/v2/cases/{case_id}/process   (drop-in replacement for existing /api/cases/{case_id}/process)
  POST /api/v2/process-case              (CLAUDE.md spec route, same logic)

Response shape:
  Fully V1-compatible — identical keys to /api/cases/{case_id}/process so the
  existing UI works without any frontend changes.
  V2-only traceability data is appended under v2_* keys which the current UI
  ignores, but the future click-to-highlight feature will consume.

V2 improvements over process.py:
  - Multi-stage LLM calls (doc type ID + case classification + per-doc extraction + validation)
  - Chunk-based coordinate resolution (rapidfuzz on word_map, not whole-document scan)
  - Full extraction traceability per field (source_document, page, bbox, chunk_id, raw_text)
  - Conflict detection + reasoning agent resolution
  - Configurable taxonomies and schemas via .env + JSON files
  - Writes to NEW Cosmos DB collections (cases_v2, extractions_v2, documents_v2, pipeline_logs_v2)
  - ALSO writes V1-compatible records to existing collections so all GET endpoints work
"""

import asyncio
import logging
import time
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from pipeline_v2.agents.enrichment_agent import EnrichmentAgent
from pipeline_v2.agents.reasoning_agent import resolve_conflicts
from pipeline_v2.models import MergedField, PipelineResult
from pipeline_v2.stages import (
    stage1_ingestion,
    stage2_parsing,
    stage3_chunking,
    stage4_doc_classification,
    stage5_case_classification,
    stage6_schema_loader,
    stage7_extraction,
    stage8_coordinate_resolver,
    stage9_merge,
    stage10_enrichment,
    stage11_validation,
    stage12_routing,
)
from pipeline_v2.utils.cosmos_client_v2 import CosmosClientV2
from pipeline_v2.utils.pipeline_logger import plog

logger = logging.getLogger(__name__)
router = APIRouter()


# ── V1 classification_category lookup ─────────────────────────────────────────
# Maps V2 snake_case case_type → V1 display string expected by the UI
_CASE_TYPE_TO_CATEGORY: Dict[str, str] = {
    "new_claim":               "New",
    "renewal":                 "Renewal",
    "endorsement":             "New",            # Closest V1 equivalent
    "mid_term_adjustment":     "New",
    "cancellation":            "Query/General",
    "general_query":           "Query/General",
    "follow_up":               "Follow-up",
    "complaint_escalation":    "Complaint/Escalation",
    "regulatory_legal":        "Regulatory/Legal",
    "documentation_evidence":  "Documentation/Evidence",
    "spam_irrelevant":         "Spam/Irrelevant",
    "bor":                     "BOR",
}


# ── DB helpers ─────────────────────────────────────────────────────────────────

def _get_v1_db():
    from config import settings
    if settings.demo_mode:
        from services.local_db import LocalDBService
        return LocalDBService()
    from services.cosmos_db import CosmosDBService
    return CosmosDBService()


def _get_page_dims(parsed_docs: List, doc_name: str, page_num: int) -> dict:
    """Look up ADI page dimensions for a given document + page number."""
    for doc in parsed_docs:
        if doc.filename == doc_name:
            for page in doc.pages:
                if page.get("page_number") == page_num:
                    return {
                        "width": page.get("width"),
                        "height": page.get("height"),
                        "unit": page.get("unit", "inch"),
                    }
            # Page number not matched — return first page as fallback
            if doc.pages:
                p = doc.pages[0]
                return {"width": p.get("width"), "height": p.get("height"), "unit": p.get("unit", "inch")}
    return {"width": None, "height": None, "unit": "inch"}


def _get_doc_uuid(parsed_docs: List, filename: str) -> str:
    """Resolve document UUID from filename. Falls back to filename if not found."""
    for doc in parsed_docs:
        if doc.filename == filename:
            return doc.document_id
    return filename


def _fv(merged_fields: List[MergedField], field_name: str) -> Optional[str]:
    """Get value of a merged field by name, returns None if missing/null."""
    for f in merged_fields:
        if f.field_name == field_name:
            return f.value if f.value else None
    return None


def _fc(merged_fields: List[MergedField], field_name: str) -> Optional[float]:
    """Get confidence of a merged field by name."""
    for f in merged_fields:
        if f.field_name == field_name:
            return f.confidence
    return None


# ── V2 internal field serialiser (for v2_* extras and v2 DB) ──────────────────

def _build_field_detail(field: MergedField) -> Dict[str, Any]:
    """Full V2 field object — value + confidence + status + complete traceability."""
    traceability = None
    if field.primary_source and field.primary_source.location:
        loc = field.primary_source.location
        traceability = {
            "document_name":      loc.document_name,
            "page_number":        loc.page_number,
            "bbox":               loc.bbox,
            "blob_url":           loc.blob_url,
            "chunk_id":           loc.chunk_id,
            "section_heading":    loc.section_heading,
            "approximate_position": loc.approximate_position,
            "raw_text":           loc.raw_text,
            "extraction_source":  loc.extraction_source,
            "enrichment_url":     field.enrichment_url,
        }
    return {
        "value":         field.value,
        "confidence":    round(field.confidence, 4),
        "status":        field.status,
        "mandatory":     field.mandatory,
        "display_label": field.display_label,
        "traceability":  traceability,
        "all_sources": [
            {
                "document_name": s.document_name,
                "value":         s.value,
                "confidence":    round(s.confidence, 4),
            }
            for s in (field.all_sources or [])
        ],
    }


# ── V1-compatible builders ─────────────────────────────────────────────────────

def _build_key_fields(
    merged_fields: List[MergedField],
    doc_classifications: Dict,
) -> Dict[str, Any]:
    """
    Build V1 key_fields dict from V2 merged_fields.
    Structure must match the KeyFields TypeScript interface exactly.
    """
    fv = lambda name: _fv(merged_fields, name)
    fc = lambda name: _fc(merged_fields, name)

    # field_confidence — flat dict {field_name: confidence} for every field
    field_confidence: Dict[str, float] = {}
    for f in merged_fields:
        if f.confidence and f.confidence > 0:
            field_confidence[f.field_name] = round(f.confidence, 4)

    # coverages — build from coverage_types / coverage_limit / deductible / limit_of_liability
    coverages = []
    cov_types = fv("coverage_types")
    cov_limit = fv("coverage_limit") or fv("limit_of_liability")
    deductible = fv("deductible")
    if cov_types or cov_limit or deductible:
        coverages.append({
            "coverage":            cov_types or "",
            "coverageDescription": fv("business_description") or "",
            "limit":               cov_limit or "",
            "deductible":          deductible or "",
        })

    # exposures — from exposure_types
    exposures = []
    exp_types = fv("exposure_types")
    if exp_types:
        exposures.append({
            "exposureType":        exp_types,
            "exposureDescription": fv("business_description") or "",
            "value":               "",
        })

    # documents — from document_classifications
    documents = [
        {
            "fileName":            fn,
            "fileType":            fn.rsplit(".", 1)[-1].upper() if "." in fn else "PDF",
            "documentDescription": dc.role if dc else "Attachment",
        }
        for fn, dc in doc_classifications.items()
    ]

    # document_type — most significant doc role (first non-unknown)
    doc_type = next(
        (dc.role for dc in doc_classifications.values() if dc.role != "unknown"),
        "unknown",
    )

    return {
        # Core insured
        "name":                 fv("insured_name"),
        "applicant_name":       fv("insured_name"),
        "insured": {
            "name":    fv("insured_name"),
            "address": fv("insured_address"),
        },
        "address":              fv("insured_address"),

        # Agent / broker
        "agent": {
            "agencyName": fv("agency"),
            "name":       fv("agent_name") or fv("licensed_producer"),
            "email":      fv("agent_email"),
            "phone":      fv("agent_phone"),
        },
        "agency":               fv("agency"),
        "licensed_producer":    fv("licensed_producer"),
        "agent_email":          fv("agent_email"),
        "agent_phone":          fv("agent_phone"),
        "primary_phone":        fv("agent_phone"),
        "email_address":        fv("agent_email"),

        # Submission metadata
        "submission_description": fv("submission_description"),
        "submission_type":      fv("submission_type"),
        "segment":              fv("segment"),
        "iat_product":          fv("iat_product"),
        "uw_am":                fv("uw_am"),
        "urgency":              fv("urgency"),
        "policy_reference":     fv("policy_reference"),
        "effective_date":       fv("effective_date"),
        "document_type":        doc_type,
        "claim_type":           fv("coverage_types"),

        # Business info
        "entity_type":          fv("entity_type"),
        "naics_code":           fv("naics_code"),
        "sic_code":             fv("sic_code"),
        "business_description": fv("business_description"),
        "primary_rating_state": fv("primary_rating_state"),

        # Structured lists
        "coverages":  coverages,
        "exposures":  exposures,
        "documents":  documents,

        # Per-field confidence scores — UI reads these for the confidence badges
        "field_confidence": field_confidence,
    }


def _build_extraction_results(
    merged_fields: List[MergedField],
    parsed_docs: List,
) -> List[Dict[str, Any]]:
    """
    Build V1-format extraction_results from V2 traceability data.

    V1 format per field:
      {"field": "Insured Name", "instances": [{"value": "...", "confidence": 0.96,
       "doc_id": "<uuid>", "page": 1, "polygon": [x1,y1,x2,y1,x2,y2,x1,y2],
       "page_width": 8.5, "page_height": 11.0, "unit": "inch"}]}

    doc_id is the document UUID (so /api/cases/{id}/documents/{doc_id}/pdf works).
    polygon is expanded from V2's [x1,y1,x2,y2] bbox →
    clockwise rectangle [x1,y1, x2,y1, x2,y2, x1,y2].
    page_width / page_height / unit come from ADI page metadata.
    """
    results = []
    for field in merged_fields:
        if not field.value:
            continue
        if not (field.primary_source and field.primary_source.location):
            continue

        loc = field.primary_source.location
        bbox = loc.bbox  # [x1, y1, x2, y2] or None

        # Expand 4-point bbox to V1's 8-point polygon (clockwise rectangle)
        if bbox and len(bbox) == 4:
            x1, y1, x2, y2 = bbox
            polygon = [x1, y1, x2, y1, x2, y2, x1, y2]
        else:
            polygon = []

        # Look up page dimensions and document UUID from parsed docs
        dims    = _get_page_dims(parsed_docs, loc.document_name, loc.page_number or 1)
        doc_uuid = _get_doc_uuid(parsed_docs, loc.document_name)

        results.append({
            "field": field.display_label or field.field_name,
            "instances": [{
                "value":       field.value,
                "confidence":  round(field.confidence, 4),
                "doc_id":      doc_uuid,
                "page":        loc.page_number or 1,
                "polygon":     polygon,
                "page_width":  dims["width"] or 0,
                "page_height": dims["height"] or 0,
                "unit":        dims["unit"],
            }],
        })
    return results


def _build_summary(case_cls, merged_fields: List[MergedField]) -> str:
    """
    Generate a summary string from V2 classification reasoning.
    V1 classifier returns a free-text summary — we synthesise one here.
    V2's reasoning is richer than V1's summary so this is an improvement.
    """
    if case_cls.reasoning:
        return case_cls.reasoning

    # Fallback: synthesise from extracted values
    insured = _fv(merged_fields, "insured_name") or "Unknown insured"
    agency  = _fv(merged_fields, "agency") or "unknown broker"
    lob     = case_cls.line_of_business or "unknown line"
    return (
        f"{_CASE_TYPE_TO_CATEGORY.get(case_cls.case_type, case_cls.case_type)} submission "
        f"from {agency} for {insured} ({lob})."
    )


def _build_enrichment_doc(
    case_id: str,
    merged_fields: List[MergedField],
) -> Optional[Dict[str, Any]]:
    """
    Build V1-compatible enrichment doc from fields that were web-enriched.
    Returns None if no enrichment happened.
    """
    enrichment_fields = [f for f in merged_fields if f.enrichment_url]
    if not enrichment_fields:
        return None

    source_urls = list({f.enrichment_url for f in enrichment_fields if f.enrichment_url})

    enrichment_data: Dict[str, Any] = {
        "source_urls":        source_urls,
        "company_name":       _fv(merged_fields, "insured_name"),
        "website":            None,
        "enrichment_status":  "completed",
    }

    # Map each enriched field into V1 EnrichedField shape {value, confidence, source}
    for field in enrichment_fields:
        enrichment_data[field.field_name] = {
            "value":      field.value,
            "confidence": round(field.confidence, 4),
            "source":     field.enrichment_url,
        }

    return {
        "case_id":    case_id,
        "result_id":  str(uuid.uuid4()),
        "enrichment": enrichment_data,
        "enriched_at": datetime.utcnow().isoformat(),
    }


# ── V2-only extras (for future click-to-highlight and audit) ──────────────────

def _build_v2_traceability(
    merged_fields: List[MergedField],
    parsed_docs: List,
) -> Dict[str, Any]:
    """
    Per-field traceability dict keyed by field_name.
    The click-to-highlight feature reads:
      v2_traceability[fieldName] → {page_number, bbox, page_width, page_height,
                                     coordinate_unit, doc_id, blob_url, raw_text, ...}
    """
    out = {}
    for field in merged_fields:
        if field.primary_source and field.primary_source.location:
            loc = field.primary_source.location
            dims     = _get_page_dims(parsed_docs, loc.document_name, loc.page_number or 1)
            doc_uuid = _get_doc_uuid(parsed_docs, loc.document_name)
            out[field.field_name] = {
                "page_number":       loc.page_number,
                "bbox":              loc.bbox,
                "page_width":        dims["width"],
                "page_height":       dims["height"],
                "coordinate_unit":   dims["unit"],
                "doc_id":            doc_uuid,
                "document_name":     loc.document_name,
                "blob_url":          loc.blob_url,
                "raw_text":          loc.raw_text,
                "chunk_id":          loc.chunk_id,
                "section_heading":   loc.section_heading,
                "extraction_source": loc.extraction_source,
                "enrichment_url":    field.enrichment_url,
            }
    return out


# ── Write-back to V1 DB so all existing GET endpoints work ────────────────────

async def _write_v1_db_records(
    case_id: str,
    case_cls,
    merged_fields: List[MergedField],
    doc_classifications: Dict,
    validation_flags: List,
    routing,
    duration: float,
    db_v1,
    parsed_docs: List = None,
) -> str:
    """
    Write V1-compatible records to existing Cosmos collections so that:
      GET /api/cases/{id}                → shows correct status + category
      GET /api/cases/{id}/classification → returns full classification
      GET /api/cases/{id}/enrichment     → returns enrichment data

    Returns the result_id of the saved classification document.
    """
    from models.case import CaseStatus

    classification_category = _CASE_TYPE_TO_CATEGORY.get(
        case_cls.case_type, "Query/General"
    )
    requires_human_review = routing.route == "full_human_review"
    result_id = str(uuid.uuid4())

    # 1. Build full classification doc in V1 shape
    key_fields  = _build_key_fields(merged_fields, doc_classifications)
    extract_res = _build_extraction_results(merged_fields, parsed_docs or [])
    summary     = _build_summary(case_cls, merged_fields)

    classification_doc = {
        "result_id":                   result_id,
        "case_id":                     case_id,
        "classification_category":     classification_category,
        "confidence_score":            round(case_cls.confidence, 4),
        "summary":                     summary,
        "key_fields":                  key_fields,
        "requires_human_review":       requires_human_review,
        "classified_at":               datetime.utcnow().isoformat(),
        "extraction_results":          extract_res,
        "extracted_tables":            [],   # V2 doesn't extract tables
        "annotated_docs":              {},   # Replaced by click-to-highlight (v2_traceability)
        "downstream_notification_sent": False,
        "downstream_notification_at":  None,
        # V2-only extras (UI ignores, future feature reads)
        "v2_traceability":             _build_v2_traceability(merged_fields, parsed_docs or []),
        "v2_conflicts": [
            {
                "field_name":  f.field_name,
                "display_label": f.display_label,
                "values": [
                    {"document": s.document_name, "value": s.value}
                    for s in (f.conflict_values or [])
                ],
            }
            for f in merged_fields if f.status == "conflict"
        ],
        "v2_validation_flags":         [vf.model_dump() for vf in validation_flags],
        "v2_missing_mandatory_fields": [
            f.field_name for f in merged_fields if f.mandatory and f.status == "missing"
        ],
        "v2_line_of_business":         case_cls.line_of_business,
        "v2_broker_submitted":         case_cls.broker_submitted,
        "v2_routing":                  routing.route,
        "v2_review_reasons":           routing.reasons,
        "v2_flagged_fields":           routing.flagged_fields,
        "v2_processing_duration_seconds": round(duration, 2),
        "pipeline_version":            "v2",
    }

    try:
        await db_v1.save_classification_result(classification_doc)
        logger.info(f"[ProcessV2] Saved V1 classification result for case {case_id}")
    except Exception as e:
        logger.error(f"[ProcessV2] Failed to save V1 classification result: {e}")

    # 2. Update case status in V1 cases collection
    try:
        final_status = (
            CaseStatus.PENDING_REVIEW if requires_human_review else CaseStatus.PROCESSED
        )
        await db_v1.update_case_status(
            case_id,
            final_status,
            classification_category=classification_category,
            confidence_score=round(case_cls.confidence, 4),
            requires_human_review=requires_human_review,
            pipeline_step="completed",
            pipeline_version="v2",
        )
        logger.info(f"[ProcessV2] Updated V1 case status → {final_status.value}")
    except Exception as e:
        logger.error(f"[ProcessV2] Failed to update V1 case status: {e}")

    # 3. Save enrichment results to V1 enrichment collection (if any web enrichment occurred)
    enrichment_doc = _build_enrichment_doc(case_id, merged_fields)
    if enrichment_doc:
        try:
            await db_v1.save_enrichment_result(enrichment_doc)
            logger.info(f"[ProcessV2] Saved V1 enrichment result for case {case_id}")
        except Exception as e:
            logger.error(f"[ProcessV2] Failed to save V1 enrichment result: {e}")

    return result_id


# ── V2 internal DB persistence ─────────────────────────────────────────────────

async def _save_v2_results(
    case_id: str,
    case_cls,
    merged_fields: List[MergedField],
    doc_classifications: Dict,
    chunk_map: Dict,
    parsed_docs: List,
    validation_flags: List,
    routing,
    duration: float,
    db_v2: CosmosClientV2,
):
    """Persist all v2 results to new Cosmos v2 collections."""

    # 1. Case summary
    await db_v2.save_case({
        "case_id":                  case_id,
        "created_at":               datetime.utcnow().isoformat(),
        "case_type":                case_cls.case_type,
        "line_of_business":         case_cls.line_of_business,
        "urgency":                  case_cls.urgency,
        "classification_confidence": case_cls.confidence,
        "broker_submitted":         case_cls.broker_submitted,
        "routing_decision":         routing.route,
        "routing_reasons":          routing.reasons,
        "review_required":          routing.route != "auto_process",
        "pipeline_version":         "v2",
        "processing_status":        "completed",
        "processing_duration_seconds": round(duration, 2),
        "updated_at":               datetime.utcnow().isoformat(),
    })

    # 2. Extraction results with full traceability
    fields_dict        = {f.field_name: _build_field_detail(f) for f in merged_fields}
    conflicts          = [
        {"field_name": f.field_name, "values": [s.value for s in (f.conflict_values or [])]}
        for f in merged_fields if f.status == "conflict"
    ]
    missing_mandatory  = [f.field_name for f in merged_fields if f.mandatory and f.status == "missing"]

    await db_v2.save_extraction({
        "case_id":                 case_id,
        "pipeline_version":        "v2",
        "fields":                  fields_dict,
        "conflicts":               conflicts,
        "validation_flags":        [vf.model_dump() for vf in validation_flags],
        "missing_mandatory_fields": missing_mandatory,
        "saved_at":                datetime.utcnow().isoformat(),
    })

    # 3. Document records with chunk maps
    for doc in parsed_docs:
        doc_chunks = [
            {
                "chunk_id":            c.chunk_id,
                "page_number":         c.page_number,
                "section_heading":     c.section_heading,
                "text":                c.text[:2000],
                "approximate_position": c.approximate_position,
                "word_map":            [w.model_dump() for w in c.word_map[:500]],
            }
            for c in chunk_map.values()
            if c.document_name == doc.filename
        ]
        role = doc_classifications.get(doc.filename)
        await db_v2.save_document({
            "case_id":        case_id,
            "filename":       doc.filename,
            "blob_url":       doc.blob_url,
            "document_role":  role.role if role else "unknown",
            "role_confidence": role.confidence if role else 0.0,
            "page_count":     doc.page_count,
            "pipeline_version": "v2",
            "chunk_count":    len(doc_chunks),
            "chunks":         doc_chunks,
        })


# ── Final response builder — V1-compatible + V2 extras ────────────────────────

def _build_response(
    case_id: str,
    case_cls,
    merged_fields: List[MergedField],
    validation_flags: List,
    routing,
    doc_classifications: Dict,
    duration: float,
    result_id: str,
    parsed_docs: List = None,
) -> Dict[str, Any]:
    """
    Build the API response in V1 ClassificationResult shape.
    The existing UI reads all standard V1 keys unchanged.
    v2_* keys are appended for the future click-to-highlight feature.
    """
    classification_category = _CASE_TYPE_TO_CATEGORY.get(
        case_cls.case_type, "Query/General"
    )
    requires_human_review = routing.route == "full_human_review"

    return {
        # ── V1 ClassificationResult keys (UI reads these) ──────────────────
        "result_id":                    result_id,
        "case_id":                      case_id,
        "classification_category":      classification_category,
        "confidence_score":             round(case_cls.confidence, 4),
        "summary":                      _build_summary(case_cls, merged_fields),
        "key_fields":                   _build_key_fields(merged_fields, doc_classifications),
        "requires_human_review":        requires_human_review,
        "classified_at":                datetime.utcnow().isoformat(),
        "extraction_results":           _build_extraction_results(merged_fields, parsed_docs or []),
        "extracted_tables":             [],   # V2 does not extract tables
        "annotated_docs":               {},   # Replaced by click-to-highlight
        "downstream_notification_sent": False,
        "downstream_notification_at":   None,

        # ── V2-only keys — click-to-highlight reads these ──────────────────
        # Every field → {page_number, bbox, page_width, page_height, coordinate_unit, doc_id, ...}
        "v2_traceability":              _build_v2_traceability(merged_fields, parsed_docs or []),
        "v2_conflicts": [
            {
                "field_name":    f.field_name,
                "display_label": f.display_label,
                "values": [
                    {"document": s.document_name, "value": s.value}
                    for s in (f.conflict_values or [])
                ],
            }
            for f in merged_fields if f.status == "conflict"
        ],
        "v2_validation_flags":          [vf.model_dump() for vf in validation_flags],
        "v2_missing_mandatory_fields": [
            f.field_name for f in merged_fields if f.mandatory and f.status == "missing"
        ],
        "v2_line_of_business":          case_cls.line_of_business,
        "v2_case_type":                 case_cls.case_type,
        "v2_broker_submitted":          case_cls.broker_submitted,
        "v2_routing":                   routing.route,
        "v2_review_reasons":            routing.reasons,
        "v2_flagged_fields":            routing.flagged_fields,
        "v2_processing_duration_seconds": round(duration, 2),
        "pipeline_version":             "v2",
    }


# ── Main pipeline orchestrator ─────────────────────────────────────────────────

async def _run_pipeline(case_id: str) -> Dict[str, Any]:
    start   = time.time()
    db_v1   = _get_v1_db()
    db_v2   = CosmosClientV2()

    # ── Start debug log (overwrites log.txt) ──────────────────────────────────
    plog.start_case(case_id)

    await db_v2.update_case_status(case_id, "processing", "stage1_ingestion")

    # ── Stage 1: Ingestion ─────────────────────────────────────────────────────
    stage_start = time.time()
    ingestion   = await stage1_ingestion.run(case_id, db_v1)
    await db_v2.log_stage(case_id, "stage1_ingestion", "success", time.time() - stage_start)
    plog.log_stage("1 — Ingestion",
        email_subject=ingestion.email_subject,
        email_sender=getattr(ingestion, "email_sender", ""),
        email_body_length=f"{len(ingestion.email_body)} chars",
        email_body_preview=ingestion.email_body[:1000],
        attachments=[getattr(a, "filename", str(a)) for a in (ingestion.attachments or [])],
    )

    # ── Stage 2: Parsing + OCR (parallel per doc) ─────────────────────────────
    await db_v2.update_case_status(case_id, "processing", "stage2_parsing")
    stage_start = time.time()
    parsed_docs = await stage2_parsing.run(ingestion)
    await db_v2.log_stage(case_id, "stage2_parsing", "success", time.time() - stage_start,
                          metadata={"doc_count": len(parsed_docs)})
    plog.log_stage("2 — Parsing / OCR",
        doc_count=len(parsed_docs),
        documents=[
            {
                "filename": d.filename,
                "pages": d.page_count,
                "text_length": len(d.full_text or ""),
                "text_preview": (d.full_text or "")[:500],
            }
            for d in parsed_docs
        ],
    )

    # ── Stage 3: Chunking ──────────────────────────────────────────────────────
    stage_start = time.time()
    chunk_map   = stage3_chunking.run(parsed_docs)
    await db_v2.log_stage(case_id, "stage3_chunking", "success", time.time() - stage_start,
                          metadata={"chunk_count": len(chunk_map)})
    plog.log_stage("3 — Chunking",
        total_chunks=len(chunk_map),
        chunks_per_doc={
            doc.filename: sum(1 for c in chunk_map.values() if c.document_name == doc.filename)
            for doc in parsed_docs
        },
        chunk_ids=list(chunk_map.keys()),
    )

    # ── Stage 4: Document type identification (parallel, small model) ──────────
    await db_v2.update_case_status(case_id, "processing", "stage4_doc_classification")
    stage_start        = time.time()
    doc_classifications = await stage4_doc_classification.run(
        parsed_docs, ingestion.email_subject
    )
    await db_v2.log_stage(case_id, "stage4_doc_classification", "success", time.time() - stage_start)
    plog.log_stage("4 — Document Classification",
        results={
            fn: {"role": dc.role, "confidence": dc.confidence, "reasoning": dc.reasoning}
            for fn, dc in doc_classifications.items()
        },
    )

    # ── Stage 5: Case classification (large model) ─────────────────────────────
    await db_v2.update_case_status(case_id, "processing", "stage5_case_classification")
    stage_start = time.time()
    case_cls    = await stage5_case_classification.run(
        ingestion.email_body, doc_classifications, ingestion.email_subject, case_id,
        parsed_docs=parsed_docs,
    )
    await db_v2.log_stage(case_id, "stage5_case_classification", "success", time.time() - stage_start)
    plog.log_stage("5 — Case Classification",
        case_type=case_cls.case_type,
        line_of_business=case_cls.line_of_business,
        confidence=case_cls.confidence,
        review_required=case_cls.review_required,
        urgency=case_cls.urgency,
        reasoning=case_cls.reasoning,
    )

    # ── GATE: Low confidence → skip extraction, route to human review ──────────
    if case_cls.review_required:
        logger.info(f"[ProcessV2] case={case_id} confidence gate → full_human_review")
        plog.log_stage("GATE — Human Review (confidence too low, skipping extraction)")
        routing  = stage12_routing.run([], [], case_cls.confidence)
        duration = time.time() - start
        plog.end_case(duration, routing.route)

        await _save_v2_results(
            case_id, case_cls, [], doc_classifications, chunk_map,
            parsed_docs, [], routing, duration, db_v2
        )
        await db_v2.update_case_status(case_id, "completed", "full_human_review")

        result_id = await _write_v1_db_records(
            case_id, case_cls, [], doc_classifications, [], routing, duration, db_v1,
            parsed_docs=parsed_docs,
        )
        return _build_response(
            case_id, case_cls, [], [], routing,
            doc_classifications, duration, result_id, parsed_docs=parsed_docs,
        )

    # ── Stage 6: Load extraction schema ───────────────────────────────────────
    schema = stage6_schema_loader.run(case_cls.case_type)
    plog.log_stage("6 — Schema Loading",
        case_type=case_cls.case_type,
        schema_file=f"{case_cls.case_type}.json",
        field_count=len(schema.fields),
        fields=[
            {"name": f.field_name, "mandatory": f.mandatory, "primary_sources": f.primary_sources}
            for f in schema.fields
        ],
    )

    # ── Stage 7: Per-document extraction (parallel, large model) ──────────────
    await db_v2.update_case_status(case_id, "processing", "stage7_extraction")
    stage_start    = time.time()
    raw_extractions = await stage7_extraction.run(
        parsed_docs, doc_classifications, chunk_map, schema, ingestion.email_body, case_id
    )
    await db_v2.log_stage(case_id, "stage7_extraction", "success", time.time() - stage_start)
    # Log per-document extraction results
    plog.log_stage("7 — Extraction (summary)",
        sources=list(raw_extractions.keys()),
    )
    from pipeline_v2.stages.stage7_extraction import _relevant_fields
    for source, fields_list in raw_extractions.items():
        doc_role = doc_classifications.get(source)
        role_str = doc_role.role if doc_role else "submission_email"
        relevant = _relevant_fields(schema, role_str)
        plog.log_extraction(source, relevant, fields_list)

    # ── Stage 8: Coordinate resolution (pure Python, rapidfuzz) ───────────────
    stage_start = time.time()
    resolved    = stage8_coordinate_resolver.run(raw_extractions, chunk_map)
    await db_v2.log_stage(case_id, "stage8_coordinate_resolver", "success", time.time() - stage_start)
    bbox_count = sum(
        1 for doc_res in resolved.values()
        for _, loc in doc_res if loc and loc.bbox
    )
    plog.log_stage("8 — Coordinate Resolution",
        fields_with_bbox=bbox_count,
        fields_without_bbox=sum(
            1 for doc_res in resolved.values() for _, loc in doc_res
        ) - bbox_count,
    )

    # ── Stage 9: Merge + conflict detection ───────────────────────────────────
    stage_start   = time.time()
    merged_fields = stage9_merge.run(resolved, schema)
    await db_v2.log_stage(case_id, "stage9_merge", "success", time.time() - stage_start)
    plog.log_merge(merged_fields)

    # ── Reasoning agent: resolve conflicts (large model) ──────────────────────
    merged_fields = await resolve_conflicts(merged_fields, case_id)

    # ── Stage 10: Web enrichment (missing web_enrichable fields only) ──────────
    await db_v2.update_case_status(case_id, "processing", "stage10_enrichment")
    stage_start      = time.time()
    enrichment_agent = EnrichmentAgent(case_id=case_id)
    merged_fields    = await stage10_enrichment.run(
        merged_fields, ingestion.email_body, enrichment_agent
    )
    await db_v2.log_stage(case_id, "stage10_enrichment", "success", time.time() - stage_start)
    enriched = [f for f in merged_fields if f.enrichment_url]
    plog.log_stage("10 — Web Enrichment",
        enriched_fields=[(f.field_name, f.value, f.enrichment_url) for f in enriched] or "none",
    )

    # ── Stage 11: Validation (small model) ────────────────────────────────────
    await db_v2.update_case_status(case_id, "processing", "stage11_validation")
    stage_start     = time.time()
    validation_flags = await stage11_validation.run(merged_fields, schema, case_id)
    await db_v2.log_stage(case_id, "stage11_validation", "success", time.time() - stage_start)
    plog.log_stage("11 — Validation",
        flag_count=len(validation_flags),
        flags=[
            {"field": f.field_name, "type": f.flag_type, "severity": f.severity, "desc": f.description}
            for f in validation_flags
        ] or "no flags",
    )

    # ── Stage 12: Routing decision (pure Python) ───────────────────────────────
    routing  = stage12_routing.run(merged_fields, validation_flags, case_cls.confidence)
    duration = time.time() - start
    plog.log_stage("12 — Routing",
        route=routing.route,
        reasons=routing.reasons,
        flagged_fields=routing.flagged_fields,
    )

    # ── Persist to V2 collections ─────────────────────────────────────────────
    await _save_v2_results(
        case_id, case_cls, merged_fields, doc_classifications, chunk_map,
        parsed_docs, validation_flags, routing, duration, db_v2
    )
    await db_v2.update_case_status(case_id, "completed", routing.route)

    # ── Write V1-compatible records so all existing GET endpoints work ─────────
    result_id = await _write_v1_db_records(
        case_id, case_cls, merged_fields, doc_classifications,
        validation_flags, routing, duration, db_v1, parsed_docs=parsed_docs,
    )

    logger.info(
        f"[ProcessV2] case={case_id} category={_CASE_TYPE_TO_CATEGORY.get(case_cls.case_type)} "
        f"route={routing.route} duration={duration:.1f}s"
    )
    plog.end_case(duration, routing.route)

    return _build_response(
        case_id, case_cls, merged_fields, validation_flags, routing,
        doc_classifications, duration, result_id, parsed_docs=parsed_docs,
    )


# ── API Endpoints ──────────────────────────────────────────────────────────────

@router.post("/cases/{case_id}/process")
async def process_v2_by_case_id(request: Request, case_id: str):
    """
    V2 pipeline — drop-in URL replacement for /api/cases/{case_id}/process.
    Returns V1-compatible response shape so the existing UI works unchanged.
    Register this router under /api/v2 in main.py.
    """
    try:
        return await _run_pipeline(case_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"[ProcessV2] Pipeline failed for case {case_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


class ProcessCaseRequest(BaseModel):
    case_id: str


@router.post("/process-case")
async def process_v2_flat(request: Request, body: ProcessCaseRequest):
    """
    V2 pipeline — alternative flat endpoint: POST /api/v2/process-case {"case_id": "..."}.
    Returns V1-compatible response shape.
    """
    try:
        return await _run_pipeline(body.case_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"[ProcessV2] Pipeline failed for case {body.case_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
