"""
Stage 12 — Routing Decision (Pure Python)
Determines whether the case should be auto-processed, spot-checked, or fully reviewed.
"""

import logging
from typing import List

from pipeline_v2.config import v2_settings
from pipeline_v2.models import MergedField, RoutingDecision, ValidationFlag

logger = logging.getLogger(__name__)


def run(
    merged_fields: List[MergedField],
    validation_flags: List[ValidationFlag],
    classification_confidence: float,
) -> RoutingDecision:
    """
    Determine routing based on classification confidence, field status, and validation.
    Routes: auto_process | spot_check | full_human_review
    """
    reasons = []
    flagged_fields = []
    cls_threshold = v2_settings.v2_classification_confidence_threshold
    field_threshold = v2_settings.v2_field_confidence_threshold

    # 1. Low classification confidence → full review
    if classification_confidence < cls_threshold:
        reasons.append(
            f"Low classification confidence ({classification_confidence:.2f} < {cls_threshold})"
        )
        return RoutingDecision(
            route="full_human_review",
            reasons=reasons,
            flagged_fields=[],
        )

    # 2. Validation errors → full review
    errors = [f for f in validation_flags if f.severity == "error"]
    for err in errors:
        reasons.append(f"Validation error: {err.field_name} — {err.description}")
        flagged_fields.append(err.field_name)

    # 3. Missing mandatory fields → full review
    missing_mandatory = [f for f in merged_fields if f.mandatory and f.status == "missing"]
    for mf in missing_mandatory:
        reasons.append(f"Missing mandatory field: {mf.field_name}")
        flagged_fields.append(mf.field_name)

    # 4. Conflicts → full review
    conflicts = [f for f in merged_fields if f.status == "conflict"]
    for cf in conflicts:
        reasons.append(f"Conflicting values for: {cf.field_name}")
        flagged_fields.append(cf.field_name)

    if errors or missing_mandatory or conflicts:
        return RoutingDecision(
            route="full_human_review",
            reasons=reasons,
            flagged_fields=list(set(flagged_fields)),
        )

    # 5. Low-confidence fields → spot check
    low_confidence = [
        f for f in merged_fields
        if f.value is not None and f.confidence < field_threshold
    ]
    for lc in low_confidence:
        flagged_fields.append(lc.field_name)

    # 6. Validation warnings → spot check
    warnings = [f for f in validation_flags if f.severity == "warning"]
    for w in warnings:
        flagged_fields.append(w.field_name)

    if low_confidence or warnings:
        for lc in low_confidence:
            reasons.append(f"Low confidence ({lc.confidence:.2f}): {lc.field_name}")
        return RoutingDecision(
            route="spot_check",
            reasons=reasons,
            flagged_fields=list(set(flagged_fields)),
        )

    # All good
    logger.info("[Stage12] Route: auto_process")
    return RoutingDecision(route="auto_process", reasons=[], flagged_fields=[])
