"""
Stage 9 — Merge & Conflict Detection (Pure Python)
Collects per-document extraction results and builds a master record.
For each field: accept single value, boost multi-source agreement, flag conflicts.
"""

import logging
from typing import Dict, List, Optional, Tuple

from pipeline_v2.config import v2_settings
from pipeline_v2.models import (
    ExtractedFieldRaw, ExtractionSchema, FieldSource,
    MergedField, SourceLocation,
)

logger = logging.getLogger(__name__)


def _normalize(value: Optional[str]) -> str:
    if not value:
        return ""
    return " ".join(value.lower().strip().split())


def run(
    resolved: Dict[str, List[Tuple[ExtractedFieldRaw, Optional[SourceLocation]]]],
    schema: ExtractionSchema,
) -> List[MergedField]:
    """
    Merge extracted fields from all sources into a single master list.
    One MergedField per schema field.
    """
    # Collect all FieldSource objects per field_name
    per_field: Dict[str, List[FieldSource]] = {f.field_name: [] for f in schema.fields}

    for source_doc, field_results in resolved.items():
        for field, location in field_results:
            if field.field_name not in per_field:
                continue
            if not field.value:
                continue
            per_field[field.field_name].append(
                FieldSource(
                    document_name=source_doc,
                    value=field.value,
                    confidence=field.confidence,
                    location=location,
                )
            )

    merged: List[MergedField] = []
    threshold = v2_settings.v2_field_confidence_threshold

    for schema_field in schema.fields:
        fn = schema_field.field_name
        sources = per_field.get(fn, [])

        if not sources:
            merged.append(MergedField(
                field_name=fn,
                display_label=schema_field.display_label,
                value=None,
                confidence=0.0,
                mandatory=schema_field.mandatory,
                web_enrichable=schema_field.web_enrichable,
                status="missing",
            ))
            continue

        # Sort by confidence descending
        sources.sort(key=lambda s: s.confidence, reverse=True)
        best = sources[0]

        if len(sources) == 1:
            status = "accepted" if best.confidence >= threshold else "low_confidence"
            merged.append(MergedField(
                field_name=fn,
                display_label=schema_field.display_label,
                value=best.value,
                confidence=best.confidence,
                mandatory=schema_field.mandatory,
                web_enrichable=schema_field.web_enrichable,
                status=status,
                primary_source=best,
                all_sources=sources,
            ))
            continue

        # Multiple sources — check for agreement
        norm_values = [_normalize(s.value) for s in sources]
        unique_values = set(norm_values)

        if len(unique_values) == 1:
            # All agree — boost confidence slightly
            boosted = min(1.0, best.confidence + 0.05)
            merged.append(MergedField(
                field_name=fn,
                display_label=schema_field.display_label,
                value=best.value,
                confidence=boosted,
                mandatory=schema_field.mandatory,
                web_enrichable=schema_field.web_enrichable,
                status="accepted",
                primary_source=best,
                all_sources=sources,
            ))
        else:
            # Conflict — store all versions
            merged.append(MergedField(
                field_name=fn,
                display_label=schema_field.display_label,
                value=best.value,    # Use highest-confidence value as primary
                confidence=best.confidence,
                mandatory=schema_field.mandatory,
                web_enrichable=schema_field.web_enrichable,
                status="conflict",
                primary_source=best,
                all_sources=sources,
                conflict_values=sources,
            ))

    accepted = sum(1 for f in merged if f.status == "accepted")
    conflicts = sum(1 for f in merged if f.status == "conflict")
    missing = sum(1 for f in merged if f.status == "missing")
    logger.info(f"[Stage9] Merged: {accepted} accepted, {conflicts} conflicts, {missing} missing")
    return merged
