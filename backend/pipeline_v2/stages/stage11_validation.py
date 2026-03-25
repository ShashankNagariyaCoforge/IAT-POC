"""
Stage 11 — Validation
One focused LLM call on the complete merged record.
Checks for logical errors, OCR artifacts, contradictions, missing mandatory fields.
Returns a list of ValidationFlags (warnings + errors).
"""

import json
import logging
import os
from typing import List

from pipeline_v2.config import v2_settings
from pipeline_v2.models import ExtractionSchema, MergedField, ValidationFlag
from pipeline_v2.utils.llm_client import call_llm, LLMCallError

logger = logging.getLogger(__name__)

_PROMPTS_DIR = os.path.join(os.path.dirname(__file__), "..", "prompts")


def _load_validation_prompt() -> str:
    path = os.path.join(_PROMPTS_DIR, "validation.txt")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    return (
        "You are validating extracted insurance fields for logical errors.\n"
        "Check ONLY for issues listed. Do not re-extract values.\n"
        "Return ONLY valid JSON with no other text."
    )


_VALIDATION_PROMPT = None


def _get_prompt() -> str:
    global _VALIDATION_PROMPT
    if _VALIDATION_PROMPT is None:
        _VALIDATION_PROMPT = _load_validation_prompt()
    return _VALIDATION_PROMPT


async def run(
    merged_fields: List[MergedField],
    schema: ExtractionSchema,
    case_id: str = "",
) -> List[ValidationFlag]:
    """
    Validate the merged record. Returns list of ValidationFlags.
    Empty list = all checks passed.
    """
    # Build a compact representation of the merged record for the LLM
    record = {
        f.field_name: {
            "value": f.value,
            "confidence": f.confidence,
            "status": f.status,
            "mandatory": f.mandatory,
        }
        for f in merged_fields
    }

    user_msg = (
        f"Extracted insurance fields:\n{json.dumps(record, indent=2)}\n\n"
        "Perform these validation checks:\n"
        "1. Date logic: effective_date / loss date / inception should be before expiry\n"
        "2. OCR suspected: values with common OCR errors (O vs 0, l vs 1, misplaced chars)\n"
        "3. Internal contradictions between related fields\n"
        "4. Missing mandatory fields (mandatory=true with null value)\n"
        "5. Format errors (e.g. invalid phone format, obviously wrong NAICS code)\n\n"
        "Return JSON:\n"
        '{"flags": [\n'
        '  {\n'
        '    "field_name": "<field>",\n'
        '    "flag_type": "<date_logic|ocr_suspected|contradiction|missing_mandatory|format_error>",\n'
        '    "severity": "<warning|error>",\n'
        '    "description": "<what is wrong>",\n'
        '    "suggested_action": "<what to do>"\n'
        '  }\n'
        ']}'
    )

    try:
        result = await call_llm(
            system_prompt=_get_prompt(),
            user_message=user_msg,
            stage_name="stage11_validation",
            model="small",
            json_mode=True,
            case_id=case_id,
        )
    except LLMCallError as e:
        logger.warning(f"[Stage11] Validation LLM failed (non-fatal): {e}")
        return []

    flags = []
    for raw_flag in result.get("flags", []):
        try:
            flags.append(ValidationFlag(**raw_flag))
        except Exception:
            pass

    errors = sum(1 for f in flags if f.severity == "error")
    warnings = sum(1 for f in flags if f.severity == "warning")
    logger.info(f"[Stage11] Validation: {errors} errors, {warnings} warnings")
    return flags
