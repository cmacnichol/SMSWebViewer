"""FastAPI application entry point.

Configures lifespan (DB init, scheduler), mounts API router,
MCP SSE transport, and static frontend files.
"""

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import router as main_router
from app.api.auth import router as auth_router
from app.api.gdrive import router as gdrive_router
from app.core.config import get_settings
from app.core.database import init_db
from app.core.mcp_server import mcp
from app.core.scheduler import setup_scheduler, shutdown_scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: initialize DB and scheduler on startup."""
    logger.info("Starting SMS Web Viewer...")
    
    settings = get_settings()
    if not settings.GCP_CLIENT_ID or not settings.GCP_CLIENT_SECRET:
        logger.warning("=" * 60)
        logger.warning("GCP OAuth Credentials are MISSING or MALFORMED in .env!")
        logger.warning("The application will run, but you will not be able to connect to Google Drive.")
        logger.warning("Please edit the .env file, add your Client ID and Secret, and restart the container.")
        logger.warning("=" * 60)
    else:
        logger.info("Google OAuth credentials found.")

    await init_db()
    await setup_scheduler()
    yield
    shutdown_scheduler()
    logger.info("SMS Web Viewer shut down.")


app = FastAPI(
    title="SMS Web Viewer",
    description="SMS Backup & Restore viewer with Google Drive integration",
    version="1.0.0",
    lifespan=lifespan,
)

# API routes
app.include_router(main_router)
app.include_router(auth_router)
app.include_router(gdrive_router)

from mcp.server.sse import SseServerTransport

sse = SseServerTransport("/mcp/messages/")

async def handle_sse(request):
    async with sse.connect_sse(
        request.scope, request.receive, request._send
    ) as streams:
        await mcp._mcp_server.run(
            streams[0],
            streams[1],
            mcp._mcp_server.create_initialization_options(),
        )

app.add_route("/mcp/sse", handle_sse, methods=["GET"])
app.mount("/mcp/messages/", sse.handle_post_message)

# Static files (frontend)
static_dir = os.path.join(os.path.dirname(__file__), "static")
app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/")
async def root():
    """Redirect root to the frontend."""
    return RedirectResponse(url="/static/index.html")


@app.get("/health")
async def health():
    """Health check endpoint for Docker HEALTHCHECK."""
    return {"status": "ok"}
