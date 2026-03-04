import logging
import json
import base64
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel

from config import settings
from services.blob_storage import BlobStorageService
from services.classifier import Classifier
from utils.pii_report import generate_case_pii_report

logger = logging.getLogger(__name__)
router = APIRouter()

def _get_db():
    if settings.demo_mode:
        from services.local_db import LocalDBService
        return LocalDBService()
    else:
        from services.cosmos_db import CosmosDBService
        return CosmosDBService()

class SyncResult(BaseModel):
    new_cases_processed: int
    failed: int
    message: str

@router.post("/cases/sync", response_model=SyncResult)
async def sync_emails_from_blob():
    """
    Scans Blob Storage for new `email.json` files that haven't been processed
    (missing `is_processed=true` tag), downloads them, parses their details,
    downloads attachments, and runs them through the main ingestion pipeline and AI.
    """
    logger.info("Starting Blob Storage Email Sync...")
    
    blob_service = BlobStorageService()
    db_service = _get_db()
    classifier = Classifier()
    
    # Needs to be true pipeline since we're writing to cosmos. But pipeline expects a Graph API format.
    # The external script json is very similar but we need to structure it into the DB correctly.
    # To keep it atomic, we'll instantiate our own services.
    from services.document_parser import DocumentParser
    from services.pii_masker import PIIMasker
    import uuid
    from datetime import datetime
    
    parser = DocumentParser()
    masker = PIIMasker()
    
    try:
        container = settings.blob_container_raw_emails
        unprocessed_folders = await blob_service.list_unprocessed_email_folders(container)
        
        if not unprocessed_folders:
            return SyncResult(new_cases_processed=0, failed=0, message="No new emails found.")
            
        logger.info(f"Found {len(unprocessed_folders)} unprocessed email folders.")
        success_count = 0
        failure_count = 0
        
        for folder in unprocessed_folders:
            logger.info(f"Processing folder: {folder}")
            # The case_id will be matched or generated inside CaseManager
            case_id = None 
            try:
                # 1. Download email.json
                email_json_path = f"{folder}/email.json"
                email_text = await blob_service.download_text(container, email_json_path)
                email_data = json.loads(email_text)
                
                # 2. Resolve Case via Thread Detection
                from services.case_manager import CaseManager
                case_mgr = CaseManager(db_service)
                case_id = await case_mgr.resolve_case(email_data)
                logger.info(f"Assigned/Resolved Case ID: {case_id}")
                
                # 3. Create Email Record (Case is already created/updated by resolve_case)
                from models.case import CaseStatus
                
                email_record = {
                    "email_id": str(uuid.uuid4()),
                    "case_id": case_id,
                    "message_id": email_data.get("messageId") or email_data.get("internetMessageId") or "unknown",
                    "sender": email_data.get("from", "unknown"),
                    "recipient": ", ".join(email_data.get("to", [])),
                    "subject": email_data.get("subject", "No Subject"),
                    "body_masked": "", # Set later
                    "received_at": email_data.get("receivedDateTime", datetime.utcnow().isoformat()),
                    "has_attachments": email_data.get("hasAttachments", False)
                }
                await db_service.create_email(email_record)

                # 4. Find Attachments inside the same folder
                blobs_in_folder = await blob_service.list_blobs_in_folder(container, folder)
                attachment_paths = [b for b in blobs_in_folder if b != email_json_path and not "/unzipped/" in b]
                
                combined_text = email_data.get("body", "") + " \n\n "
                
                for att_path in attachment_paths:
                    att_bytes = await blob_service.download_bytes(container, att_path)
                    att_filename = att_path.split("/")[-1]
                    
                    # Parse document
                    parse_result = await parser.parse(att_filename, att_bytes)
                    text_content = parse_result.raw_text
                    combined_text += f"\n\n--- Attachment: {att_filename} ---\n{text_content}"
                    
                    # Save document record
                    doc_record = {
                        "document_id": str(uuid.uuid4()),
                        "case_id": case_id,
                        "filename": att_filename,
                        "blob_path": att_path,
                        "extracted_text": text_content,
                        "processing_status": "DONE"
                    }
                    await db_service.create_document(doc_record)

                # 5. PII Masking
                masked_text, pii_mappings = await masker.mask_text(
                    text=combined_text,
                    case_id=case_id,
                    document_id=case_id 
                )
                
                # Decrypt original values for the HTML Report
                for m in pii_mappings:
                    try:
                        m["original_value"] = masker._decrypt(m["original_value_encrypted"])
                    except Exception:
                        pass
                        
                # Generate HTML Report for this specific case
                report_url = generate_case_pii_report(case_id, combined_text, masked_text, pii_mappings)
                logger.info(f"Generated Case PII Report at {report_url}")
                
                # Update email with masked body
                email_dump = email_record.copy()
                email_dump["body_masked"] = masked_text[:2000] # store preview
                
                if settings.demo_mode:
                    # TinyDB doesn't use identical upsert logic, recreate/update manually or use built-in
                    from tinydb import Query
                    from services.local_db import _get_db as get_tinydb
                    db = get_tinydb()
                    E = Query()
                    db.table("emails").upsert(email_dump, E.email_id == email_dump["email_id"])
                    db.storage.flush()
                else:
                    container_client = await db_service._get_container("emails")
                    await container_client.upsert_item(email_dump)

                # 6. AI Classification
                classification = await classifier.classify(masked_text)
                
                # Update case with results
                classification["result_id"] = str(uuid.uuid4())
                classification["case_id"] = case_id
                classification["classified_at"] = datetime.utcnow().isoformat()
                
                await db_service.save_classification_result(classification)
                
                await db_service.update_case_status(
                    case_id,
                    CaseStatus.NOTIFIED,
                    classification_category=classification["classification_category"],
                    confidence_score=classification["confidence_score"],
                    requires_human_review=classification["requires_human_review"]
                )
                
                # 7. Success! Tag the blob
                await blob_service.mark_as_processed(container, email_json_path)
                logger.info(f"Successfully processed {folder}")
                success_count += 1
                
            except Exception as e:
                logger.error(f"Failed processing folder {folder}: {e}", exc_info=True)
                if case_id:
                    await db_service.delete_case_data(case_id)
                failure_count += 1

        return SyncResult(
            new_cases_processed=success_count,
            failed=failure_count,
            message=f"Synced {success_count} emails successfully. {failure_count} failed."
        )

    except Exception as e:
        logger.error(f"Error during Blob Email Sync: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        await blob_service.close()
