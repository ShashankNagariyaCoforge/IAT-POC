import logging
import asyncio
from typing import Any
import re
import uuid
import os
from datetime import datetime
from pathlib import Path
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from services.extraction_service import find_field_worker
from services.pii_masker import mask_text_worker

from config import settings
from services.classifier import Classifier
from services.content_safety import ContentSafetyService
from services.pii_masker import PIIMasker
from services.blob_storage import BlobStorageService
from services.extraction_service import ExtractionService
from services.enrichment_service import EnrichmentService
from services.renderer import DocumentRenderer
from utils.pii_report import format_pii_report_html
from models.case import CaseStatus

logger = logging.getLogger(__name__)
router = APIRouter()

# ── Per-process log file ───────────────────────────────────────────────────────
LOG_FILE = Path(__file__).resolve().parent.parent / "logs" / "process.log"
_file_handler: logging.FileHandler | None = None


# Loggers that are noisy background tasks — suppress from the process log file
_SUPPRESS_IN_FILE = {
    "pymongo.client", "pymongo.connection", "pymongo.topology",
    "services.cosmos_db",
    "services.email_fetcher", "services.email_poller",
    "services.graph_client",
    "services.content_safety",   # periodic re-init noise
    "primp",                     # low-level HTTP noise from ddgs
}

class _SuppressBackgroundFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return record.name not in _SUPPRESS_IN_FILE


def _start_process_log(case_id: str) -> None:
    """Attach a plain-text FileHandler to root logger, overwriting previous run."""
    global _file_handler
    _stop_process_log()  # Remove any leftover handler from previous call
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    fh = logging.FileHandler(LOG_FILE, mode="w", encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter(
        fmt="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    fh.addFilter(_SuppressBackgroundFilter())
    logging.getLogger().addHandler(fh)
    _file_handler = fh
    logging.getLogger().info(f"=== Process started for case_id={case_id} ===")

def _stop_process_log() -> None:
    """Detach and close the file handler."""
    global _file_handler
    if _file_handler:
        logging.getLogger().removeHandler(_file_handler)
        _file_handler.close()
        _file_handler = None

def _get_cosmos():
    if settings.demo_mode:
        from services.local_db import LocalDBService
        return LocalDBService()
    from services.cosmos_db import CosmosDBService
    return CosmosDBService()


@router.post("/cases/{case_id}/process")
async def process_single_case(request: Request, case_id: str, skip_pii: bool = False):
    """
    Manually triggers the AI pipeline (Safety check + Classification) 
    for a specific case that is currently in 'RECEIVED' state.
    """
    db_service = _get_cosmos()
    case = await db_service.get_case(case_id)
    
    if not case:
        raise HTTPException(status_code=404, detail=f"Case not found: {case_id}")

    if case.get("status") != CaseStatus.RECEIVED.value:
         raise HTTPException(status_code=400, detail=f"Case {case_id} is already processed or processing.")

    # 1. Update status to processing so UI reflects it immediately
    await db_service.update_case_status(case_id, CaseStatus.PROCESSING, pii_skipped=skip_pii, pipeline_step="fetch_content")
    _start_process_log(case_id)

    try:
        classifier = Classifier()
        safety_svc = ContentSafetyService()
        masker = PIIMasker()
        blob_service = BlobStorageService()
        extraction_svc = ExtractionService()
        executor = getattr(request.app.state, "executor", None)
        loop = asyncio.get_event_loop()

        # 1. Fetch all content for merging
        emails = await db_service.get_emails_for_case(case_id)
        documents = await db_service.get_documents_for_case(case_id)
        
        logger.info(f"[Process] Fetching case {case_id}: Found {len(emails)} emails and {len(documents)} documents.")

        if not emails and not documents:
            await db_service.update_case_status(case_id, CaseStatus.FAILED, pii_skipped=skip_pii)
            raise HTTPException(status_code=400, detail="No content found for this case to process.")

        # 2. Build combined text (Raw)
        def clean_conversation_context(text: str) -> str:
            """Strips 'Original Message' and common thread separators to avoid redundancy."""
            if not text: return ""
            separators = [
                "-----Original Message-----",
                "________________________________",
                "From:",
                "On ",  # On [Date], [Name] wrote:
            ]
            cleaned = text
            for sep in separators:
                if sep in cleaned:
                    cleaned = cleaned.split(sep)[0]
            return cleaned.strip()

        text_parts = []
        # Sort chronologically (oldest first for a natural thread flow in GPT)
        sorted_emails = sorted(emails, key=lambda x: x.get('received_at', ''))
        
        for em in sorted_emails:
             body_text = em.get('body') or em.get('body_masked', '')
             if not em.get('body'): # If it's old plain text, clean it
                 from utils.html_utils import clean_html
                 body_text = clean_html(body_text)
             
             cleaned_body = clean_conversation_context(body_text)
             text_parts.append(f"[Source: Email from {em.get('sender')}]\n{cleaned_body}")
        
        doc_layout_results = {} # doc_id -> analyze_result
        doc_bytes_map = {} # doc_id -> doc_bytes

        async def process_document_item(doc):
            doc_id = doc.get("document_id")
            blob_path = doc.get("blob_path")
            filename = doc.get("filename") or doc.get("file_name") # Handle key variance
            
            logger.info(f"[Process] Processing doc: {filename} (ID: {doc_id}, Blob: {blob_path})")
            
            if not blob_path:
                logger.warning(f"[Process] Skip DI: No blob_path for {filename}")
                content = None
                if doc.get("extracted_text"):
                    content = f"[Source: Attachment {filename}]\n{doc.get('extracted_text')}"
                return doc_id, None, None, content

            try:
                # Multi-container search strategy
                containers_to_try = [
                    settings.blob_container_raw_emails,
                    settings.blob_container_attachments
                ]
                
                doc_bytes = None
                last_err = None
                used_container = None
                
                for container in containers_to_try:
                    try:
                        logger.info(f"[Process] Trying container '{container}' for blob '{blob_path}'")
                        doc_bytes = await blob_service.download_bytes(container, blob_path)
                        used_container = container
                        break
                    except Exception as e:
                        last_err = e
                        continue
                        
                if not doc_bytes:
                    # Final "Smart" fallback if the path actually IS "container/blob"
                    if "/" in blob_path:
                        parts = blob_path.split("/", 1)
                        c, b = parts[0], parts[1]
                        logger.info(f"[Process] Final fallback: Trying container '{c}', blob '{b}'")
                        doc_bytes = await blob_service.download_bytes(c, b)
                        used_container = c
                    else:
                        raise last_err or Exception(f"Blob {blob_path} not found in any container.")

                logger.info(f"[Process] Successfully downloaded {filename} from container '{used_container}'")
                
                import mimetypes
                content_type, _ = mimetypes.guess_type(filename)
                content_type = content_type or "application/octet-stream"
                
                logger.info(f"[Process] Running DI extraction on {filename} ({doc_id})")
                layout_result = await extraction_svc.analyze_document(doc_bytes, content_type)
                
                text_content = None
                # Update text parts with DI text if missing
                extracted_text = layout_result.get("content", "")
                if extracted_text:
                    text_content = f"[Source: Attachment {filename}]\n{extracted_text}"
                
                return doc_id, layout_result, doc_bytes, text_content
            except Exception as di_err:
                logger.warning(f"[Process] DI extraction failed for {filename}: {di_err}")
                text_content = None
                if doc.get("extracted_text"):
                    text_content = f"[Source: Attachment {filename}]\n{doc.get('extracted_text')}"
                return doc_id, None, None, text_content

        # Process all documents in parallel
        doc_tasks = [process_document_item(doc) for doc in documents]
        doc_results = await asyncio.gather(*doc_tasks)

        # filename → first 400 chars of extracted text (for doc classification)
        doc_snippets: dict = {}

        for doc_id, layout_result, doc_bytes, text_content in doc_results:
            if doc_id:
                if layout_result:
                    doc_layout_results[doc_id] = layout_result
                if doc_bytes:
                    doc_bytes_map[doc_id] = doc_bytes
            if text_content:
                text_parts.append(text_content)
                # Collect snippet for doc classification (strip the [Source:] label)
                body = text_content.split("\n", 1)[1] if "\n" in text_content else text_content
                # Retrieve filename from the [Source: Attachment <filename>] label
                src_line = text_content.split("\n", 1)[0]
                if "Attachment" in src_line:
                    fname = src_line.split("Attachment", 1)[1].strip().rstrip("]")
                    if fname:
                        doc_snippets[fname] = body[:400]

        combined_raw_text = "\n\n---\n\n".join(text_parts)

        # 2b. Launch web enrichment early — it only needs URLs + company name from raw text,
        #     not PII-masked text, so it can start immediately in parallel with masking.
        enrichment_svc = EnrichmentService()
        enrichment_task = asyncio.create_task(
            enrichment_svc.run_enrichment(combined_raw_text)
        )
        logger.info(f"[Process] Web enrichment task launched in background for case {case_id}")

        # 3. PII Masking (Optional)
        if not skip_pii:
            await db_service.update_case_status(case_id, CaseStatus.PROCESSING, pii_skipped=skip_pii, pipeline_step="pii_masking")
            logger.info(f"[Process] Masking PII for case {case_id} using ProcessPool (if available)")
            # Optimization: Mask each Document in parallel before merging
            # This is much faster than masking a single giant combined string sequentially.
            
            # 3a. Prepare text parts for masking
            # We want to keep the source labels outside of masking to avoid polluting PII detection
            masking_tasks = []
            
            # Helper to mask a specific source
            async def mask_source(source_label: str, raw_text: str):
                m_text, m_mappings = await masker.mask_text(
                    raw_text, 
                    case_id=case_id, 
                    document_id=case_id, # Simplified for combined report
                    executor=executor
                )
                return source_label, m_text, m_mappings

            # Emails
            for em in sorted_emails:
                 body_text = em.get('body') or em.get('body_masked', '')
                 if not em.get('body'):
                     from utils.html_utils import clean_html
                     body_text = clean_html(body_text)
                 cleaned_body = clean_conversation_context(body_text)
                 masking_tasks.append(mask_source(f"[Source: Email from {em.get('sender')}]", cleaned_body))
            
            # Documents (using DI text if available, fallback to doc.extracted_text)
            for doc_id, layout in doc_layout_results.items():
                filename = next((d.get("filename") or d.get("file_name") for d in documents if d.get("document_id") == doc_id), "Attachment")
                extracted_text = layout.get("content", "")
                if extracted_text:
                    masking_tasks.append(mask_source(f"[Source: Attachment {filename}]", extracted_text))
            
            # Execute masking in parallel
            masking_results = await asyncio.gather(*masking_tasks)
            
            masked_text_parts = []
            pii_mappings = []
            for label, m_text, m_mappings in masking_results:
                masked_text_parts.append(f"{label}\n{m_text}")
                pii_mappings.extend(m_mappings)
            
            masked_text = "\n\n---\n\n".join(masked_text_parts)
        else:
            logger.info(f"[Process] Skipping PII masking for case {case_id} as requested by UI.")
            masked_text = combined_raw_text
            pii_mappings = []

        # 4. Save PII mappings and HTML Report for download
        for mapping in pii_mappings:
            await db_service.save_pii_mapping(mapping)

        # Generate "Good HTML" Report
        html_report = format_pii_report_html(
            case_id=case_id,
            original_text=combined_raw_text,
            masked_text=masked_text,
            pii_mappings=pii_mappings
        )

        # Upload report/masked text (Blob or Local)
        report_blob_name = f"cases/{case_id}/pii_masking_report.html"
        masked_blob_name = f"cases/{case_id}/masked_full_content.txt"

        if settings.demo_mode:
            # Save locally for demo
            local_report_dir = os.path.join(settings.demo_data_dir or "demo_data", "extracted_text")
            os.makedirs(local_report_dir, exist_ok=True)
            
            with open(os.path.join(local_report_dir, f"{case_id}_pii_report.html"), "w", encoding="utf-8") as f:
                f.write(html_report)
            with open(os.path.join(local_report_dir, f"{case_id}_masked.txt"), "w", encoding="utf-8") as f:
                f.write(masked_text)
            
            # For demo, we still set these paths to something recognizable
            report_blob_path = os.path.join(local_report_dir, f"{case_id}_pii_report.html")
            masked_blob_path = os.path.join(local_report_dir, f"{case_id}_masked.txt")
        else:
            if not skip_pii:
                # Upload HTML report as a blob
                await blob_service.upload_text(
                    settings.blob_container_extracted_text,
                    report_blob_name,
                    html_report,
                    content_type="text/html"
                )
            
            await blob_service.upload_text(
                settings.blob_container_extracted_text,
                masked_blob_name,
                masked_text
            )
            report_blob_path = report_blob_name if not skip_pii else None
            masked_blob_path = masked_blob_name

        # 5 & 6. Content Safety and AI Classification (Parallel Optimization)
        # We combine these statuses into a single "Analyzing" state for the UI 
        # while they run in parallel back-to-back
        asyncio.create_task(db_service.update_case_status(
            case_id, CaseStatus.PROCESSING, pii_skipped=skip_pii, pipeline_step="classification"
        ))
        
        logger.info(f"[Process] Launching Safety, Thread Classification and Document Classification in parallel for case {case_id}")

        # Step 1: Run safety check, thread classification, and document classification in parallel
        safety_task = asyncio.create_task(safety_svc.analyze_text(masked_text))
        classification_task = asyncio.create_task(classifier.classify(masked_text, is_masked=(not skip_pii)))
        doc_classification_task = asyncio.create_task(classifier.classify_documents(doc_snippets))

        safety_result, classification, doc_type_map = await asyncio.gather(
            safety_task, classification_task, doc_classification_task
        )
        logger.info(f"[Process] Doc classification results: {doc_type_map}")

        safety_flagged_for_review = False

        if safety_result:
            logger.info(f"[ContentSafety] Scores for case {case_id}: "
                        f"Hate={safety_result.hate_severity}, "
                        f"SelfHarm={safety_result.self_harm_severity}, "
                        f"Sexual={safety_result.sexual_severity}, "
                        f"Violence={safety_result.violence_severity}")

            # Non-blocking safety update
            asyncio.create_task(db_service.update_case_safety(case_id, safety_result.model_dump()))

            max_severity = max(
                safety_result.hate_severity,
                safety_result.self_harm_severity,
                safety_result.sexual_severity,
                safety_result.violence_severity,
            )
            if max_severity >= 4:
                logger.warning(f"[ContentSafety] Case {case_id} BLOCKED. Max Severity: {max_severity}")
                await db_service.update_case_status(case_id, CaseStatus.BLOCKED_SAFETY, pii_skipped=skip_pii)
                return {"message": "Case blocked by safety guardrails."}
            elif max_severity >= 2:
                logger.info(f"[ContentSafety] Case {case_id} flagged for review. Max Severity: {max_severity}")
                safety_flagged_for_review = True

        # Step 2: Extraction — run main extraction, secondary (enrichment) extraction,
        #         and await the already-running web enrichment in parallel.
        asyncio.create_task(db_service.update_case_status(
            case_id, CaseStatus.PROCESSING, pii_skipped=skip_pii, pipeline_step="extraction"
        ))
        _submission_type = classification.get("submission_type", "Unknown")
        logger.info(
            f"[Process] Step 2 — Launching main extraction + secondary extraction in parallel. "
            f"category='{classification.get('classification_category')}' "
            f"submission_type='{_submission_type}' "
            f"iat_policy={classification.get('iat_policy_detected', False)} "
            f"expiring_carrier='{classification.get('expiring_carrier')}'"
        )

        _main_ext_task = asyncio.create_task(classifier.extract(
            masked_text,
            classification_category=classification.get("classification_category", "Unknown"),
            is_masked=(not skip_pii),
            submission_type=_submission_type,
            iat_policy_detected=bool(classification.get("iat_policy_detected", False)),
            expiring_carrier=classification.get("expiring_carrier"),
            doc_type_map=doc_type_map,
        ))
        _secondary_ext_task = asyncio.create_task(classifier.extract_enrichment_fields(
            masked_text,
            is_masked=(not skip_pii),
            submission_type=_submission_type,
        ))

        # Await all three in parallel; treat failures as non-fatal
        _parallel_results = await asyncio.gather(
            _main_ext_task,
            _secondary_ext_task,
            asyncio.wait_for(enrichment_task, timeout=240),
            return_exceptions=True,
        )
        extraction_result    = _parallel_results[0] if not isinstance(_parallel_results[0], Exception) else {}
        secondary_result     = _parallel_results[1] if not isinstance(_parallel_results[1], Exception) else {}
        enrichment_web_result = _parallel_results[2] if not isinstance(_parallel_results[2], Exception) else None

        if isinstance(_parallel_results[0], Exception):
            logger.error(f"[Process] Main extraction failed: {_parallel_results[0]}", exc_info=True)
        if isinstance(_parallel_results[1], Exception):
            logger.warning(f"[Process] Secondary extraction failed (non-fatal): {_parallel_results[1]}")
        if isinstance(_parallel_results[2], (asyncio.TimeoutError, Exception)):
            logger.warning(f"[Process] Web enrichment failed/timed out (non-fatal): {_parallel_results[2]}")
            enrichment_task.cancel()

        # Merge main extraction into classification
        classification["key_fields"] = extraction_result.get("key_fields", {})
        if "field_confidence" in extraction_result:
            classification["key_fields"]["field_confidence"] = extraction_result["field_confidence"]

        # Promote classification-level fields into key_fields so the UI can display them
        kf = classification["key_fields"]
        if not kf.get("submission_type") and classification.get("submission_type"):
            kf["submission_type"] = classification["submission_type"]
        if not kf.get("urgency") and classification.get("urgency"):
            kf["urgency"] = classification["urgency"]

        # ── Enrichment comparison: secondary extraction vs web ────────────────
        # For each of the 16 enrichment-targeted fields:
        #   - Doc wins  → value found in documents with confidence >= threshold,
        #                 OR web had nothing → merge into key_fields + traceability
        #   - Web wins  → only web found it (or web was more confident) → keep in
        #                 enrichment panel, null out from key_fields
        from services.classifier import ENRICHMENT_FIELD_KEYS

        _FIELD_THRESHOLD = 0.75
        sec_kf    = secondary_result.get("key_fields", {}) if secondary_result else {}
        sec_conf  = secondary_result.get("field_confidence", {}) if secondary_result else {}
        sec_trace = secondary_result.get("field_traceability", {}) if secondary_result else {}

        # Build a mutable copy of the web enrichment data (flat dict of field → EnrichedField dict or None)
        _web_data: dict = {}
        if enrichment_web_result and isinstance(enrichment_web_result, dict):
            _web_data = dict(enrichment_web_result)  # already model_dump()

        secondary_field_traceability: dict = {}  # traceability entries for doc-sourced enrichment fields

        for _fk in ENRICHMENT_FIELD_KEYS:
            doc_val  = sec_kf.get(_fk)
            doc_conf = float(sec_conf.get(_fk, 0.0))
            web_field = _web_data.get(_fk)
            web_val  = web_field.get("value") if isinstance(web_field, dict) else None

            doc_wins = bool(doc_val) and (doc_conf >= _FIELD_THRESHOLD or not web_val)

            if doc_wins:
                # Merge into key_fields — shown in top extraction block
                kf[_fk] = doc_val
                kf.setdefault("field_confidence", {})[_fk] = doc_conf
                trace = sec_trace.get(_fk)
                if trace:
                    secondary_field_traceability[_fk] = trace
                # Null out from web enrichment result so it doesn't appear in web panel
                if _fk in _web_data:
                    _web_data[_fk] = None
            # else: web wins — stays in _web_data for enrichment panel, not in key_fields

        # entity_type and naics_code are from main extraction — remove from web panel if found
        for _fk in ("entity_type", "naics_code"):
            if kf.get(_fk) and _fk in _web_data:
                _web_data[_fk] = None

        logger.info(
            f"[Process] Enrichment comparison: "
            f"{sum(1 for v in secondary_field_traceability.values() if v)} doc-sourced fields merged into key_fields, "
            f"{sum(1 for k in ENRICHMENT_FIELD_KEYS if isinstance(_web_data.get(k), dict) and _web_data[k].get('value'))} web-only fields kept in enrichment panel"
        )

        # ── V1 Traceability: resolve raw_text → bbox for each field ──────────
        field_traceability_raw = extraction_result.get("field_traceability", {})
        # Merge secondary extraction traceability so bbox resolver picks it up
        field_traceability_raw.update(secondary_field_traceability)
        if field_traceability_raw:
            from services.traceability_service import resolve_bbox

            # Build filename → doc_id lookup
            filename_to_doc_id = {}
            for d in documents:
                fname = (d.get("filename") or d.get("file_name") or "").lower().strip()
                if fname:
                    filename_to_doc_id[fname] = d.get("document_id")

            v1_traceability = {}
            for field_key, trace in field_traceability_raw.items():
                raw_text = trace.get("raw_text", "")
                source_doc = (trace.get("source_document") or "").strip()
                if not raw_text:
                    continue

                source_lower = source_doc.lower()
                is_email = (
                    source_lower == "email"
                    or source_lower.startswith("email from")
                    or source_lower.startswith("email")
                    or not source_lower
                )

                if is_email:
                    v1_traceability[field_key] = {
                        "source": "email",
                        "raw_text": raw_text,
                    }
                else:
                    # Match filename to doc_id (case-insensitive)
                    doc_id = filename_to_doc_id.get(source_lower)
                    if not doc_id:
                        # Partial match fallback
                        for fname, did in filename_to_doc_id.items():
                            if source_lower in fname or fname in source_lower:
                                doc_id = did
                                break

                    layout = doc_layout_results.get(doc_id) if doc_id else None
                    if layout:
                        location = resolve_bbox(raw_text, layout)
                        if location:
                            # Find doc entry for filename
                            doc_entry = next(
                                (d for d in documents if d.get("document_id") == doc_id), {}
                            )
                            v1_traceability[field_key] = {
                                "source": "document",
                                "doc_id": doc_id,
                                "document_name": doc_entry.get("filename") or doc_entry.get("file_name") or source_doc,
                                "raw_text": raw_text,
                                "page": location["page"],
                                "bbox": location["bbox"],
                                "page_width": location["page_width"],
                                "page_height": location["page_height"],
                                "unit": location["unit"],
                            }
                        else:
                            # bbox resolution failed — still record doc source without bbox
                            doc_entry = next(
                                (d for d in documents if d.get("document_id") == doc_id), {}
                            )
                            v1_traceability[field_key] = {
                                "source": "document",
                                "doc_id": doc_id,
                                "document_name": doc_entry.get("filename") or doc_entry.get("file_name") or source_doc,
                                "raw_text": raw_text,
                                "page": None,
                                "bbox": None,
                                "page_width": None,
                                "page_height": None,
                                "unit": None,
                            }
                    else:
                        # Doc not in OCR results — fall back to email-style snippet
                        v1_traceability[field_key] = {
                            "source": "email",
                            "raw_text": raw_text,
                        }

            classification["v1_traceability"] = v1_traceability
            logger.info(f"[Process] v1_traceability resolved for {len(v1_traceability)} fields "
                        f"({sum(1 for v in v1_traceability.values() if v.get('bbox'))} with bbox, "
                        f"{sum(1 for v in v1_traceability.values() if v['source'] == 'email')} from email)")
        else:
            classification["v1_traceability"] = {}

        # Stamp result metadata
        classification["result_id"] = str(uuid.uuid4())
        classification["case_id"] = case_id
        classification["classified_at"] = datetime.utcnow().isoformat()
        classification["masked_text_blob_path"] = masked_blob_path
        classification["pii_report_blob_path"] = report_blob_path

        # 6.1 Ensure documents list is populated from actual attachments
        # This provides a reliable source of truth even if LLM extraction fails due to truncation.
        if "key_fields" not in classification:
            classification["key_fields"] = {}

        from services.classifier import DOC_TYPE_LABELS
        classification["key_fields"]["documents"] = [
            {
                "fileName": d.get("filename") or d.get("file_name"),
                "fileType": doc_type_map.get(
                    d.get("filename") or d.get("file_name") or "", "other"
                ),
                "documentDescription": DOC_TYPE_LABELS.get(
                    doc_type_map.get(d.get("filename") or d.get("file_name") or "", "other"),
                    "Other Document"
                ),
            }
            for d in documents
        ]

        # 6.4 Pre-decrypt PII mappings for spatial matching
        placeholder_to_originals = {}
        for m in pii_mappings:
            mv = m["masked_value"]
            if mv not in placeholder_to_originals:
                placeholder_to_originals[mv] = set()
            try:
                # Internal decryption helper
                orig = masker._decrypt(m["original_value_encrypted"])
                placeholder_to_originals[mv].add(orig)
            except Exception:
                pass

        # 6.5 Match Key Fields to Locations (Parallel Extraction)
        # Using create_task for the status update to let CPU initialization start immediately
        asyncio.create_task(db_service.update_case_status(case_id, CaseStatus.PROCESSING, pii_skipped=skip_pii, pipeline_step="extraction"))
        extraction_results = []
        doc_tables = [] # List of extracted tables across all docs
        
        for doc_id, layout in doc_layout_results.items():
            # Capture table structure for the frontend
            tables = extraction_svc.extract_tables(layout)
            for t in tables:
                t["doc_id"] = doc_id
                doc_tables.append(t)

        # Collect all leaf nodes for parallel processing
        fields_to_extract = []

        def collect_fields(data: Any, prefix: str = ""):
            if isinstance(data, dict):
                for k, v in data.items():
                    SPECIAL_KEYS = {
                        "name": "Insured: Name",
                        "agency": "Agency",
                        "naics_code": "NAICS Code",
                        "sic_code": "SIC Code",
                        "iat_product": "IAT Product",
                        "uw_am": "UW / AM"
                    }
                    if k in SPECIAL_KEYS:
                        clean_k = SPECIAL_KEYS[k]
                    else:
                        clean_k = re.sub(r'([a-z])([A-Z])', r'\1 \2', k).replace("_", " ").title()
                    
                    new_prefix = f"{prefix}: {clean_k}" if prefix else clean_k
                    collect_fields(v, new_prefix)
            elif isinstance(data, list):
                for i, item in enumerate(data):
                    new_prefix = f"{prefix} [{i+1}]"
                    collect_fields(item, new_prefix)
            elif data and str(data).lower() not in ["null", "none", "—", "n/a", "not available", "not provided", "none"]:
                fields_to_extract.append((prefix, str(data)))

        collect_fields(classification.get("key_fields", {}))
        logger.info(f"[Extraction] Collected {len(fields_to_extract)} fields for extraction.")

        # Semaphore to limit concurrency (e.g. 16 fields at a time) to avoid too many parallel DI/Executor calls
        sem = asyncio.Semaphore(16)

        async def extract_single_field(field_label: str, raw_value: str):
            async with sem:
                # If the value is a placeholder, try to search for the original text
                search_values = [raw_value]
                if raw_value in placeholder_to_originals:
                    search_values.extend(list(placeholder_to_originals[raw_value]))
                
                # Remove duplicates and empty strings
                search_values = list(set([v for v in search_values if v and v.strip()]))
                
                instances = []
                
                # Search document by document
                for doc_id, layout in doc_layout_results.items():
                    doc_field_matches = []
                    for val in search_values:
                        if executor:
                            matches = await loop.run_in_executor(executor, find_field_worker, layout, val)
                        else:
                            matches = await asyncio.to_thread(extraction_svc.find_field_in_lines, layout, val)
                        
                        for m in matches:
                            m["doc_id"] = doc_id
                            doc_field_matches.append(m)
                    
                    if doc_field_matches:
                        doc_field_matches.sort(key=lambda x: (x.get("similarity", 0), x.get("confidence", 0)), reverse=True)
                        best_in_doc = doc_field_matches[0]
                        instances.extend(doc_field_matches)
                        
                        # Early Exit Check
                        if best_in_doc.get("similarity", 0) >= 0.95:
                            break 
                
                if instances:
                    instances.sort(key=lambda x: (x.get("similarity", 0), x.get("confidence", 0)), reverse=True)
                    if "[" not in field_label:
                        instances = [instances[0]]
                    
                    extraction_results.append({
                        "field": field_label,
                        "value": raw_value,
                        "instances": instances
                    })

        if fields_to_extract:
            extraction_tasks = [extract_single_field(f, v) for f, v in fields_to_extract]
            await asyncio.gather(*extraction_tasks)
            logger.info(f"[Extraction] Parallel extraction complete. Found {len(extraction_results)} matches.")
        
        classification["extraction_results"] = extraction_results
        classification["extracted_tables"] = doc_tables
        
        # 6.6 Generate Annotated PDFs
        logger.info(f"[Process] Generating annotated PDFs for {len(doc_layout_results)} documents in parallel...")
        annotated_docs = {}
        renderer = DocumentRenderer()

        async def render_and_upload(doc_id, layout):
            try:
                orig_bytes = doc_bytes_map.get(doc_id)
                if not orig_bytes:
                    logger.warning(f"[Process] Missing original bytes for doc {doc_id}")
                    return None, None
                
                # Find filename for this doc_id
                doc_entry = next((d for d in documents if d.get("document_id") == doc_id), {})
                filename = doc_entry.get("filename") or doc_entry.get("file_name") or f"{doc_id}.pdf"
                
                logger.info(f"[Process] Rendering annotated PDF for {filename} ({doc_id})")
                
                if filename.lower().endswith(('.png', '.jpg', '.jpeg')):
                    # Use ProcessPool for rendering if available
                    if executor:
                        annotated_bytes = await loop.run_in_executor(
                            executor, 
                            renderer.render_image_to_annotated, 
                            orig_bytes, 
                            layout.get("pages", [{}])[0], 
                            extraction_results
                        )
                    else:
                        annotated_bytes = await asyncio.to_thread(
                            renderer.render_image_to_annotated, 
                            orig_bytes, 
                            layout.get("pages", [{}])[0], 
                            extraction_results
                        )
                else:
                    # PDF or Scanned PDF
                    if executor:
                        annotated_bytes = await loop.run_in_executor(
                            executor, 
                            renderer.render_pdf_to_annotated, 
                            filename, 
                            layout, 
                            extraction_results, 
                            orig_bytes
                        )
                    else:
                        annotated_bytes = await asyncio.to_thread(
                            renderer.render_pdf_to_annotated, 
                            filename, 
                            layout, 
                            extraction_results, 
                            orig_bytes
                        )
                
                if not annotated_bytes:
                    logger.warning(f"[Process] Failed to generate annotated bytes for {filename}")
                    return None, None

                annotated_blob_name = f"annotated/{case_id}/{doc_id}_annotated.pdf"
                upload_container = settings.blob_container_raw_emails
                logger.info(f"[Process] Uploading annotated PDF for {filename} to {annotated_blob_name}")
                
                await blob_service.upload_bytes(
                    upload_container,
                    annotated_blob_name,
                    annotated_bytes,
                    content_type="application/pdf"
                )
                return doc_id, annotated_blob_name
            except Exception as e:
                logger.error(f"Failed to render/upload doc {doc_id}: {e}", exc_info=True)
                return None, None

        # Execute rendering and uploading in parallel
        render_tasks = [render_and_upload(doc_id, layout) for doc_id, layout in doc_layout_results.items()]
        render_results = await asyncio.gather(*render_tasks)

        for doc_id, blob_name in render_results:
            if doc_id and blob_name:
                annotated_docs[doc_id] = blob_name

        classification["annotated_docs"] = annotated_docs
        print(f"DEBUG [Process]: Phase 6 complete. Found {len(annotated_docs)} annotated documents.")
        
        # 6.7 Save Classification Result with Annotated Paths
        logger.info(f"[Extraction] Final extraction results count: {len(extraction_results)}")
        # Non-blocking save
        asyncio.create_task(db_service.save_classification_result(classification))

        # 6.8 Save enrichment results (already awaited in parallel with extraction above)
        try:
            if _web_data:
                # Backfill company_name from classification if enrichment didn't find one
                if not _web_data.get("company_name"):
                    company_from_cls = classification.get("key_fields", {}).get("name", "")
                    if company_from_cls:
                        _web_data["company_name"] = company_from_cls

                enrichment_doc = {
                    "case_id": case_id,
                    "result_id": str(uuid.uuid4()),
                    "enrichment": _web_data,
                    "enriched_at": datetime.utcnow().isoformat(),
                }
                await db_service.save_enrichment_result(enrichment_doc)
                logger.info(f"[Process] Enrichment results saved for case {case_id}")
            else:
                logger.info(f"[Process] No web enrichment data to save for case {case_id}")
        except Exception as enrich_err:
            logger.warning(f"[Process] Enrichment save failed (non-fatal) for case {case_id}: {enrich_err}")

        # 7. Final Status Update
        if not safety_flagged_for_review:
            await db_service.update_case_status(
                case_id, CaseStatus.PROCESSED,
                classification_category=classification["classification_category"],
                confidence_score=classification["confidence_score"],
                requires_human_review=classification["requires_human_review"],
                pii_skipped=skip_pii,
                pipeline_step="completed"
            )
        else:
            await db_service.update_case_status(
                case_id, CaseStatus.NEEDS_REVIEW_SAFETY,
                classification_category=classification["classification_category"],
                confidence_score=classification["confidence_score"],
                requires_human_review=True,
                pii_skipped=skip_pii,
                pipeline_step="completed"
            )
            
        logger.info(f"=== Process completed successfully for case_id={case_id} ===")
        _stop_process_log()
        print(f"SUCCESS [Process]: Total case {case_id} processed successfully.")
        return {"message": f"Successfully processed case {case_id}"}

    except Exception as e:
        logger.error(f"[Process] Failed processing case {case_id}: {e}", exc_info=True)
        logger.info(f"=== Process FAILED for case_id={case_id} ===")
        _stop_process_log()
        print(f"CRITICAL ERROR [Process]: Failed processing case {case_id}: {e}")
        # Attempt to set status to FAILED in DB — always try, never silently swallow
        try:
            _fail_db = _get_cosmos()
            await _fail_db.update_case_status(case_id, CaseStatus.FAILED, pii_skipped=skip_pii)
            logger.info(f"[Process] Successfully set case {case_id} to FAILED status")
        except Exception as fail_err:
            logger.error(f"[Process] CRITICAL: could not set FAILED status for case {case_id}: {fail_err}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
