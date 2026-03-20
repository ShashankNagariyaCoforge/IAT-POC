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

    async def reset_case(self, case_id: str) -> None:
        """Partial reset: clear classification and safety, set to RECEIVED."""
        db = _get_db()
        q = Query()
        # Delete classification results
        db.table("classification_results").remove(q.case_id == case_id)
        # Delete enrichment results
        db.table("enrichment_results").remove(q.case_id == case_id)
        # Update case record
        db.table("cases").update({
            "status": CaseStatus.RECEIVED.value,
            "classification_category": None,
            "confidence_score": 0,
            "requires_human_review": False,
            "summary": None,
            "content_safety_result": None,
            "updated_at": datetime.utcnow().isoformat()
        }, q.case_id == case_id)
        db.storage.flush()
        logger.info(f"[LocalDB] Reset case to RECEIVED: {case_id}")

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

    async def upsert_email(self, email_doc: Dict) -> None:
        db = _get_db()
        E = Query()
        db.table("emails").upsert(dict(email_doc), E.email_id == email_doc["email_id"])
        db.storage.flush()
        logger.info(f"[LocalDB] Upserted email {email_doc.get('email_id')}")

    # Compatibility alias
    async def create_email(self, email_doc: Dict) -> None:
        await self.upsert_email(email_doc)

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

    async def find_recent_case_by_subject_and_sender(
        self, 
        subject: str, 
        sender: str, 
        minutes: int = 10
    ) -> Optional[str]:
        """Aggressive fallback: match by Subject + Sender within a small time window."""
        from datetime import timedelta
        db = _get_db()
        C = Query()
        
        threshold = (datetime.utcnow() - timedelta(minutes=minutes)).isoformat()
        
        # TinyDB doesn't support complex date comparisons in a simple query easily,
        # but we can do a search with a custom test function or filter after search.
        results = db.table("cases").search(
            (C.subject == subject) & 
            (C.sender == sender) & 
            (C.updated_at >= threshold)
        )
        
        if results:
            results.sort(key=lambda c: c.get("updated_at") or "", reverse=True)
            return results[0]["case_id"]
        return None

    # ===== DOCUMENTS =====

    async def upsert_document(self, doc: Dict) -> None:
        db = _get_db()
        D = Query()
        db.table("documents").upsert(dict(doc), D.document_id == doc["document_id"])
        db.storage.flush()
        logger.info(f"[LocalDB] Upserted document {doc.get('document_id')}")

    # Compatibility alias
    async def create_document(self, doc: Dict) -> None:
        await self.upsert_document(doc)

    async def update_document(self, doc: Dict) -> None:
        await self.upsert_document(doc)

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

    # ===== ENRICHMENT RESULTS =====

    async def save_enrichment_result(self, result: Dict) -> None:
        db = _get_db()
        db.table("enrichment_results").insert(dict(result))
        db.storage.flush()
        logger.info(f"[LocalDB] Saved enrichment for case {result.get('case_id')}")

    async def get_enrichment_for_case(self, case_id: str) -> Optional[Dict]:
        db = _get_db()
        R = Query()
        results = db.table("enrichment_results").search(R.case_id == case_id)
        if not results:
            return None
        return sorted(results, key=lambda r: r.get("enriched_at") or "", reverse=True)[0]

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

    async def get_dashboard_metrics(self) -> Dict:
        """
        Calculates and returns metrics specifically designed for the dashboard:
        - top metrics
        - sankey chart data
        - pie chart data
        """
        db = _get_db()
        cases = db.table("cases").all()
        
        total_cases = len(cases)
        classified_cases = [c for c in cases if c.get("status") in {"CLASSIFIED", "PROCESSED", "PENDING_REVIEW", "NEEDS_REVIEW_SAFETY"}]
        
        # 1. Avg Confidence
        total_confidence = sum([c.get("confidence_score", 0) for c in classified_cases if c.get("confidence_score") is not None])
        avg_confidence = total_confidence / len(classified_cases) if classified_cases else 0

        # 2. Review Required Count
        review_required_count = len([c for c in cases if c.get("status") in {"PENDING_REVIEW", "NEEDS_REVIEW_SAFETY", "BLOCKED_SAFETY"}])

        # 3. Auto-Triage Rate
        # Cases that successfully made it to an end state without review
        auto_triaged = len([c for c in cases if c.get("status") in {"CLASSIFIED", "PROCESSED"}])
        auto_triage_rate = auto_triaged / total_cases if total_cases > 0 else 0

        # 4. Pie Chart Data (Pipeline Status Triage)
        status_counts = {}
        for c in cases:
            s = c.get("status", "RECEIVED")
            status_counts[s] = status_counts.get(s, 0) + 1

        # Color mapping for statuses
        color_map = {
            "RECEIVED": "#94a3b8",
            "PROCESSING": "#60a5fa",
            "CLASSIFIED": "#34d399",
            "PROCESSED": "#10b981",
            "PENDING_REVIEW": "#f59e0b",
            "NEEDS_REVIEW_SAFETY": "#f97316",
            "BLOCKED_SAFETY": "#ef4444",
            "FAILED": "#ef4444"
        }

        pie_chart = [
            {"name": status, "value": count, "color": color_map.get(status, "#cbd5e1")}
            for status, count in status_counts.items()
        ]

        # 5. Sankey Chart Data
        # Nodes: 0=Intake, 1=Safety Cleared, 2=Safety Flagged/Blocked, 
        # 3=Documentation, 4=Inquiry, 5=Auto-Processed, 6=Manual Review
        
        # Calculate splits
        # Intake -> Safety
        intake_count = total_cases
        
        safety_cleared = len([c for c in cases if c.get("status") not in {"NEEDS_REVIEW_SAFETY", "BLOCKED_SAFETY", "RECEIVED"}])
        safety_flagged = len([c for c in cases if c.get("status") in {"NEEDS_REVIEW_SAFETY", "BLOCKED_SAFETY"}])
        
        # Categories
        cat_docs = len([c for c in cases if c.get("classification_category") == "Documentation Submission"])
        cat_inq = len([c for c in cases if c.get("classification_category") == "Inquiry"])
        cat_other = safety_cleared - cat_docs - cat_inq
        
        sankey_nodes = [
            {"name": "Total Incoming"},      # 0
            {"name": "Safety Cleared"},      # 1
            {"name": "Safety Flagged"},      # 2
            {"name": "Documentation"},       # 3
            {"name": "Inquiry"},             # 4
            {"name": "Other Categories"},    # 5
            {"name": "Auto-Processed"},      # 6
            {"name": "Review Required"}      # 7
        ]
        
        sankey_links = [
            {"source": 0, "target": 1, "value": safety_cleared},
            {"source": 0, "target": 2, "value": safety_flagged},
            {"source": 1, "target": 3, "value": cat_docs},
            {"source": 1, "target": 4, "value": cat_inq},
            {"source": 1, "target": 5, "value": max(0, cat_other)},
            
            # For simplicity, routing standard classifications to Auto-Processed or Review based on global review count
            # In a real app we'd map this per-node, but an aggregate is fine for display
            {"source": 3, "target": 6, "value": max(0, cat_docs - (review_required_count // 3))},
            {"source": 3, "target": 7, "value": review_required_count // 3},
            {"source": 4, "target": 6, "value": max(0, cat_inq - (review_required_count // 3))},
            {"source": 4, "target": 7, "value": review_required_count // 3},
            {"source": 5, "target": 6, "value": max(0, cat_other - (review_required_count - 2 * (review_required_count // 3)))},
            {"source": 5, "target": 7, "value": max(0, review_required_count - 2 * (review_required_count // 3))},
            {"source": 2, "target": 7, "value": safety_flagged} # Safety flagged always goes to review
        ]

        # Clean 0 value links
        sankey_links = [l for l in sankey_links if l["value"] > 0]

        return {
            "decision_accuracy": avg_confidence,
            "avg_agent_processing_time_ms": 3450, # Mocked latency stat
            "extraction_accuracy": 0.94,          # Mocked extraction stat
            "action_required_threads": review_required_count,
            "auto_triage_rate": auto_triage_rate,
            "pie_chart": pie_chart,
            "sankey_chart": {
                "nodes": sankey_nodes,
                "links": sankey_links
            }
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
