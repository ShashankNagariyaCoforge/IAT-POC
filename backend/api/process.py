import logging
import uuid
from datetime import datetime
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from config import settings
from services.classifier import Classifier
from services.content_safety import ContentSafetyService
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
        
        # In a real system, you would grab the masked_text from the Blob or DB where the poller saved it.
        # For simplicity of this manual trigger, we pull the emails and concat their masked bodies.
        emails = await db_service.get_emails_for_case(case_id)
        if not emails:
            await db_service.update_case_status(case_id, CaseStatus.FAILED)
            raise HTTPException(status_code=400, detail="No emails found for this case to process.")
            
        masked_text = ""
        for em in emails:
             masked_text += em.get("body_masked", "") + "\n\n"
             
        # Content Safety
        safety_result = await safety_svc.analyze_text(masked_text)
        safety_flagged_for_review = False
        
        if safety_result:
            await db_service.update_case_safety(case_id, safety_result.model_dump())
            max_severity = max(
                safety_result.hate_severity,
                safety_result.self_harm_severity,
                safety_result.sexual_severity,
                safety_result.violence_severity,
            )
            if max_severity >= 4:
                await db_service.update_case_status(case_id, CaseStatus.BLOCKED_SAFETY)
                return {"message": "Case blocked by safety guardrails."}
            elif max_severity >= 2:
                safety_flagged_for_review = True

        # AI Classification
        classification = await classifier.classify(masked_text)
        classification["result_id"] = str(uuid.uuid4())
        classification["case_id"] = case_id
        classification["classified_at"] = datetime.utcnow().isoformat()
        await db_service.save_classification_result(classification)

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
