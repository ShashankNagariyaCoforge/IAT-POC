"""
Cosmos DB Client V2 — writes exclusively to NEW v2 collections.
Reads case data from existing v1 collections (via the existing db service).
"""

import logging
from datetime import datetime
from typing import Any, Dict, Optional

from motor.motor_asyncio import AsyncIOMotorClient

from config import settings as base_settings
from pipeline_v2.config import v2_settings

logger = logging.getLogger(__name__)


class CosmosClientV2:
    def __init__(self):
        if base_settings.demo_mode:
            self._demo = True
            self._client = None
            self._db = None
            logger.info("[CosmosV2] DEMO_MODE — all DB writes are no-ops")
            return
        self._demo = False
        conn_str = base_settings.mongodb_connection_string
        if not conn_str:
            raise RuntimeError("MONGODB_CONNECTION_STRING not configured")
        self._client = AsyncIOMotorClient(conn_str)
        self._db = self._client[v2_settings.v2_cosmos_database_name]

    def _col(self, name: str):
        return self._db[name]

    # ── Cases V2 ─────────────────────────────────────────────────────────────

    async def save_case(self, doc: Dict[str, Any]):
        if self._demo:
            return
        col = self._col(v2_settings.v2_cosmos_cases_collection)
        await col.replace_one({"case_id": doc["case_id"]}, doc, upsert=True)
        logger.info(f"[CosmosV2] Saved case: {doc['case_id']}")

    async def update_case_status(self, case_id: str, status: str, pipeline_step: str = ""):
        if self._demo:
            return
        col = self._col(v2_settings.v2_cosmos_cases_collection)
        update = {"$set": {"processing_status": status, "updated_at": datetime.utcnow().isoformat()}}
        if pipeline_step:
            update["$set"]["pipeline_step"] = pipeline_step
        await col.update_one({"case_id": case_id}, update, upsert=True)

    async def get_case(self, case_id: str) -> Optional[Dict]:
        if self._demo:
            return None
        col = self._col(v2_settings.v2_cosmos_cases_collection)
        return await col.find_one({"case_id": case_id})

    # ── Extractions V2 ───────────────────────────────────────────────────────

    async def save_extraction(self, doc: Dict[str, Any]):
        if self._demo:
            return
        col = self._col(v2_settings.v2_cosmos_extractions_collection)
        await col.replace_one({"case_id": doc["case_id"]}, doc, upsert=True)
        logger.info(f"[CosmosV2] Saved extraction: {doc['case_id']}")

    # ── Documents V2 ─────────────────────────────────────────────────────────

    async def save_document(self, doc: Dict[str, Any]):
        if self._demo:
            return
        col = self._col(v2_settings.v2_cosmos_documents_collection)
        doc_key = f"{doc['case_id']}_{doc['filename']}"
        await col.replace_one({"id": doc_key}, {**doc, "id": doc_key}, upsert=True)

    # ── Pipeline Logs V2 ─────────────────────────────────────────────────────

    async def log_stage(
        self,
        case_id: str,
        stage: str,
        status: str,
        duration_seconds: float = 0.0,
        llm_tokens: int = 0,
        error: Optional[str] = None,
        metadata: Optional[Dict] = None,
    ):
        if self._demo or not v2_settings.v2_log_pipeline_steps:
            return
        col = self._col(v2_settings.v2_cosmos_logs_collection)
        # Use base deployment name as fallback for the log record
        deployment_name = (
            v2_settings.v2_azure_openai_deployment_large
            or base_settings.azure_openai_deployment
        )
        doc = {
            "id": f"{case_id}_{stage}_{datetime.utcnow().timestamp()}",
            "case_id": case_id,
            "stage": stage,
            "status": status,
            "duration_seconds": duration_seconds,
            "llm_tokens_used": llm_tokens,
            "llm_model": deployment_name,
            "error": error,
            "metadata": metadata or {},
            "logged_at": datetime.utcnow().isoformat(),
        }
        await col.insert_one(doc)

    async def initialize_collections(self):
        """Ensure indexes on all v2 collections."""
        if self._demo:
            return
        await self._col(v2_settings.v2_cosmos_cases_collection).create_index("case_id", unique=True)
        await self._col(v2_settings.v2_cosmos_extractions_collection).create_index("case_id", unique=True)
        await self._col(v2_settings.v2_cosmos_documents_collection).create_index("case_id")
        await self._col(v2_settings.v2_cosmos_logs_collection).create_index([("case_id", 1), ("stage", 1)])
        logger.info("[CosmosV2] Indexes ensured on v2 collections")
