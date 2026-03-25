"""
Stage 2 — Parsing & OCR
Downloads each attachment from blob and runs Azure Document Intelligence.
All documents processed in parallel. Returns ParsedDocument list.
"""

import asyncio
import logging
import mimetypes
from typing import List

from pipeline_v2.models import IngestionResult, ParsedDocument
from pipeline_v2.utils import blob_client, ocr_client
from config import settings as base_settings

logger = logging.getLogger(__name__)

# Containers to search when downloading attachments (same as process.py)
_DOWNLOAD_CONTAINERS = [
    base_settings.blob_container_raw_emails,
    base_settings.blob_container_attachments,
]


async def _parse_single_doc(doc: dict) -> ParsedDocument:
    filename = doc.get("filename") or doc.get("file_name") or "attachment"
    blob_path = doc.get("blob_path", "")
    doc_id = doc.get("document_id", filename)

    # Build blob URL for traceability (informational, not for download)
    blob_url = f"{base_settings.blob_container_raw_emails}/{blob_path}"

    if not blob_path:
        # No blob — use any pre-extracted text
        text = doc.get("extracted_text", "")
        logger.warning(f"[Stage2] No blob_path for {filename}, using extracted_text")
        return ParsedDocument(
            document_id=doc_id,
            filename=filename,
            blob_url=blob_url,
            content_type="text/plain",
            full_text=text,
            page_count=1,
        )

    try:
        doc_bytes, used_container = await blob_client.download_bytes_multi_container(
            blob_path, _DOWNLOAD_CONTAINERS
        )
    except Exception as e:
        logger.warning(f"[Stage2] Could not download {filename}: {e}")
        text = doc.get("extracted_text", "")
        return ParsedDocument(
            document_id=doc_id,
            filename=filename,
            blob_url=blob_url,
            content_type="application/octet-stream",
            full_text=text,
            page_count=1,
        )

    content_type, _ = mimetypes.guess_type(filename)
    content_type = content_type or "application/octet-stream"

    # Skip ADI for plain text files
    if content_type == "text/plain":
        return ParsedDocument(
            document_id=doc_id,
            filename=filename,
            blob_url=blob_url,
            content_type=content_type,
            full_text=doc_bytes.decode("utf-8", errors="ignore"),
            page_count=1,
        )

    try:
        logger.info(f"[Stage2] Running ADI on {filename} ({len(doc_bytes)} bytes)")
        adi_result = await ocr_client.analyze_document(doc_bytes, content_type)
        page_count = len(adi_result.get("pages", [])) or 1
        return ParsedDocument(
            document_id=doc_id,
            filename=filename,
            blob_url=blob_url,
            content_type=content_type,
            full_text=adi_result.get("full_text", ""),
            page_count=page_count,
            pages=adi_result.get("pages", []),
            paragraphs=adi_result.get("paragraphs", []),
            tables=adi_result.get("tables", []),
        )
    except Exception as e:
        logger.warning(f"[Stage2] ADI failed for {filename}: {e}")
        fallback_text = doc.get("extracted_text", "")
        return ParsedDocument(
            document_id=doc_id,
            filename=filename,
            blob_url=blob_url,
            content_type=content_type,
            full_text=fallback_text,
            page_count=1,
        )


async def run(ingestion: IngestionResult) -> List[ParsedDocument]:
    """Parse all attachments in parallel. Returns list of ParsedDocuments."""
    if not ingestion.raw_documents:
        logger.info(f"[Stage2] No documents to parse for case {ingestion.case_id}")
        return []

    tasks = [_parse_single_doc(doc) for doc in ingestion.raw_documents]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    parsed = []
    for r in results:
        if isinstance(r, Exception):
            logger.error(f"[Stage2] Document parse error: {r}")
        else:
            parsed.append(r)

    logger.info(f"[Stage2] Parsed {len(parsed)} documents for case {ingestion.case_id}")
    return parsed
