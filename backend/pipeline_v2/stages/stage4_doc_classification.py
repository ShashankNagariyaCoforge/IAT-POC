"""
Stage 4 — Document Type Identification
One LLM call per document (parallel). Uses small model.
Assigns each attachment a role from the configured taxonomy.
"""

import asyncio
import json
import logging
from typing import Dict, List

from pipeline_v2.config import v2_settings
from pipeline_v2.models import DocumentClassification, ParsedDocument
from pipeline_v2.utils.llm_client import call_llm

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """You are classifying insurance document types.
Given a short text excerpt and email subject, identify the document role.
Return ONLY valid JSON with no other text."""


async def _classify_one(doc: ParsedDocument, email_subject: str) -> DocumentClassification:
    roles = v2_settings.document_roles_list
    roles_str = ", ".join(roles)

    # Use first 500 chars of document text as hint
    preview = doc.full_text[:500].strip() or "(no text extracted)"

    user_msg = (
        f"Email subject: {email_subject}\n"
        f"Filename: {doc.filename}\n"
        f"Document text excerpt:\n{preview}\n\n"
        f"Classify this document into exactly ONE of these roles: {roles_str}\n\n"
        f"Return JSON: {{\"role\": \"<role>\", \"confidence\": <0.0-1.0>, \"reasoning\": \"<one sentence>\"}}"
    )

    try:
        result = await call_llm(
            system_prompt=_SYSTEM_PROMPT,
            user_message=user_msg,
            stage_name="stage4_doc_classification",
            model="small",
            json_mode=True,
            max_tokens=v2_settings.v2_max_tokens_doc_classification,
        )
        role = result.get("role", "unknown")
        if role not in roles:
            role = "unknown"
        return DocumentClassification(
            filename=doc.filename,
            role=role,
            confidence=float(result.get("confidence", 0.5)),
            reasoning=result.get("reasoning", ""),
        )
    except Exception as e:
        logger.warning(f"[Stage4] Doc classification failed for {doc.filename}: {e}")
        return DocumentClassification(
            filename=doc.filename,
            role="unknown",
            confidence=0.0,
            reasoning=f"Classification failed: {e}",
        )


async def run(
    parsed_docs: List[ParsedDocument],
    email_subject: str,
) -> Dict[str, DocumentClassification]:
    """Classify all documents in parallel. Returns {filename -> DocumentClassification}."""
    if not parsed_docs:
        return {}

    tasks = [_classify_one(doc, email_subject) for doc in parsed_docs]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    doc_classifications: Dict[str, DocumentClassification] = {}
    for r in results:
        if isinstance(r, Exception):
            logger.error(f"[Stage4] Classification error: {r}")
        else:
            doc_classifications[r.filename] = r
            logger.info(f"[Stage4] {r.filename} → {r.role} ({r.confidence:.2f})")

    return doc_classifications
