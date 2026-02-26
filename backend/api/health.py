"""
Health and system stats API endpoints (Step 15).
Public endpoint: GET /health
Protected endpoint: GET /api/stats
"""

import logging

from fastapi import APIRouter

from services.cosmos_db import CosmosDBService

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/health")
async def health_check():
    """
    Public health check endpoint.
    Used by Docker healthcheck and monitoring systems.
    Returns 200 if the service is running.
    """
    return {"status": "healthy", "service": "IAT Insurance Email Automation"}


@router.get("/api/stats")
async def get_stats():
    """
    Dashboard statistics endpoint.
    Returns total cases, breakdown by status and category, and human review count.
    Requires JWT authentication (enforced by middleware).
    """
    cosmos = CosmosDBService()
    stats = await cosmos.get_stats()
    return stats
