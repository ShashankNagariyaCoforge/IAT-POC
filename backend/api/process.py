import logging
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
            
            # Fetch bytes from blob
            if blob_path:
                try:
                    container = settings.blob_container_attachments
                    # Split container from path if it's there
                    path_parts = blob_path.split("/")
                    actual_blob_name = "/".join(path_parts[1:]) if path_parts[0] == container else blob_path
                    
                    doc_bytes = await blob_service.download_bytes(container, actual_blob_name)
                    
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
            elif doc.get("extracted_text"):
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

        # 6.5 Match Key Fields to Locations (Extraction Results)
        extraction_results = []
        key_fields_dict = classification.get("key_fields", {})
        
        for field_key, field_value in key_fields_dict.items():
            if not field_value: continue
            
            instances = []
            for doc_id, layout in doc_layout_results.items():
                matches = extraction_svc.find_field_in_lines(layout, str(field_value))
                for m in matches:
                    m["doc_id"] = doc_id
                    instances.append(m)
            
            if instances:
                extraction_results.append({
                    "field": field_key.replace("_", " ").title(),
                    "instances": instances
                })
        
        classification["extraction_results"] = extraction_results
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
