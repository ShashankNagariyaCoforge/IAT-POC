"""
Stage 10 — Web Enrichment
Only triggered for fields where:
- value is null AND web_enrichable=True in schema
- Has a timeout to prevent blocking the pipeline
"""

import asyncio
import logging
from typing import List

from pipeline_v2.config import v2_settings
from pipeline_v2.models import FieldSource, MergedField, SourceLocation

logger = logging.getLogger(__name__)


async def run(
    merged_fields: List[MergedField],
    email_body: str,
    enrichment_agent,
    company_name_hint: str = "",
) -> List[MergedField]:
    """
    Run web enrichment for missing web_enrichable fields.
    Applies a hard timeout (V2_ENRICHMENT_TIMEOUT_SECONDS).
    Non-fatal: returns original fields unchanged if enrichment fails/times out.
    """
    fields_to_enrich = [
        f for f in merged_fields
        if f.web_enrichable and (f.value is None or f.status == "missing")
    ]

    if not fields_to_enrich:
        logger.info("[Stage10] No fields need web enrichment")
        return merged_fields

    logger.info(f"[Stage10] Enriching {len(fields_to_enrich)} fields via web")

    try:
        enrichment_results = await asyncio.wait_for(
            enrichment_agent.enrich(fields_to_enrich, email_body, company_name_hint=company_name_hint),
            timeout=float(v2_settings.v2_enrichment_timeout_seconds),
        )
    except asyncio.TimeoutError:
        logger.warning(f"[Stage10] Enrichment timed out after {v2_settings.v2_enrichment_timeout_seconds}s")
        return merged_fields
    except Exception as e:
        logger.warning(f"[Stage10] Enrichment failed (non-fatal): {e}")
        return merged_fields

    # Update merged fields with enrichment results
    field_map = {f.field_name: f for f in merged_fields}

    for result in enrichment_results:
        if not result.value:
            continue
        field = field_map.get(result.field_name)
        if not field:
            continue

        location = SourceLocation(
            document_name="web_enrichment",
            blob_url=result.source_url,
            page_number=0,
            bbox=None,
            raw_text=result.raw_text,
            extraction_source="web_enrichment",
        )
        source = FieldSource(
            document_name="web_enrichment",
            value=result.value,
            confidence=result.confidence,
            location=location,
        )

        field.value = result.value
        field.confidence = result.confidence
        field.status = "accepted"
        field.primary_source = source
        field.all_sources = [source]
        field.enrichment_url = result.source_url

        logger.info(f"[Stage10] Enriched field '{result.field_name}' = '{result.value}' (from {result.source_url})")

    return merged_fields
