import logging
from typing import Any
import re
import uuid
import os
from datetime import datetime
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from config import settings
from services.classifier import Classifier
from services.content_safety import ContentSafetyService
from services.pii_masker import PIIMasker
from services.blob_storage import BlobStorageService
from services.extraction_service import ExtractionService
from utils.pii_report import format_pii_report_html
from models.case import CaseStatus

logger = logging.getLogger(__name__)
router = APIRouter()

def _get_cosmos():
    if settings.demo_mode:
        from services.local_db import LocalDBService
        return LocalDBService()
    from services.cosmos_db import CosmosDBService
    return CosmosDBService()


@router.post("/cases/{case_id}/process")
async def process_single_case(case_id: str):
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
    await db_service.update_case_status(case_id, CaseStatus.PROCESSING)

    try:
        classifier = Classifier()
        safety_svc = ContentSafetyService()
        masker = PIIMasker()
        blob_service = BlobStorageService()
        extraction_svc = ExtractionService()

        # 1. Fetch all content for merging
        emails = await db_service.get_emails_for_case(case_id)
        documents = await db_service.get_documents_for_case(case_id)
        
        logger.info(f"[Process] Fetching case {case_id}: Found {len(emails)} emails and {len(documents)} documents.")

        if not emails and not documents:
            await db_service.update_case_status(case_id, CaseStatus.FAILED)
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
        for doc in documents:
            doc_id = doc.get("document_id")
            blob_path = doc.get("blob_path")
            filename = doc.get("filename") or doc.get("file_name") # Handle key variance
            
            logger.info(f"[Process] Processing doc: {filename} (ID: {doc_id}, Blob: {blob_path})")
            
            # Fetch bytes from blob
            if blob_path:
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
                    doc_layout_results[doc_id] = layout_result
                    
                    # Update text parts with DI text if missing
                    extracted_text = layout_result.get("content", "")
                    if extracted_text:
                        text_parts.append(f"[Source: Attachment {filename}]\n{extracted_text}")
                except Exception as di_err:
                    logger.warning(f"[Process] DI extraction failed for {filename}: {di_err}")
                    if doc.get("extracted_text"):
                        text_parts.append(f"[Source: Attachment {filename}]\n{doc.get('extracted_text')}")
            else:
                logger.warning(f"[Process] Skip DI: No blob_path for {filename}")
                if doc.get("extracted_text"):
                    text_parts.append(f"[Source: Attachment {filename}]\n{doc.get('extracted_text')}")
        
        combined_raw_text = "\n\n---\n\n".join(text_parts)

        # 3. PII Masking (with chunking handled inside PIIMasker)
        logger.info(f"[Process] Masking PII for case {case_id}")
        masked_text, pii_mappings = await masker.mask_text(
            combined_raw_text, 
            case_id=case_id, 
            document_id=case_id  # Use case_id as doc_id for the combined report
        )

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
            report_blob_path = report_blob_name
            masked_blob_path = masked_blob_name

        # 5. Content Safety (on masked text)
        safety_result = await safety_svc.analyze_text(masked_text)
        safety_flagged_for_review = False
        
        if safety_result:
            logger.info(f"[ContentSafety] Scores for case {case_id}: "
                        f"Hate={safety_result.hate_severity}, "
                        f"SelfHarm={safety_result.self_harm_severity}, "
                        f"Sexual={safety_result.sexual_severity}, "
                        f"Violence={safety_result.violence_severity}")
            
            await db_service.update_case_safety(case_id, safety_result.model_dump())
            max_severity = max(
                safety_result.hate_severity,
                safety_result.self_harm_severity,
                safety_result.sexual_severity,
                safety_result.violence_severity,
            )
            if max_severity >= 4:
                logger.warning(f"[ContentSafety] Case {case_id} BLOCKED. Max Severity: {max_severity}")
                await db_service.update_case_status(case_id, CaseStatus.BLOCKED_SAFETY)
                return {"message": "Case blocked by safety guardrails."}
            elif max_severity >= 2:
                logger.info(f"[ContentSafety] Case {case_id} flagged for review. Max Severity: {max_severity}")
                safety_flagged_for_review = True

        # 6. AI Classification
        classification = await classifier.classify(masked_text)
        classification["result_id"] = str(uuid.uuid4())
        classification["case_id"] = case_id
        classification["classified_at"] = datetime.utcnow().isoformat()
        classification["masked_text_blob_path"] = masked_blob_path
        classification["pii_report_blob_path"] = report_blob_path

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

        # 6.5 Match Key Fields to Locations (Recursive Extraction)
        extraction_results = []
        doc_tables = [] # List of extracted tables across all docs
        
        for doc_id, layout in doc_layout_results.items():
            # Capture table structure for the frontend
            tables = extraction_svc.extract_tables(layout)
            for t in tables:
                t["doc_id"] = doc_id
                doc_tables.append(t)

        def recursive_extract(data: Any, prefix: str = ""):
            if isinstance(data, dict):
                for k, v in data.items():
                    # Clean the key for display (e.g. agencyName -> Agency Name)
                    # Add space before capitals for CamelCase, then replace _ with space
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
                    recursive_extract(v, new_prefix)
            elif isinstance(data, list):
                for i, item in enumerate(data):
                    new_prefix = f"{prefix} [{i+1}]"
                    recursive_extract(item, new_prefix)
            elif data and str(data).lower() not in ["null", "none", "—", "n/a", "not available", "not provided", "none"]:
                # Leaf node: search for coordinates
                field_label = prefix
                
                # If the value is a placeholder, try to search for the original text
                search_values = [str(data)]
                if str(data) in placeholder_to_originals:
                    search_values.extend(list(placeholder_to_originals[str(data)]))
                
                instances = []
                # Remove duplicates and empty strings
                search_values = list(set([v for v in search_values if v and v.strip()]))
                
                logger.info(f"[Extraction] Searching for field '{field_label}' with values: {search_values}")
                
                for val in search_values:
                    for doc_id, layout in doc_layout_results.items():
                        matches = extraction_svc.find_field_in_lines(layout, val)
                        for m in matches:
                            m["doc_id"] = doc_id
                            instances.append(m)
                
                if instances:
                    # Sort globally by similarity and confidence before picking top
                    instances.sort(key=lambda x: (x.get("similarity", 0), x.get("confidence", 0)), reverse=True)
                    
                    # Enforce "Winner Takes All" for single fields to avoid noise
                    if "[" not in field_label:
                        # Take only the absolute best match found across all documents
                        instances = [instances[0]]
                    
                    logger.info(f"[Extraction] Found {len(instances)} matches for '{field_label}'")
                    extraction_results.append({
                        "field": field_label,
                        "value": str(data),
                        "instances": instances
                    })
                else:
                    logger.warning(f"[Extraction] No matches found for '{field_label}' in any document.")

        logger.info(f"[Extraction] Starting recursive extraction on {len(doc_layout_results)} document layouts.")
        recursive_extract(classification.get("key_fields", {}))
        
        classification["extraction_results"] = extraction_results
        classification["extracted_tables"] = doc_tables
        logger.info(f"[Extraction] Final extraction results count: {len(extraction_results)}")
        await db_service.save_classification_result(classification)

        # 7. Final Status Update
        if not safety_flagged_for_review:
            await db_service.update_case_status(
                case_id, CaseStatus.PROCESSED,
                classification_category=classification["classification_category"],
                confidence_score=classification["confidence_score"],
                requires_human_review=classification["requires_human_review"],
            )
        else:
            await db_service.update_case_status(
                case_id, CaseStatus.NEEDS_REVIEW_SAFETY,
                classification_category=classification["classification_category"],
                confidence_score=classification["confidence_score"],
                requires_human_review=True,
            )
            
        return {"message": f"Successfully processed case {case_id}"}
        
    except Exception as e:
        logger.error(f"[Process] Failed processing case {case_id}: {e}", exc_info=True)
        await db_service.update_case_status(case_id, CaseStatus.FAILED)
        raise HTTPException(status_code=500, detail=str(e))
