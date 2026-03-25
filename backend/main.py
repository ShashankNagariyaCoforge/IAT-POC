"""
IAT Insurance AI Email Automation Platform
FastAPI Application Entry Point
"""

import sys
import asyncio
import logging
from contextlib import asynccontextmanager
from concurrent.futures import ProcessPoolExecutor
import multiprocessing

# Windows-specific fix for Playwright/Subprocess support
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from api.webhook import router as webhook_router
from api.cases import router as cases_router
from api.sync import router as sync_router
from api.process import router as process_router
from api.health import router as health_router
from process_v2 import router as process_v2_router
from middleware.auth import JWTAuthMiddleware
from services.cosmos_db import CosmosDBService
from services.graph_client import GraphClient
from services.email_poller import start_email_poll_loop
from utils.logging import setup_logging

# Setup structured JSON logging
setup_logging(settings.log_level)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown lifecycle."""
    logger.info("Starting IAT Insurance Email Automation Platform...")

    renewal_task = None
    poll_task = None
    executor = None

    # Step: Initialize Global Process Pool for CPU-bound tasks (PII, Bounding Box, Rendering)
    num_cpus = multiprocessing.cpu_count()
    # We cap at 8 or use available CPUs to fully utilize the VM
    max_workers = min(num_cpus, 8) 
    logger.info(f"Initializing global ProcessPoolExecutor with {max_workers} workers.")
    executor = ProcessPoolExecutor(max_workers=max_workers)
    app.state.executor = executor

    if settings.demo_mode:
        # ── Demo Mode: skip all cloud service initialization ──────────────
        logger.info("🎯 DEMO MODE active — using local TinyDB, skipping Cosmos/Graph init.")
        logger.info("   Run `python demo_ingest.py` first to populate the local DB.")
    else:
        # ── Production: initialize Azure services ─────────────────────────
        try:
            if not settings.azure_cosmos_endpoint and not settings.mongodb_connection_string:
                logger.warning(
                    "Cosmos DB is not configured (missing Endpoint or MongoDB Connection String). "
                    "Set these in your .env file."
                )
            else:
                cosmos = CosmosDBService()
                await cosmos.initialize_containers()
                logger.info("Cosmos DB initialized.")
                
            # Initialize Blob Storage containers
            from services.blob_storage import BlobStorageService
            blob_svc = BlobStorageService()
            await blob_svc.ensure_containers()
            logger.info("Blob Storage containers verified/created.")
            
        except Exception as e:
            logger.warning(f"Production service initialization failed: {e}")

        try:
            if not settings.graph_client_id or not settings.graph_tenant_id:
                logger.warning(
                    "GRAPH_CLIENT_ID / GRAPH_TENANT_ID not configured — "
                    "Microsoft Graph webhook subscription will be unavailable."
                )
            else:
                graph = GraphClient()
                await graph.ensure_webhook_subscription()
                logger.info("Graph API webhook subscription active.")
                renewal_task = asyncio.create_task(_renew_subscription_loop(graph))
                app.state.renewal_task = renewal_task
        except Exception as e:
            logger.warning(f"Graph webhook setup skipped: {e}")

    # ── Auto Email Polling (always start — gracefully skips if creds missing) ──
    poll_task = asyncio.create_task(
        start_email_poll_loop(interval_seconds=settings.email_poll_interval_seconds)
    )
    app.state.poll_task = poll_task
    logger.info(
        f"📧 Email auto-poller started — interval: {settings.email_poll_interval_seconds}s"
    )

    logger.info("Application startup complete.")
    yield

    # Shutdown
    logger.info("Shutting down...")
    if renewal_task is not None:
        renewal_task.cancel()
    if poll_task is not None:
        poll_task.cancel()
        logger.info("Email auto-poller stopped.")
    
    if executor:
        logger.info("Shutting down global ProcessPoolExecutor...")
        executor.shutdown(wait=True)


async def _renew_subscription_loop(graph: GraphClient):
    """Background task: renew Graph subscription every 48 hours."""
    interval = settings.webhook_subscription_renewal_hours * 3600
    while True:
        await asyncio.sleep(interval)
        try:
            await graph.renew_webhook_subscription()
            logger.info("Graph webhook subscription renewed successfully.")
        except Exception as e:
            logger.error(f"Failed to renew Graph subscription: {e}")


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
app.include_router(sync_router, prefix="/api", tags=["Sync"])
app.include_router(process_router, prefix="/api", tags=["Process"])
app.include_router(process_v2_router, prefix="/api/v2", tags=["Process V2"])
app.include_router(health_router, tags=["Health"])
