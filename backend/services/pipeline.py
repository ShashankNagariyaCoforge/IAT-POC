"""
Pipeline orchestrator (Step 12).
Coordinates the full 9-step processing pipeline for each incoming email:
  1. Save email + attachments to blob
  2. Detect chain → create or update Case
  3. Parse documents
  4. OCR (conditional)
  5. Web crawl (conditional)
  6. Merge all text
  7. PII masking
  8. GPT classification
  9. Save results, update case, send notification
"""

import base64
import json
import logging
import uuid
from datetime import datetime

from config import settings
from models.case import CaseStatus
from services.blob_storage import BlobStorageService
from services.case_manager import CaseManager
from services.classifier import Classifier
from services.cosmos_db import CosmosDBService
from services.document_parser import DocumentParser
from services.graph_client import GraphClient
from services.notifier import Notifier
from services.ocr_service import OCRService
from services.pii_masker import PIIMasker
from services.web_crawler import WebCrawler

logger = logging.getLogger(__name__)


async def run_pipeline(message_id: str) -> None:
    """
    Full 9-step processing pipeline for one email.
    All errors are caught; case status is set to FAILED on any unrecoverable error.

    Args:
        message_id: The Graph API message ID received from the webhook notification.
    """
    case_id = None
    cosmos = CosmosDBService()
    blob = BlobStorageService()
    graph = GraphClient()
    parser = DocumentParser()
    ocr = OCRService()
    crawler = WebCrawler()
    masker = PIIMasker()
    classifier = Classifier()
    case_mgr = CaseManager(cosmos)
    notifier = Notifier(graph)

    try:
        # ── Step 1: Fetch email and save to blob ──────────────────────────────
        logger.info(f"[Pipeline] Fetching email: {message_id}")
        email_data = await graph.fetch_email(message_id)
        attachments = await graph.fetch_attachments(message_id)

        # ── Step 2: Email chain detection → create or update Case ─────────────
        case_id = await case_mgr.resolve_case(email_data)
        logger.info(f"[Pipeline] Resolved to case: {case_id}")

        # Save raw email JSON to blob
        email_blob_name = blob.build_blob_name(case_id, f"{message_id}.json")
        await blob.upload_text(
            settings.blob_container_raw_emails,
            email_blob_name,
            json.dumps(email_data),
        )

        # Save email record to Cosmos DB
        email_id = str(uuid.uuid4())
        internet_headers = {
            h["name"]: h["value"]
            for h in email_data.get("internetMessageHeaders", [])
        }
        email_doc = {
            "email_id": email_id,
            "case_id": case_id,
            "message_id": email_data.get("internetMessageId", message_id),
            "in_reply_to": internet_headers.get("In-Reply-To"),
            "references": internet_headers.get("References", "").split(),
            "sender": email_data.get("from", {}).get("emailAddress", {}).get("address", ""),
            "recipients": [r["emailAddress"]["address"] for r in email_data.get("toRecipients", [])],
            "subject": email_data.get("subject", ""),
            "received_at": email_data.get("receivedDateTime", datetime.utcnow().isoformat()),
            "blob_path": email_blob_name,
            "has_attachments": len(attachments) > 0,
            "attachment_count": len(attachments),
        }
        await cosmos.create_email(email_doc)

        # Update case status to PROCESSING
        await cosmos.update_case_status(case_id, CaseStatus.PROCESSING)

        # ── Steps 3-6: Parse each attachment ─────────────────────────────────
        all_extracted_texts = []

        # Also include the email body text
        body_content = email_data.get("body", {}).get("content", "")
        if body_content:
            all_extracted_texts.append(("email_body", body_content))

        for attachment in attachments:
            doc_id = str(uuid.uuid4())
            filename = attachment.get("name", f"attachment_{doc_id}")
            content_bytes = base64.b64decode(attachment.get("contentBytes", ""))
            content_type = attachment.get("contentType", "application/octet-stream")

            # Save raw attachment to blob
            att_blob_name = blob.build_blob_name(case_id, filename, prefix="attachments")
            await blob.upload_bytes(settings.blob_container_attachments, att_blob_name, content_bytes, content_type)

            # Create document record
            doc_record = {
                "document_id": doc_id,
                "email_id": email_id,
                "case_id": case_id,
                "file_name": filename,
                "file_type": filename.rsplit(".", 1)[-1].lower() if "." in filename else "unknown",
                "blob_path": att_blob_name,
                "ocr_required": False,
                "ocr_applied": False,
                "has_urls": False,
                "crawled_urls": [],
                "processing_status": "PROCESSING",
                "created_at": datetime.utcnow().isoformat(),
            }

            # Step 3: Parse document
            parse_result = await parser.parse(filename, content_bytes)
            extracted_text = parse_result.raw_text

            # Step 4: OCR if needed
            if parse_result.ocr_required:
                logger.info(f"[Pipeline] Running OCR on {filename}")
                doc_record["ocr_required"] = True
                try:
                    extracted_text = await ocr.extract_text(content_bytes, content_type)
                    doc_record["ocr_applied"] = True
                except Exception as ocr_err:
                    logger.error(f"[Pipeline] OCR failed for {filename}: {ocr_err}")

            # Step 5: Web crawl if URLs found
            crawled_text_parts = []
            if parse_result.urls:
                logger.info(f"[Pipeline] Crawling {len(parse_result.urls)} URLs from {filename}")
                doc_record["has_urls"] = True
                doc_record["crawled_urls"] = parse_result.urls
                url_texts = await crawler.crawl_urls(parse_result.urls)
                for url, text in url_texts.items():
                    if text:
                        crawled_text_parts.append(f"[From URL: {url}]\n{text}")

            # Step 6: Merge text from parser + crawled
            merged = "\n\n".join(filter(None, [extracted_text] + crawled_text_parts))
            all_extracted_texts.append((filename, merged))

            # Save extracted text to blob
            text_blob_name = blob.build_blob_name(case_id, f"{doc_id}_extracted.txt")
            await blob.upload_text(settings.blob_container_extracted_text, text_blob_name, merged)
            doc_record["extracted_text_blob_path"] = text_blob_name
            doc_record["processing_status"] = "DONE"
            await cosmos.create_document(doc_record)

        # Combine all emails and document texts
        combined_text = "\n\n---\n\n".join(
            f"[Source: {src}]\n{txt}" for src, txt in all_extracted_texts if txt
        )

        # ── Step 7: PII masking ───────────────────────────────────────────────
        logger.info(f"[Pipeline] Masking PII for case {case_id}")
        doc_id_for_masking = str(uuid.uuid4())
        masked_text, pii_mappings = await masker.mask_text(combined_text, case_id, doc_id_for_masking)

        # Save masked text to blob
        masked_blob_name = blob.build_blob_name(case_id, "masked_text.txt")
        await blob.upload_text(settings.blob_container_extracted_text, masked_blob_name, masked_text)

        # Save PII mappings (encrypted) to Cosmos — NEVER expose in API
        for mapping in pii_mappings:
            await cosmos.save_pii_mapping(mapping)

        # ── Step 8: GPT-4o-mini classification ───────────────────────────────
        logger.info(f"[Pipeline] Classifying case {case_id}")
        classification = await classifier.classify(masked_text)

        # ── Step 9: Save results, update case status ──────────────────────────
        result_id = str(uuid.uuid4())
        result_doc = {
            "result_id": result_id,
            "case_id": case_id,
            "email_id": email_id,
            "classification_category": classification["classification_category"],
            "confidence_score": classification["confidence_score"],
            "summary": classification["summary"],
            "key_fields": classification.get("key_fields", {}),
            "routing_recommendation": classification["routing_recommendation"],
            "requires_human_review": classification["requires_human_review"],
            "classified_at": datetime.utcnow().isoformat(),
            "masked_text_blob_path": masked_blob_name,
            "downstream_notification_sent": False,
        }
        await cosmos.save_classification_result(result_doc)

        # Determine final case status
        final_status = (
            CaseStatus.PENDING_REVIEW
            if classification["requires_human_review"]
            else CaseStatus.CLASSIFIED
        )
        await cosmos.update_case_status(
            case_id,
            final_status,
            classification_category=classification["classification_category"],
            confidence_score=classification["confidence_score"],
            requires_human_review=classification["requires_human_review"],
            routing_recommendation=classification["routing_recommendation"],
            summary=classification["summary"],
        )

        # Send downstream notification
        await notifier.send_notification(case_id, result_doc)
        await cosmos.update_case_status(case_id, CaseStatus.NOTIFIED)
        await cosmos.update_classification_notification(result_id, datetime.utcnow())

        logger.info(f"[Pipeline] Case {case_id} completed successfully. Category: {classification['classification_category']}")

    except Exception as e:
        logger.error(f"[Pipeline] Fatal error for message {message_id}: {e}", exc_info=True)
        if case_id:
            try:
                await cosmos.update_case_status(case_id, CaseStatus.FAILED)
            except Exception as update_err:
                logger.error(f"[Pipeline] Also failed to update case status: {update_err}")
