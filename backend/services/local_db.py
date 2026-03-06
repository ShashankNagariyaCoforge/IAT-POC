"""
Demo Mode: Local TinyDB service.
Drop-in replacement for CosmosDBService — same async interface, backed by
a local JSON file at demo_data/db.json.

IMPORTANT: This file is ONLY used when DEMO_MODE=true in .env.
           Do NOT use in production.
"""

import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from tinydb import TinyDB, Query
from tinydb.storages import JSONStorage
from tinydb.middlewares import CachingMiddleware

from models.case import CaseStatus

logger = logging.getLogger(__name__)

# Path to the local JSON database file
_HERE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(_HERE, "..", "demo_data", "db.json")


def _get_db() -> TinyDB:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    return TinyDB(DB_PATH, storage=CachingMiddleware(JSONStorage))


class LocalDBService:
    """
    Local TinyDB-backed service that mirrors CosmosDBService's interface.
    All methods are async to maintain compatibility with the existing API layer.
    """

    # ===== CASES =====

    async def create_case(self, case) -> Any:
        """Create a new case (accepts CaseDocument or dict)."""
        db = _get_db()
        if hasattr(case, "model_dump"):
            item = case.model_dump(mode="json")
        else:
            item = dict(case)
        # Convert datetime objects to ISO strings
        for k, v in item.items():
            if isinstance(v, datetime):
                item[k] = v.isoformat()
        db.table("cases").insert(item)
        db.storage.flush()
        logger.info(f"[LocalDB] Created case: {item['case_id']}")
        return case

    async def get_case(self, case_id: str) -> Optional[Dict]:
        db = _get_db()
        Case = Query()
        results = db.table("cases").search(Case.case_id == case_id)
        return results[0] if results else None

    async def update_case_status(
        self,
        case_id: str,
        status: CaseStatus,
        **extra_fields,
    ) -> None:
        db = _get_db()
        Case = Query()
        updates = {
            "status": status.value,
            "updated_at": datetime.utcnow().isoformat(),
        }
        updates.update(extra_fields)
        db.table("cases").update(updates, Case.case_id == case_id)
        db.storage.flush()
        logger.info(f"[LocalDB] Updated case {case_id} → {status.value}")

    async def delete_case_data(self, case_id: str) -> None:
        """
        Rollback helper: Delete the case and ALL associated records.
        """
        logger.warning(f"[LocalDB] Rolling back records for failed case: {case_id}")
        db = _get_db()
        q = Query()
        db.table("emails").remove(q.case_id == case_id)
        db.table("documents").remove(q.case_id == case_id)
        db.table("classification_results").remove(q.case_id == case_id)
        db.table("cases").remove(q.case_id == case_id)
        db.storage.flush()
        logger.info(f"[LocalDB] Successfully rolled back data for {case_id}")

    async def update_case_safety(self, case_id: str, safety_result: dict) -> None:
        """Update case with content safety scores."""
        db = _get_db()
        Case = Query()
        db.table("cases").update(
            {"content_safety_result": safety_result, "updated_at": datetime.utcnow().isoformat()},
            Case.case_id == case_id
        )
        db.storage.flush()
        logger.info(f"[LocalDB] Saved content safety result for case {case_id}")

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
        db = _get_db()
        items = db.table("cases").all()

        # Filtering
        if search:
            s = search.lower()
            items = [
                c for c in items
                if s in (c.get("case_id") or "").lower()
                or s in (c.get("sender") or "").lower()
                or s in (c.get("subject") or "").lower()
            ]
        if category:
            items = [c for c in items if c.get("classification_category") == category]
        if status:
            items = [c for c in items if c.get("status") == status]
        if requires_human_review is not None:
            items = [c for c in items if c.get("requires_human_review") == requires_human_review]
        if date_from:
            items = [c for c in items if (c.get("created_at") or "") >= date_from]
        if date_to:
            items = [c for c in items if (c.get("created_at") or "") <= date_to]

        # Sorting
        allowed_sort = {"case_id", "created_at", "updated_at", "sender", "status", "confidence_score"}
        if sort_by not in allowed_sort:
            sort_by = "created_at"
        reverse = sort_order.upper() == "DESC"
        items.sort(key=lambda c: (c.get(sort_by) or ""), reverse=reverse)

        total = len(items)
        offset = (page - 1) * page_size
        page_items = items[offset: offset + page_size]

        return {
            "cases": page_items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": max(1, -(-total // page_size)),
        }

    async def get_next_case_sequence(self) -> int:
        db = _get_db()
        return len(db.table("cases").all()) + 1

    # ===== EMAILS =====

    async def create_email(self, email_doc: Dict) -> None:
        db = _get_db()
        db.table("emails").insert(dict(email_doc))
        db.storage.flush()
        logger.info(f"[LocalDB] Saved email {email_doc.get('email_id')}")

    async def get_emails_for_case(self, case_id: str) -> List[Dict]:
        db = _get_db()
        E = Query()
        items = db.table("emails").search(E.case_id == case_id)
        return sorted(items, key=lambda x: x.get("received_at") or "")

    async def find_email_by_message_id(self, message_id: str) -> Optional[Dict]:
        db = _get_db()
        E = Query()
        results = db.table("emails").search(E.message_id == message_id)
        return results[0] if results else None

    async def find_case_by_subject(self, clean_subject: str) -> Optional[str]:
        db = _get_db()
        C = Query()
        results = db.table("cases").search(C.subject == clean_subject)
        if results:
            results.sort(key=lambda c: c.get("created_at") or "", reverse=True)
            return results[0]["case_id"]
        return None

    # ===== DOCUMENTS =====

    async def create_document(self, doc: Dict) -> None:
        db = _get_db()
        db.table("documents").insert(dict(doc))
        db.storage.flush()

    async def get_documents_for_case(self, case_id: str) -> List[Dict]:
        db = _get_db()
        D = Query()
        return db.table("documents").search(D.case_id == case_id)

    async def update_document(self, doc: Dict) -> None:
        db = _get_db()
        D = Query()
        db.table("documents").upsert(dict(doc), D.document_id == doc["document_id"])
        db.storage.flush()

    # ===== CLASSIFICATION RESULTS =====

    async def save_classification_result(self, result: Dict) -> None:
        db = _get_db()
        db.table("classification_results").insert(dict(result))
        db.storage.flush()
        logger.info(f"[LocalDB] Saved classification for case {result.get('case_id')}")

    async def get_classification_for_case(self, case_id: str) -> Optional[Dict]:
        db = _get_db()
        R = Query()
        results = db.table("classification_results").search(R.case_id == case_id)
        if not results:
            return None
        return sorted(results, key=lambda r: r.get("classified_at") or "", reverse=True)[0]

    async def update_classification_notification(self, result_id: str, sent_at: datetime) -> None:
        db = _get_db()
        R = Query()
        db.table("classification_results").update(
            {
                "downstream_notification_sent": True,
                "downstream_notification_at": sent_at.isoformat(),
            },
            R.result_id == result_id,
        )
        db.storage.flush()

    # ===== PII MAPPING (no-op for demo) =====

    async def save_pii_mapping(self, mapping: Dict) -> None:
        # No-op in demo mode — PII mappings not persisted locally
        pass

    # ===== STATS =====

    async def get_stats(self) -> Dict:
        db = _get_db()
        cases = db.table("cases").all()
        total = len(cases)

        by_status: Dict[str, int] = {}
        by_category: Dict[str, int] = {}
        review_count = 0

        for c in cases:
            s = c.get("status", "UNKNOWN")
            by_status[s] = by_status.get(s, 0) + 1
            cat = c.get("classification_category")
            if cat:
                by_category[cat] = by_category.get(cat, 0) + 1
            if c.get("requires_human_review"):
                review_count += 1

        return {
            "total_cases": total,
            "by_status": by_status,
            "by_category": by_category,
            "pending_human_review": review_count,
        }

    # ===== TIMELINE =====

    async def get_timeline_for_case(self, case_id: str) -> List[Dict]:
        events = []

        emails = await self.get_emails_for_case(case_id)
        for email in emails:
            events.append({
                "timestamp": email.get("received_at"),
                "event": "Email received",
                "details": f"From: {email.get('sender')} | Subject: {email.get('subject')}",
            })

        classification = await self.get_classification_for_case(case_id)
        if classification:
            events.append({
                "timestamp": classification.get("classified_at"),
                "event": "Email classified",
                "details": (
                    f"Category: {classification.get('classification_category')} "
                    f"| Confidence: {classification.get('confidence_score')}"
                ),
            })
            if classification.get("downstream_notification_sent"):
                events.append({
                    "timestamp": classification.get("downstream_notification_at"),
                    "event": "Downstream notification sent",
                    "details": "Notification delivered.",
                })

        events.sort(key=lambda e: e.get("timestamp") or "")
        return events

    # ===== INITIALISE (no-op for local) =====

    async def initialize_containers(self) -> None:
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        logger.info(f"[LocalDB] TinyDB ready at {DB_PATH}")
