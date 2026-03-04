"""
Demo ingestion script.
Run this ONCE before the demo to populate the local TinyDB with 5 processed cases.

Usage:
    cd /home/azureuser/Documents/projects/IAT-POC/backend
    source .venv/bin/activate
    python demo_ingest.py

What it does:
  1. Reads each email JSON from demo_data/emails/
  2. Parses the attached PDF using DocumentParser
  3. Runs PII masking
  4. Classifies using Azure OpenAI
  5. Saves case, email, document, and classification to local TinyDB (demo_data/db.json)
"""

import asyncio
import base64
import json
import logging
import os
import sys
import uuid
from datetime import datetime

# ── Ensure backend/ is on path ─────────────────────────────────────────────
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Force DEMO_MODE on for the ingest script regardless of .env
os.environ["DEMO_MODE"] = "true"
os.environ["DEV_BYPASS_AUTH"] = "true"
os.environ["PII_ENCRYPTION_KEY"] = "ObAPE59fbMPiQyjXax/jt1mOkV+RJpuilD1gQACb3RI="
if not os.environ.get("AZURE_OPENAI_API_KEY"):
    os.environ["AZURE_OPENAI_API_KEY"] = "mock_key_for_demo_if_missing"

from config import settings
from models.case import CaseDocument, CaseStatus
from services.local_db import LocalDBService
from services.document_parser import DocumentParser
from services.pii_masker import PIIMasker
# from services.classifier import Classifier

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

EMAILS_DIR = os.path.join(os.path.dirname(__file__), "demo_data", "emails")
EXTRACTED_DIR = os.path.join(os.path.dirname(__file__), "demo_data", "extracted_text")
DB_PATH = os.path.join(os.path.dirname(__file__), "demo_data", "db.json")

# Wipe existing DB so we start fresh each time
if os.path.exists(DB_PATH):
    os.remove(DB_PATH)
    logger.info("Cleared existing demo_data/db.json")


async def ingest_email(
    email_json_path: str,
    case_sequence: int,
    db: LocalDBService,
    parser: DocumentParser,
    masker: PIIMasker,
    # classifier: Classifier,
) -> None:
    logger.info(f"\n{'='*60}")
    logger.info(f"Processing: {os.path.basename(email_json_path)}")

    with open(email_json_path, "r") as f:
        email_data = json.load(f)

    # ── Build IDs ──────────────────────────────────────────────────────────
    case_id = f"IAT-2026-{case_sequence:06d}"
    email_id = str(uuid.uuid4())
    message_id = email_data.get("internetMessageId", email_data.get("id"))
    sender = email_data["from"]["emailAddress"]["address"]
    subject = email_data.get("subject", "(No subject)")
    received_at = email_data.get("receivedDateTime", datetime.utcnow().isoformat())

    # ── Step 1: Create case (RECEIVED) ──────────────────────────────────────
    case = CaseDocument(
        case_id=case_id,
        status=CaseStatus.RECEIVED,
        subject=subject,
        sender=sender,
        email_count=1,
        created_at=datetime.fromisoformat(received_at.replace("Z", "+00:00")),
        updated_at=datetime.fromisoformat(received_at.replace("Z", "+00:00")),
    )
    await db.create_case(case)
    logger.info(f"  ✔ Created case {case_id}")

    # ── Step 2: Save email record ────────────────────────────────────────────
    internet_headers = {
        h["name"]: h["value"]
        for h in email_data.get("internetMessageHeaders", [])
    }
    email_doc = {
        "email_id": email_id,
        "case_id": case_id,
        "message_id": email_data.get("internetMessageId", message_id),
        "in_reply_to": internet_headers.get("In-Reply-To", ""),
        "references": internet_headers.get("References", "").split(),
        "sender": sender,
        "recipients": [
            r["emailAddress"]["address"]
            for r in email_data.get("toRecipients", [])
        ],
        "subject": subject,
        "received_at": received_at,
        "blob_path": "",
        "has_attachments": bool(email_data.get("attachments")),
        "attachment_count": len(email_data.get("attachments", [])),
        "body": email_data.get("body", {}).get("content", ""),
    }
    await db.create_email(email_doc)
    logger.info(f"  ✔ Saved email record")

    # ── Update status: PROCESSING ────────────────────────────────────────────
    await db.update_case_status(case_id, CaseStatus.PROCESSING)

    # ── Steps 3-6: Parse each attachment ────────────────────────────────────
    all_extracted_texts = []

    body_content = email_data.get("body", {}).get("content", "")
    if body_content:
        all_extracted_texts.append(("email_body", body_content))

    attachments = email_data.get("attachments", [])
    for attachment in attachments:
        doc_id = str(uuid.uuid4())
        filename = attachment.get("name", f"attachment_{doc_id}.pdf")
        content_bytes = base64.b64decode(attachment.get("contentBytes", ""))
        content_type = attachment.get("contentType", "application/octet-stream")
        file_ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "unknown"

        logger.info(f"  ⚙ Parsing {filename} ({len(content_bytes):,} bytes)...")

        # Parse
        parse_result = await parser.parse(filename, content_bytes)
        extracted_text = parse_result.raw_text
        logger.info(f"  ✔ Extracted {len(extracted_text):,} chars from {filename}")

        # Save extracted text locally
        os.makedirs(EXTRACTED_DIR, exist_ok=True)
        local_text_path = os.path.join(EXTRACTED_DIR, f"{doc_id}_extracted.txt")
        with open(local_text_path, "w", encoding="utf-8") as tf:
            tf.write(extracted_text)

        # Create document record
        doc_record = {
            "document_id": doc_id,
            "email_id": email_id,
            "case_id": case_id,
            "file_name": filename,
            "file_type": file_ext,
            "blob_path": "",  # no blob in demo
            "extracted_text_local_path": local_text_path,
            "ocr_required": parse_result.ocr_required,
            "ocr_applied": False,
            "has_urls": bool(parse_result.urls),
            "crawled_urls": parse_result.urls,
            "page_count": parse_result.page_count,
            "processing_status": "DONE",
            "created_at": datetime.utcnow().isoformat(),
        }
        await db.create_document(doc_record)
        all_extracted_texts.append((filename, extracted_text))

    # ── Step 7: PII masking ──────────────────────────────────────────────────
    combined_text = "\n\n---\n\n".join(
        f"[Source: {src}]\n{txt}" for src, txt in all_extracted_texts if txt
    )
    logger.info(f"  ⚙ Masking PII ({len(combined_text):,} chars)...")
    doc_id_for_masking = str(uuid.uuid4())

    try:
        masked_text, _pii_mappings = await masker.mask_text(
            combined_text, case_id, doc_id_for_masking
        )
        logger.info(f"  ✔ PII masking done")
    except Exception as e:
        logger.warning(f"  ⚠ PII masking failed ({e}), using raw text")
        masked_text = combined_text

    # ── Step 8: AI Classification (MOCKED for Demo) ─────────────────────────
    logger.info(f"  ⚙ Skipping real Azure OpenAI classification (mocking instead)...")
    # classification = await classifier.classify(masked_text)
    classification = {
        "classification_category": "Documentation Submission",
        "confidence_score": 0.95,
        "summary": "This is a mock classification summary since OpenAI credentials were skipped.",
        "key_fields": {"mock_key": "mock_value"},
        "requires_human_review": False
    }
    logger.info(
        f"  ✔ Classified as '{classification['classification_category']}' "
        f"(confidence: {classification['confidence_score']:.0%})"
    )

    # ── Step 9: Save results ─────────────────────────────────────────────────
    result_id = str(uuid.uuid4())
    classified_at = datetime.utcnow().isoformat()
    result_doc = {
        "result_id": result_id,
        "case_id": case_id,
        "email_id": email_id,
        "classification_category": classification["classification_category"],
        "confidence_score": classification["confidence_score"],
        "summary": classification["summary"],
        "key_fields": classification.get("key_fields", {}),
        "requires_human_review": classification["requires_human_review"],
        "classified_at": classified_at,
        "downstream_notification_sent": False,
        "masked_text_blob_path": "",
    }
    await db.save_classification_result(result_doc)

    final_status = (
        CaseStatus.PENDING_REVIEW
        if classification["requires_human_review"]
        else CaseStatus.CLASSIFIED
    )
    await db.update_case_status(
        case_id,
        final_status,
        classification_category=classification["classification_category"],
        confidence_score=classification["confidence_score"],
        requires_human_review=classification["requires_human_review"],
        summary=classification["summary"],
    )

    # Mark notified
    await db.update_case_status(case_id, CaseStatus.NOTIFIED)
    await db.update_classification_notification(result_id, datetime.utcnow())

    logger.info(
        f"  ✅ Case {case_id} done → status=NOTIFIED  "
        f"category='{classification['classification_category']}'"
    )


async def main():
    logger.info("🎯 IAT Demo Ingestion Script")
    logger.info(f"   Emails dir : {EMAILS_DIR}")
    logger.info(f"   DB path    : {DB_PATH}")
    logger.info(f"   OpenAI     : {settings.azure_openai_endpoint or '(from env)'}")

    db = LocalDBService()
    parser = DocumentParser()
    masker = PIIMasker()
    # Skip actual classification since endpoint isn't configured
    # classifier = Classifier()

    email_files = sorted([
        os.path.join(EMAILS_DIR, f)
        for f in os.listdir(EMAILS_DIR)
        if f.endswith(".json")
    ])

    if not email_files:
        logger.error(f"No email JSON files found in {EMAILS_DIR}")
        sys.exit(1)

    logger.info(f"\nFound {len(email_files)} email(s) to process.\n")

    for i, email_path in enumerate(email_files, 1):
        try:
            await ingest_email(email_path, i, db, parser, masker)
        except Exception as e:
            logger.error(f"  ❌ Failed to process {email_path}: {e}", exc_info=True)

    # Summary
    stats = await db.get_stats()
    logger.info(f"\n{'='*60}")
    logger.info(f"✅ Ingestion complete!")
    logger.info(f"   Total cases  : {stats['total_cases']}")
    logger.info(f"   By status    : {stats['by_status']}")
    logger.info(f"   By category  : {stats['by_category']}")
    logger.info(f"\nNow start the backend:  uvicorn main:app --reload --port 8000")
    logger.info(f"And the frontend:       cd ../frontend && npm run dev")


if __name__ == "__main__":
    asyncio.run(main())
