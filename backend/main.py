"""
IAT Insurance AI Email Automation Platform
FastAPI Application Entry Point
"""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from api.webhook import router as webhook_router
from api.cases import router as cases_router
from api.health import router as health_router
from middleware.auth import JWTAuthMiddleware
from services.cosmos_db import CosmosDBService
from services.graph_client import GraphClient
from utils.logging import setup_logging

# Setup structured JSON logging
setup_logging(settings.log_level)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown lifecycle."""
    logger.info("Starting IAT Insurance Email Automation Platform...")

    # Initialize services on startup
    try:
        # Ensure Cosmos DB containers exist
        cosmos = CosmosDBService()
        await cosmos.initialize_containers()
        logger.info("Cosmos DB containers verified.")

        # Register or renew Microsoft Graph webhook subscription
        graph = GraphClient()
        await graph.ensure_webhook_subscription()
        logger.info("Graph API webhook subscription active.")

        # Schedule background subscription renewal
        renewal_task = asyncio.create_task(_renew_subscription_loop(graph))
        app.state.renewal_task = renewal_task

    except Exception as e:
        logger.error(f"Startup error: {e}", exc_info=True)
        raise

    yield

    # Shutdown
    logger.info("Shutting down...")
    if hasattr(app.state, "renewal_task"):
        app.state.renewal_task.cancel()


async def _renew_subscription_loop(graph: GraphClient):
    """Background task: renew Graph subscription every 48 hours."""
    interval = settings.webhook_subscription_renewal_hours * 3600
    while True:
        await asyncio.sleep(interval)
        try:
            await graph.renew_webhook_subscription()
            logger.info("Graph webhook subscription renewed successfully.")
        except Exception as e:
            logger.error(f"Failed to renew Graph subscription: {e}", exc_info=True)


# Build FastAPI app
app = FastAPI(
    title="IAT Insurance AI Email Automation",
    description="AI-powered email triage and case management platform for IAT Insurance.",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)

# CORS (tightened in production via allowed_origins in settings)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT"],
    allow_headers=["Authorization", "Content-Type"],
)

# JWT auth middleware (protects all /api/* routes)
app.add_middleware(JWTAuthMiddleware)

# Routers
app.include_router(webhook_router, prefix="/webhook", tags=["Webhook"])
app.include_router(cases_router, prefix="/api", tags=["Cases"])
app.include_router(health_router, tags=["Health"])
