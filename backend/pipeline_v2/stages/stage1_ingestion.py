"""
Stage 1 — Ingestion
Reads existing emails and document metadata from the v1 Cosmos DB.
Returns a structured IngestionResult for downstream stages.
"""

import logging
import re
from typing import Any

from pipeline_v2.models import IngestionResult

logger = logging.getLogger(__name__)


def _strip_html(text: str) -> str:
    """Strip HTML tags and decode common entities, returning plain text."""
    if not text or "<" not in text:
        return text
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(text, "html.parser")
        # Remove script/style blocks entirely
        for tag in soup(["script", "style", "head"]):
            tag.decompose()
        plain = soup.get_text(separator="\n")
    except Exception:
        # Fallback: regex strip
        plain = re.sub(r"<[^>]+>", " ", text)
    # Collapse whitespace
    plain = re.sub(r"\n{3,}", "\n\n", plain)
    plain = re.sub(r"[ \t]{2,}", " ", plain)
    return plain.strip()


async def run(case_id: str, db_service: Any) -> IngestionResult:
    """
    Read emails and documents for this case from the existing (v1) Cosmos DB.
    The case was already ingested by the webhook pipeline — we just read it here.
    """
    emails = await db_service.get_emails_for_case(case_id)
    documents = await db_service.get_documents_for_case(case_id)

    if not emails and not documents:
        raise ValueError(f"No content found for case {case_id}")

    logger.info(f"[Stage1] case={case_id} emails={len(emails)} documents={len(documents)}")

    # Sort emails chronologically and build combined body text
    sorted_emails = sorted(emails, key=lambda e: e.get("received_at", ""))

    email_parts = []
    for em in sorted_emails:
        body = em.get("body") or em.get("body_masked", "")
        # Strip HTML tags if the body is HTML
        body = _strip_html(body)
        # Strip forwarded-message boilerplate
        for sep in ["-----Original Message-----", "________________________________", "From:"]:
            if sep in body:
                body = body.split(sep)[0]
        body = body.strip()
        if body:
            email_parts.append(f"[Email from {em.get('sender', 'unknown')}]\n{body}")

    email_body = "\n\n---\n\n".join(email_parts)

    # Get sender and subject from the first (oldest) email
    first_email = sorted_emails[0] if sorted_emails else {}
    subject = first_email.get("subject", "")
    sender = first_email.get("sender", "")
    received_at = first_email.get("received_at", "")

    # Build blob path maps for documents
    attachment_blob_paths = {}
    attachment_containers = {}
    for doc in documents:
        filename = doc.get("filename") or doc.get("file_name") or ""
        blob_path = doc.get("blob_path", "")
        if filename and blob_path:
            attachment_blob_paths[filename] = blob_path
            attachment_containers[filename] = ""  # will be resolved in Stage 2

    return IngestionResult(
        case_id=case_id,
        email_subject=subject,
        email_sender=sender,
        email_received_at=received_at,
        email_body=email_body,
        attachment_blob_paths=attachment_blob_paths,
        attachment_containers=attachment_containers,
        raw_emails=sorted_emails,
        raw_documents=documents,
    )
