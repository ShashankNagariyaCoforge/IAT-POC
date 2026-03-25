"""
Stage 5 — Case Classification
Intelligent classification using document evidence + email body + classification rules.

Key design decisions:
- Passes document TEXT SNIPPETS (not just role labels) so LLM can check for IAT policy numbers
- Loads classification_rules.json so LLM has expert override rules baked into the prompt
- Prevents "email says renewal but actually new business" type errors by requiring document evidence
"""

import json
import logging
import os
from typing import Dict, List, Optional

from pipeline_v2.config import v2_settings
from pipeline_v2.models import CaseClassification, DocumentClassification, ParsedDocument
from pipeline_v2.utils.llm_client import call_llm

logger = logging.getLogger(__name__)

_SCHEMAS_DIR = os.path.join(os.path.dirname(__file__), "..", "schemas")
_rules_cache: Optional[dict] = None


def _load_rules() -> dict:
    global _rules_cache
    if _rules_cache is None:
        path = os.path.join(_SCHEMAS_DIR, "classification_rules.json")
        with open(path, "r", encoding="utf-8") as f:
            _rules_cache = json.load(f)
    return _rules_cache


def _build_rules_summary(rules: dict) -> str:
    """
    Build a compact but complete rules block for the prompt.
    Includes decision process + per case-type override rules.
    """
    lines = []

    lines.append("=== CLASSIFICATION DECISION PROCESS ===")
    for step in rules.get("decision_process", []):
        lines.append(f"  {step}")

    lines.append("")
    lines.append("=== CASE TYPE RULES ===")
    for case_type, rule in rules.get("case_types", {}).items():
        lines.append(f"\n[{case_type}] — {rule.get('display_name', '')}")
        lines.append(f"  Definition: {rule.get('description', '')}")

        doc_signals = rule.get("document_signals", {})
        if doc_signals.get("confirms"):
            lines.append(f"  Document CONFIRMS: {'; '.join(doc_signals['confirms'][:2])}")
        if doc_signals.get("contradicts"):
            lines.append(f"  Document CONTRADICTS: {'; '.join(doc_signals['contradicts'][:2])}")

        email_signals = rule.get("email_signals", {})
        if isinstance(email_signals, dict) and email_signals.get("suggests"):
            lines.append(f"  Email keywords (hint only): {', '.join(email_signals['suggests'][:6])}")
        elif isinstance(email_signals, list):
            lines.append(f"  Email keywords (hint only): {', '.join(email_signals[:6])}")

        if rule.get("override_rule"):
            lines.append(f"  *** OVERRIDE RULE: {rule['override_rule']}")

    iat_patterns = rules.get("iat_policy_number_patterns", [])
    if iat_patterns:
        lines.append(f"\n=== IAT POLICY NUMBER PATTERNS ===")
        lines.append(f"  Look for these prefixes: {', '.join(iat_patterns)}")

    return "\n".join(lines)


def _build_document_evidence(
    doc_classifications: Dict[str, DocumentClassification],
    parsed_docs: List[ParsedDocument],
) -> str:
    """
    Build document evidence block: role + first 400 chars of text for each document.
    This lets the LLM scan for IAT policy numbers and form types.
    """
    lines = []
    doc_text_map = {d.filename: d.full_text for d in parsed_docs}

    for filename, dc in doc_classifications.items():
        snippet = (doc_text_map.get(filename, "") or "")[:400].replace("\n", " ").strip()
        lines.append(
            f"- {filename} [{dc.role}, confidence={dc.confidence:.2f}]\n"
            f"  Text preview: {snippet or '(no text extracted)'}"
        )

    return "\n".join(lines) if lines else "No attachments"


_SYSTEM_PROMPT_TEMPLATE = """\
You are classifying an insurance email submission for IAT Insurance.

YOUR TASK: Determine the correct case_type based on evidence from BOTH the email AND the documents.

IMPORTANT: Do NOT rely solely on email wording. Brokers often mislabel submissions.
A broker writing "renewal" in the email does NOT make it a renewal for IAT — you must verify.

{rules_block}

Return ONLY valid JSON with no other text.\
"""


async def run(
    email_body: str,
    doc_classifications: Dict[str, DocumentClassification],
    email_subject: str,
    case_id: str = "",
    parsed_docs: Optional[List[ParsedDocument]] = None,
) -> CaseClassification:
    """
    Classify the case using document evidence + email body + classification rules.
    `parsed_docs` is passed to give the LLM access to document text for IAT policy number search.
    """
    case_types = v2_settings.case_types_list
    lobs = v2_settings.lines_of_business_list

    rules = _load_rules()
    rules_block = _build_rules_summary(rules)
    system_prompt = _SYSTEM_PROMPT_TEMPLATE.format(rules_block=rules_block)

    # Document evidence — roles + text snippets so LLM can scan for IAT policy numbers
    doc_evidence = _build_document_evidence(
        doc_classifications,
        parsed_docs or [],
    )

    user_msg = (
        f"Subject: {email_subject}\n\n"
        f"Email body:\n{email_body[:3000]}\n\n"
        f"Attached documents (role + text preview for evidence check):\n{doc_evidence}\n\n"
        f"Available case types: {', '.join(case_types)}\n"
        f"Available lines of business: {', '.join(lobs)}\n\n"
        "Follow the CLASSIFICATION DECISION PROCESS above step by step.\n"
        "Return JSON:\n"
        "{\n"
        '  "case_type": "<one of the available case types>",\n'
        '  "line_of_business": "<one of the available lines of business>",\n'
        '  "broker_submitted": <true|false>,\n'
        '  "urgency": "<normal|urgent|critical>",\n'
        '  "confidence": <0.0-1.0>,\n'
        '  "iat_policy_number_found": <true|false>,\n'
        '  "classification_evidence": "<what specific evidence (document type, text, policy number) drove this decision>",\n'
        '  "reasoning": "<2-3 sentences explaining final decision, especially any override rules applied>"\n'
        "}"
    )

    try:
        result = await call_llm(
            system_prompt=system_prompt,
            user_message=user_msg,
            stage_name="stage5_case_classification",
            model="large",   # Use large model — classification accuracy is critical
            json_mode=True,
            max_tokens=v2_settings.v2_max_tokens_classification,
            case_id=case_id,
        )

        case_type = result.get("case_type", "general_query")
        if case_type not in case_types:
            case_type = "general_query"

        lob = result.get("line_of_business", "unknown")
        if lob not in lobs:
            lob = "unknown"

        confidence = float(result.get("confidence", 0.5))
        review_required = confidence < v2_settings.v2_classification_confidence_threshold

        # Combine reasoning + evidence for audit trail
        evidence = result.get("classification_evidence", "")
        reasoning = result.get("reasoning", "")
        full_reasoning = f"{reasoning} [Evidence: {evidence}]" if evidence else reasoning

        cls = CaseClassification(
            case_type=case_type,
            line_of_business=lob,
            broker_submitted=bool(result.get("broker_submitted", True)),
            urgency=result.get("urgency", "normal"),
            confidence=confidence,
            reasoning=full_reasoning,
            review_required=review_required,
        )
        logger.info(
            f"[Stage5] case={case_id} type={case_type} lob={lob} "
            f"confidence={confidence:.2f} iat_policy_found={result.get('iat_policy_number_found')} "
            f"review={review_required}"
        )
        return cls

    except Exception as e:
        logger.error(f"[Stage5] Case classification failed: {e}")
        return CaseClassification(
            case_type="general_query",
            line_of_business="unknown",
            broker_submitted=True,
            urgency="normal",
            confidence=0.0,
            reasoning=f"Classification failed: {e}",
            review_required=True,
        )
