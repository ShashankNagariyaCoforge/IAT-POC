"""
Reasoning Agent — Cross-document conflict resolution.
Called when Stage 9 detects conflicting values for the same field across documents.
Uses a focused LLM call to determine the authoritative value.
"""

import json
import logging
from typing import List

from pipeline_v2.models import FieldSource, MergedField
from pipeline_v2.utils.llm_client import call_llm, LLMCallError

logger = logging.getLogger(__name__)

_SYSTEM = (
    "You are resolving conflicting values extracted from multiple insurance documents.\n"
    "Given multiple source values for a single field, determine the most authoritative one.\n"
    "Prefer: formal PDFs > emails > unknown sources. "
    "Prefer: higher confidence > lower confidence.\n"
    "Return ONLY valid JSON."
)


async def resolve_conflict(field: MergedField, case_id: str = "") -> MergedField:
    """
    For a field with status='conflict', use LLM to pick the best value.
    Returns the field with updated value, confidence, and status.
    """
    if field.status != "conflict" or not field.conflict_values:
        return field

    sources_json = json.dumps(
        [
            {
                "document": s.document_name,
                "value": s.value,
                "confidence": s.confidence,
            }
            for s in field.conflict_values
        ],
        indent=2,
    )

    user_msg = (
        f"Field: {field.display_label} ({field.field_name})\n\n"
        f"Conflicting values from different sources:\n{sources_json}\n\n"
        "Which value is most likely correct? Return JSON:\n"
        '{"best_value": "<chosen value>", "confidence": <0.0-1.0>, "reasoning": "<one sentence>"}'
    )

    try:
        result = await call_llm(
            system_prompt=_SYSTEM,
            user_message=user_msg,
            stage_name="reasoning_agent_conflict",
            model="small",
            json_mode=True,
            max_tokens=300,
            case_id=case_id,
        )
        best_value = result.get("best_value")
        if best_value:
            # Find matching source for location data
            matching_source = next(
                (s for s in field.conflict_values if s.value == best_value),
                field.primary_source,
            )
            field.value = best_value
            field.confidence = float(result.get("confidence", field.confidence))
            field.status = "accepted"
            field.primary_source = matching_source
            logger.info(
                f"[ReasoningAgent] Resolved conflict for '{field.field_name}': "
                f"'{best_value}' ({field.confidence:.2f})"
            )
    except LLMCallError as e:
        logger.warning(f"[ReasoningAgent] Conflict resolution failed for {field.field_name}: {e}")

    return field


async def resolve_conflicts(fields: List[MergedField], case_id: str = "") -> List[MergedField]:
    """Resolve all conflicting fields using the reasoning agent."""
    import asyncio
    conflict_fields = [f for f in fields if f.status == "conflict"]
    if not conflict_fields:
        return fields

    logger.info(f"[ReasoningAgent] Resolving {len(conflict_fields)} conflicts")
    resolved = await asyncio.gather(
        *[resolve_conflict(f, case_id) for f in conflict_fields],
        return_exceptions=True,
    )

    field_map = {f.field_name: f for f in fields}
    for r in resolved:
        if isinstance(r, MergedField):
            field_map[r.field_name] = r

    return list(field_map.values())
