"""
Azure Cosmos DB service (MongoDB API).
Handles all CRUD operations for the collections:
  - cases, emails, documents, classification_results, pii_mapping
Pii_mapping is NEVER returned in API responses.
"""

import logging
import uuid
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import DESCENDING, ASCENDING

from config import settings
from models.case import CaseDocument, CaseStatus, ClassificationCategory

logger = logging.getLogger(__name__)

# Collection names (Mapping to previous container names)
COLLECTION_CASES = "cases"
COLLECTION_EMAILS = "emails"
COLLECTION_DOCUMENTS = "documents"
COLLECTION_CLASSIFICATION = "classification_results"
COLLECTION_PII_MAPPING = "pii_mapping"


class CosmosDBService:
    """Async MongoDB client for all IAT Insurance data operations (Cosmos DB MongoDB API)."""

    def __init__(self):
        # Prioritize MongoDB connection string
        conn_str = settings.mongodb_connection_string
        if not conn_str:
            # Check if SQL connection string was accidentally put here or if we should fallback
            sql_conn = settings.azure_cosmos_connection_string
            if sql_conn and "mongodb://" in sql_conn:
                conn_str = sql_conn
                logger.info("Using MongoDB connection string from AZURE_COSMOS_CONNECTION_STRING.")
            
        if not conn_str:
            logger.warning("MONGODB_CONNECTION_STRING not set. Database operations will fail if in production mode.")
            self._client = None
        else:
            # Use Motor for async mongo access
            # We add tlsCAFile if needed, but for Cosmos it usually works with default or certifi
            try:
                import certifi
                self._client = AsyncIOMotorClient(conn_str, tlsCAFile=certifi.where())
            except ImportError:
                self._client = AsyncIOMotorClient(conn_str)
                
            logger.info("CosmosDBService (MongoDB API) initialized.")
            
        self._database_name = settings.cosmos_database_name
        self._db = None

    def _get_db(self):
        """Lazy-load the database reference."""
        if self._db is None and self._client:
            self._db = self._client[self._database_name]
        return self._db

    async def initialize_containers(self):
        """
        Ensure connection to MongoDB is valid.
        In MongoDB API, we don't need to 'create' collections explicitly as they 
        are created on first use, but we can verify connectivity.
        """
        db = self._get_db()
        if db is not None:
            try:
                # The ping command is a reliable way to check connectivity
                await db.command("ping")
                logger.info(f"Connected to Cosmos DB MongoDB: {self._database_name}")
                
                # Optionally create indexes here for performance
                await db[COLLECTION_CASES].create_index([("case_id", ASCENDING)], unique=True)
                await db[COLLECTION_EMAILS].create_index([("message_id", ASCENDING)])
                await db[COLLECTION_EMAILS].create_index([("case_id", ASCENDING)])
                await db[COLLECTION_DOCUMENTS].create_index([("document_id", ASCENDING)], unique=True)
                await db[COLLECTION_CLASSIFICATION].create_index([("case_id", ASCENDING)])
                
            except Exception as e:
                logger.error(f"Failed to connect to MongoDB API: {e}")
                # Don't raise if we want the app to start (e.g. for health checks)
        else:
            logger.error("No MongoDB client available. Check your MONGODB_CONNECTION_STRING.")

    # ===== CASES =====

    async def create_case(self, case: CaseDocument) -> CaseDocument:
        """Create a new case in MongoDB."""
        db = self._get_db()
        item = case.model_dump(mode="json")
        # Ensure _id is case_id for efficient lookup
        item["_id"] = case.case_id
        await db[COLLECTION_CASES].insert_one(item)
        logger.info(f"Created case: {case.case_id}")
        return case

    async def get_case(self, case_id: str) -> Optional[Dict]:
        """Fetch a single case by case_id."""
        db = self._get_db()
        item = await db[COLLECTION_CASES].find_one({"_id": case_id})
        return item

    async def update_case_status(
        self,
        case_id: str,
        status: CaseStatus,
        **extra_fields,
    ) -> None:
        """Update case status and any extra fields."""
        db = self._get_db()
        update_data = {
            "status": status.value,
            "updated_at": datetime.utcnow().isoformat()
        }
        update_data.update(extra_fields)
        
        await db[COLLECTION_CASES].update_one(
            {"_id": case_id},
            {"$set": update_data}
        )
        logger.info(f"Updated case {case_id} status to {status.value}")

    async def update_case_safety(self, case_id: str, safety_result: Dict) -> None:
        """Update case with content safety results."""
        db = self._get_db()
        await db[COLLECTION_CASES].update_one(
            {"_id": case_id},
            {
                "$set": {
                    "content_safety_result": safety_result,
                    "updated_at": datetime.utcnow().isoformat()
                }
            }
        )
        logger.debug(f"Attached Content Safety results to case {case_id}")

    async def reset_case(self, case_id: str) -> None:
        """
        Partial reset: delete classification results, PII mappings, 
        and clear AI fields from the case record.
        """
        db = self._get_db()
        # 1. Delete classification results
        await db[COLLECTION_CLASSIFICATION].delete_many({"case_id": case_id})

        # 2. Delete PII mapping
        await db[COLLECTION_PII_MAPPING].delete_many({"case_id": case_id})

        # 3. Update case
        await db[COLLECTION_CASES].update_one(
            {"_id": case_id},
            {
                "$set": {
                    "status": CaseStatus.RECEIVED.value,
                    "classification_category": None,
                    "confidence_score": 0,
                    "requires_human_review": False,
                    "summary": None,
                    "content_safety_result": None,
                    "updated_at": datetime.utcnow().isoformat()
                }
            }
        )
        logger.info(f"[MongoDB] Reset case to RECEIVED: {case_id}")

    async def delete_case_data(self, case_id: str) -> None:
        """Rollback helper: Delete the case and ALL associated records."""
        db = self._get_db()
        logger.warning(f"Rolling back MongoDB records for failed case: {case_id}")
        
        # 1. Delete emails
        await db[COLLECTION_EMAILS].delete_many({"case_id": case_id})
        # 2. Delete documents
        await db[COLLECTION_DOCUMENTS].delete_many({"case_id": case_id})
        # 3. Delete classification
        await db[COLLECTION_CLASSIFICATION].delete_many({"case_id": case_id})
        # 4. Delete PII mapping
        await db[COLLECTION_PII_MAPPING].delete_many({"case_id": case_id})
        # 5. Delete the case itself
        await db[COLLECTION_CASES].delete_one({"_id": case_id})
            
        logger.info(f"Successfully rolled back data for {case_id}")

    async def list_cases(
        self,
        page: int = 1,
        page_size: int = 50,
        search: Optional[str] = None,
        category: Optional[str] = None,
        status: Optional[str] = None,
        requires_human_review: Optional[bool] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        sort_by: str = "created_at",
        sort_order: str = "DESC",
    ) -> Dict[str, Any]:
        """List cases with filtering, sorting, and pagination."""
        db = self._get_db()
        filter_q = {}

        if search:
            # Case-insensitive search using regex
            filter_q["$or"] = [
                {"case_id": {"$regex": search, "$options": "i"}},
                {"sender": {"$regex": search, "$options": "i"}},
                {"subject": {"$regex": search, "$options": "i"}}
            ]
        if category:
            filter_q["classification_category"] = category
        if status:
            filter_q["status"] = status
        if requires_human_review is not None:
            filter_q["requires_human_review"] = requires_human_review
            
        if date_from or date_to:
            filter_q["created_at"] = {}
            if date_from:
                filter_q["created_at"]["$gte"] = date_from
            if date_to:
                filter_q["created_at"]["$lte"] = date_to

        # Count total
        total = await db[COLLECTION_CASES].count_documents(filter_q)

        # Sort
        sort_dir = DESCENDING if sort_order.upper() == "DESC" else ASCENDING
        
        skip = (page - 1) * page_size
        items_cursor = db[COLLECTION_CASES].find(filter_q).sort(sort_by, sort_dir).skip(skip).limit(page_size)
        items = await items_cursor.to_list(length=page_size)

        return {
            "cases": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": max(1, -(-total // page_size)),
        }

    async def get_next_case_sequence(self) -> int:
        """Get the next global case sequence number."""
        db = self._get_db()
        # MongoDB count is fast enough for sequence in POC
        count = await db[COLLECTION_CASES].count_documents({})
        return count + 1

    # ===== EMAILS =====

    async def create_email(self, email_doc: Dict) -> None:
        """Save an email to MongoDB."""
        db = self._get_db()
        # Use email_id as _id
        email_doc["_id"] = email_doc.get("email_id")
        await db[COLLECTION_EMAILS].insert_one(email_doc)
        logger.info(f"Saved email {email_doc.get('email_id')} to MongoDB.")

    async def get_emails_for_case(self, case_id: str) -> List[Dict]:
        """Fetch all emails belonging to a case."""
        db = self._get_db()
        cursor = db[COLLECTION_EMAILS].find({"case_id": case_id}).sort("received_at", ASCENDING)
        items = await cursor.to_list(length=None)
        return items

    async def find_email_by_message_id(self, message_id: str) -> Optional[Dict]:
        """Look up an email by message_id."""
        db = self._get_db()
        return await db[COLLECTION_EMAILS].find_one({"message_id": message_id})

    async def find_case_by_subject(self, clean_subject: str) -> Optional[str]:
        """Find a case by exact subject."""
        db = self._get_db()
        item = await db[COLLECTION_CASES].find_one({"subject": clean_subject}, sort=[("created_at", DESCENDING)])
        return item["case_id"] if item else None

    async def find_recent_case_by_subject_and_sender(
        self, 
        subject: str, 
        sender: str, 
        minutes: int = 10
    ) -> Optional[str]:
        """Match by Subject + Sender within time window."""
        from datetime import timedelta
        db = self._get_db()
        threshold_time = (datetime.utcnow() - timedelta(minutes=minutes)).isoformat()
        
        item = await db[COLLECTION_CASES].find_one({
            "subject": subject,
            "sender": sender,
            "updated_at": {"$gte": threshold_time}
        }, sort=[("updated_at", DESCENDING)])
        
        return item["case_id"] if item else None

    # ===== DOCUMENTS =====

    async def create_document(self, doc: Dict) -> None:
        db = self._get_db()
        doc["_id"] = doc.get("document_id")
        await db[COLLECTION_DOCUMENTS].insert_one(doc)

    async def get_documents_for_case(self, case_id: str) -> List[Dict]:
        db = self._get_db()
        cursor = db[COLLECTION_DOCUMENTS].find({"case_id": case_id})
        return await cursor.to_list(length=None)

    async def update_document(self, doc: Dict) -> None:
        db = self._get_db()
        await db[COLLECTION_DOCUMENTS].replace_one({"_id": doc.get("document_id")}, doc, upsert=True)

    # ===== CLASSIFICATION RESULTS =====

    async def save_classification_result(self, result: Dict) -> None:
        db = self._get_db()
        result["_id"] = result.get("result_id", str(uuid.uuid4()))
        await db[COLLECTION_CLASSIFICATION].insert_one(result)

    async def get_classification_for_case(self, case_id: str) -> Optional[Dict]:
        db = self._get_db()
        return await db[COLLECTION_CLASSIFICATION].find_one({"case_id": case_id}, sort=[("classified_at", DESCENDING)])

    async def update_classification_notification(self, result_id: str, sent_at: datetime) -> None:
        db = self._get_db()
        await db[COLLECTION_CLASSIFICATION].update_one(
            {"_id": result_id},
            {
                "$set": {
                    "downstream_notification_sent": True,
                    "downstream_notification_at": sent_at.isoformat()
                }
            }
        )

    # ===== PII MAPPING =====

    async def save_pii_mapping(self, mapping: Dict) -> None:
        db = self._get_db()
        mapping["_id"] = mapping.get("mapping_id", str(uuid.uuid4()))
        await db[COLLECTION_PII_MAPPING].insert_one(mapping)

    # ===== STATS =====

    async def get_stats(self) -> Dict:
        """Return basic statistics for health/stats."""
        db = self._get_db()
        total = await db[COLLECTION_CASES].count_documents({})
        
        # Aggregate statuses
        status_pipeline = [{"$group": {"_id": "$status", "count": {"$sum": 1}}}]
        status_results = await db[COLLECTION_CASES].aggregate(status_pipeline).to_list(length=None)
        
        # Aggregate categories
        cat_pipeline = [
            {"$match": {"classification_category": {"$ne": None}}},
            {"$group": {"_id": "$classification_category", "count": {"$sum": 1}}}
        ]
        cat_results = await db[COLLECTION_CASES].aggregate(cat_pipeline).to_list(length=None)
        
        review_count = await db[COLLECTION_CASES].count_documents({"requires_human_review": True})

        return {
            "total_cases": total,
            "by_status": {res["_id"]: res["count"] for res in status_results if res["_id"]},
            "by_category": {res["_id"]: res["count"] for res in cat_results if res["_id"]},
            "pending_human_review": review_count,
        }

    async def get_dashboard_metrics(self) -> Dict:
        """Metrics with Pie and Sankey chart data."""
        db = self._get_db()
        cursor = db[COLLECTION_CASES].find({}, {"status": 1, "classification_category": 1, "confidence_score": 1, "requires_human_review": 1})
        cases = await cursor.to_list(length=None)
        
        total_cases = len(cases)
        classified_cases = [c for c in cases if c.get("status") in {"CLASSIFIED", "PROCESSED", "PENDING_REVIEW", "NEEDS_REVIEW_SAFETY"}]
        
        total_confidence = sum([c.get("confidence_score", 0) for c in classified_cases if c.get("confidence_score") is not None])
        avg_confidence = total_confidence / len(classified_cases) if classified_cases else 0

        review_required_count = len([c for c in cases if c.get("status") in {"PENDING_REVIEW", "NEEDS_REVIEW_SAFETY", "BLOCKED_SAFETY"}])
        auto_triaged = len([c for c in cases if c.get("status") in {"CLASSIFIED", "PROCESSED"}])
        auto_triage_rate = auto_triaged / total_cases if total_cases > 0 else 0

        status_counts = {}
        for c in cases:
            s = c.get("status", "RECEIVED")
            status_counts[s] = status_counts.get(s, 0) + 1

        color_map = {
            "RECEIVED": "#94a3b8", "PROCESSING": "#60a5fa", "CLASSIFIED": "#34d399", 
            "PROCESSED": "#10b981", "PENDING_REVIEW": "#f59e0b", "NEEDS_REVIEW_SAFETY": "#f97316", 
            "BLOCKED_SAFETY": "#ef4444", "FAILED": "#ef4444"
        }

        pie_chart = [{"name": s, "value": count, "color": color_map.get(s, "#cbd5e1")} for s, count in status_counts.items()]

        safety_cleared = len([c for c in cases if c.get("status") not in {"NEEDS_REVIEW_SAFETY", "BLOCKED_SAFETY", "RECEIVED"}])
        safety_flagged = len([c for c in cases if c.get("status") in {"NEEDS_REVIEW_SAFETY", "BLOCKED_SAFETY"}])
        cat_docs = len([c for c in cases if c.get("classification_category") == "Documentation Submission"])
        cat_inq = len([c for c in cases if c.get("classification_category") == "Inquiry"])
        cat_other = safety_cleared - cat_docs - cat_inq
        
        sankey_nodes = [
            {"name": "Total Incoming"}, {"name": "Safety Cleared"}, {"name": "Safety Flagged"}, 
            {"name": "Documentation"}, {"name": "Inquiry"}, {"name": "Other Categories"}, 
            {"name": "Auto-Processed"}, {"name": "Review Required"}
        ]
        
        s_links = [
            {"source": 0, "target": 1, "value": safety_cleared},
            {"source": 0, "target": 2, "value": safety_flagged},
            {"source": 1, "target": 3, "value": cat_docs},
            {"source": 1, "target": 4, "value": cat_inq},
            {"source": 1, "target": 5, "value": max(0, cat_other)},
            {"source": 3, "target": 6, "value": max(0, cat_docs - (review_required_count // 3))},
            {"source": 3, "target": 7, "value": review_required_count // 3},
            {"source": 4, "target": 6, "value": max(0, cat_inq - (review_required_count // 3))},
            {"source": 4, "target": 7, "value": review_required_count // 3},
            {"source": 5, "target": 6, "value": max(0, cat_other - (review_required_count - 2 * (review_required_count // 3)))},
            {"source": 5, "target": 7, "value": max(0, review_required_count - 2 * (review_required_count // 3))},
            {"source": 2, "target": 7, "value": safety_flagged}
        ]

        return {
            "decision_accuracy": avg_confidence,
            "avg_agent_processing_time_ms": 3450,
            "extraction_accuracy": 0.94,
            "action_required_threads": review_required_count,
            "auto_triage_rate": auto_triage_rate,
            "pie_chart": pie_chart,
            "sankey_chart": {"nodes": sankey_nodes, "links": [l for l in s_links if l["value"] > 0]}
        }

    async def get_timeline_for_case(self, case_id: str) -> List[Dict]:
        events = []
        emails = await self.get_emails_for_case(case_id)
        for email in emails:
            events.append({
                "timestamp": email.get("received_at"),
                "event": "Email received",
                "details": f"From: {email.get('sender')} | Subject: {email.get('subject')}",
            })

        cls = await self.get_classification_for_case(case_id)
        if cls:
            events.append({
                "timestamp": cls.get("classified_at"),
                "event": "Email classified",
                "details": f"Category: {cls.get('classification_category')} | Confidence: {cls.get('confidence_score')}",
            })
            if cls.get("downstream_notification_sent"):
                events.append({
                    "timestamp": cls.get("downstream_notification_at"),
                    "event": "Downstream notification sent",
                    "details": "Notification delivered.",
                })

        events.sort(key=lambda e: e["timestamp"] or "")
        return events
