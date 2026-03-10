import logging
import uuid
from datetime import datetime
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from config import settings
from services.classifier import Classifier
from services.content_safety import ContentSafetyService
from services.pii_masker import PIIMasker
from services.blob_storage import BlobStorageService
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

        # 1. Fetch all content for merging
        emails = await db_service.get_emails_for_case(case_id)
        documents = await db_service.get_documents_for_case(case_id)
        
        if not emails and not documents:
            await db_service.update_case_status(case_id, CaseStatus.FAILED)
            raise HTTPException(status_code=400, detail="No content found for this case to process.")

        # 2. Build combined text (Raw)
        text_parts = []
        for em in emails:
             text_parts.append(f"[Source: Email from {em.get('sender')}]\n{em.get('body_masked', '')}")
        
        for doc in documents:
            if doc.get("extracted_text"):
                text_parts.append(f"[Source: Attachment {doc.get('filename')}]\n{doc.get('extracted_text')}")
        
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

        # Upload HTML report as a blob
        report_blob_name = f"cases/{case_id}/pii_masking_report.html"
        await blob_service.upload_text(
            settings.blob_container_extracted_text,
            report_blob_name,
            html_report,
            content_type="text/html"
        )

        masked_blob_name = f"cases/{case_id}/masked_full_content.txt"
        await blob_service.upload_text(
            settings.blob_container_extracted_text,
            masked_blob_name,
            masked_text
        )

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
        classification["masked_text_blob_path"] = masked_blob_name
        classification["pii_report_blob_path"] = report_blob_name
        
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
