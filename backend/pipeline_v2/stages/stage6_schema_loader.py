"""
Stage 6 — Schema Loader
Loads the extraction schema JSON for the given case type.
Falls back to general_query.json if no specific schema found.
Schemas live in pipeline_v2/schemas/ and are fully configurable.
"""

import json
import logging
import os
from typing import Optional

from pipeline_v2.models import ExtractionSchema, SchemaField

logger = logging.getLogger(__name__)

_SCHEMAS_DIR = os.path.join(os.path.dirname(__file__), "..", "schemas")
_cache: dict = {}


def run(case_type: str) -> ExtractionSchema:
    """Load schema for case_type. Returns cached result on repeat calls."""
    if case_type in _cache:
        return _cache[case_type]

    schema_path = os.path.join(_SCHEMAS_DIR, f"{case_type}.json")
    if not os.path.exists(schema_path):
        logger.warning(f"[Stage6] No schema for '{case_type}', falling back to general_query")
        schema_path = os.path.join(_SCHEMAS_DIR, "general_query.json")

    with open(schema_path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    fields = [SchemaField(**field) for field in raw.get("fields", [])]
    schema = ExtractionSchema(case_type=raw.get("case_type", case_type), fields=fields)
    _cache[case_type] = schema
    logger.info(f"[Stage6] Loaded schema for '{case_type}': {len(fields)} fields")
    return schema
