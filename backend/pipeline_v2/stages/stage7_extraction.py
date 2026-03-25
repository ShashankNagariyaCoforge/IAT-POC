"""
Stage 7 — Targeted Per-Document Extraction
One focused LLM call per document (parallel).
Each call only asks for fields relevant to that document's role.
LLM must return raw_text (verbatim phrase) + chunk_id per field — no coordinates.
"""

import asyncio
import json
import logging
import os
from typing import Dict, List

from pipeline_v2.config import v2_settings
from pipeline_v2.models import (
    ChunkData, DocumentClassification, ExtractionSchema,
    ExtractedFieldRaw, ParsedDocument,
)
from pipeline_v2.utils.llm_client import call_llm, LLMCallError

logger = logging.getLogger(__name__)

_PROMPTS_DIR = os.path.join(os.path.dirname(__file__), "..", "prompts")

# Load extraction base prompt once
def _load_extraction_prompt() -> str:
    path = os.path.join(_PROMPTS_DIR, "extraction_base.txt")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    return ""   # Will be assembled inline if file missing

_EXTRACTION_BASE = None


def _get_extraction_prompt() -> str:
    global _EXTRACTION_BASE
    if _EXTRACTION_BASE is None:
        _EXTRACTION_BASE = _load_extraction_prompt()
    return _EXTRACTION_BASE


def _build_chunks_text(chunk_map: Dict[str, ChunkData], doc_filename: str) -> str:
    """Return labeled chunk texts for a specific document."""
    doc_chunks = [c for c in chunk_map.values() if c.document_name == doc_filename]
    # Sort by chunk_id to preserve document order
    doc_chunks.sort(key=lambda c: c.chunk_id)

    parts = []
    for chunk in doc_chunks:
        header = f"[{chunk.chunk_id}]"
        if chunk.section_heading:
            header += f" — {chunk.section_heading}"
        parts.append(f"{header}\n{chunk.text}")
    return "\n\n".join(parts) if parts else "(no text)"


def _relevant_fields(schema: ExtractionSchema, doc_role: str) -> list:
    """Return schema fields relevant to this document's role."""
    relevant = []
    for field in schema.fields:
        if doc_role in field.primary_sources or doc_role in field.fallback_sources:
            relevant.append(field)
        elif not field.primary_sources and not field.fallback_sources:
            # No source restrictions — relevant to all docs
            relevant.append(field)
    return relevant if relevant else schema.fields


async def _extract_from_doc(
    doc: ParsedDocument,
    doc_role: str,
    chunk_map: Dict[str, ChunkData],
    schema: ExtractionSchema,
    case_id: str,
) -> List[ExtractedFieldRaw]:

    fields = _relevant_fields(schema, doc_role)
    if not fields:
        return []

    # Build fields JSON for prompt
    fields_json = json.dumps(
        [
            {
                "field_name": f.field_name,
                "display_label": f.display_label,
                "mandatory": f.mandatory,
                "data_type": f.data_type,
            }
            for f in fields
        ],
        indent=2,
    )

    chunks_text = _build_chunks_text(chunk_map, doc.filename)

    base_prompt = _get_extraction_prompt()
    if not base_prompt:
        base_prompt = (
            "You are extracting specific fields from an insurance document.\n\n"
            "CRITICAL RULES:\n"
            "1. Extract ONLY the fields listed below. Do not add others.\n"
            "2. For each field, return raw_text — the EXACT verbatim phrase from the document "
            "(include 10-25 surrounding words for context). Never paraphrase.\n"
            "3. Return the chunk_id EXACTLY as labeled in the document chunks below.\n"
            "4. If a field is not present, return null with a brief not_found_reason.\n"
            "5. Return ONLY valid JSON matching the schema. No other text.\n"
        )

    user_msg = (
        f"Document: {doc.filename} (role: {doc_role})\n\n"
        f"Fields to extract:\n{fields_json}\n\n"
        f"Document chunks (note the chunk IDs carefully):\n{chunks_text[:v2_settings.v2_extraction_chunk_char_limit]}\n\n"
        "Return format:\n"
        "{\n"
        '  "<field_name>": {\n'
        '    "value": "extracted normalized value or null",\n'
        '    "raw_text": "exact verbatim phrase from document with context",\n'
        '    "chunk_id": "filename.pdf::CHUNK_001",\n'
        '    "confidence": 0.95,\n'
        '    "not_found_reason": null\n'
        "  },\n"
        "  ...\n"
        "}"
    )

    try:
        result = await call_llm(
            system_prompt=base_prompt,
            user_message=user_msg,
            stage_name="stage7_extraction",
            model="large",
            json_mode=True,
            case_id=case_id,
        )
    except LLMCallError as e:
        logger.error(f"[Stage7] Extraction LLM failed for {doc.filename}: {e}")
        return []

    extracted = []
    for field in fields:
        fn = field.field_name
        raw = result.get(fn, {})
        if not isinstance(raw, dict):
            continue
        value = raw.get("value")
        if isinstance(value, (list, dict)):
            value = json.dumps(value)
        elif value is not None:
            value = str(value).strip()
            if value.lower() in ("null", "none", "n/a", "not available", "not provided", ""):
                value = None

        extracted.append(ExtractedFieldRaw(
            field_name=fn,
            value=value,
            confidence=float(raw.get("confidence", 0.5)) if value else 0.0,
            raw_text=raw.get("raw_text") if value else None,
            chunk_id=raw.get("chunk_id") if value else None,
            not_found_reason=raw.get("not_found_reason") if not value else None,
            source_document=doc.filename,
        ))

    logger.info(
        f"[Stage7] {doc.filename}: extracted {sum(1 for e in extracted if e.value)} "
        f"of {len(fields)} fields"
    )
    return extracted


async def run(
    parsed_docs: List[ParsedDocument],
    doc_classifications: Dict[str, DocumentClassification],
    chunk_map: Dict[str, ChunkData],
    schema: ExtractionSchema,
    email_body: str,
    case_id: str,
) -> Dict[str, List[ExtractedFieldRaw]]:
    """
    Run extraction for all documents + email body in parallel.
    Returns {source_document -> [ExtractedFieldRaw]}.
    """
    tasks = []
    sources = []

    # Extract from each document
    for doc in parsed_docs:
        role = doc_classifications.get(doc.filename, DocumentClassification(
            filename=doc.filename, role="unknown", confidence=0.0, reasoning=""
        )).role
        tasks.append(_extract_from_doc(doc, role, chunk_map, schema, case_id))
        sources.append(doc.filename)

    # Also extract from email body as a virtual "submission_email" source
    if email_body.strip():
        # Build a synthetic ParsedDocument for the email
        email_doc = ParsedDocument(
            document_id="email_body",
            filename="submission_email",
            blob_url="",
            content_type="text/plain",
            full_text=email_body,
            page_count=1,
        )
        # Build email chunks inline (no ADI for email)
        email_chunk_id = "submission_email::CHUNK_001"
        email_chunk = ChunkData(
            chunk_id=email_chunk_id,
            document_name="submission_email",
            blob_url="",
            page_number=1,
            section_heading="Email Body",
            approximate_position="top_third",
            text=email_body[:v2_settings.v2_email_body_char_limit],
            word_map=[],
        )
        email_chunk_map = dict(chunk_map)
        email_chunk_map[email_chunk_id] = email_chunk

        tasks.append(_extract_from_doc(email_doc, "submission_email", email_chunk_map, schema, case_id))
        sources.append("submission_email")

    results = await asyncio.gather(*tasks, return_exceptions=True)

    extractions: Dict[str, List[ExtractedFieldRaw]] = {}
    for source, result in zip(sources, results):
        if isinstance(result, Exception):
            logger.error(f"[Stage7] Extraction failed for {source}: {result}")
            extractions[source] = []
        else:
            extractions[source] = result

    return extractions
