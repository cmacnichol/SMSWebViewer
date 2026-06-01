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
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from app.api.routes import router as main_router
from app.api.auth import router as gdrive_auth_router
from app.api.user_auth import router as user_auth_router
from app.api.gdrive import router as gdrive_router
from app.core.config import get_settings
from app.core.database import init_db
from app.core.mcp_server import mcp

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: initialize DB on startup."""
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
    yield
    logger.info("SMS Web Viewer shut down.")


app = FastAPI(
    title="SMS Web Viewer",
    description="SMS Backup & Restore viewer with Google Drive integration",
    version="1.1.2",
    lifespan=lifespan,
)

app.add_middleware(ProxyHeadersMiddleware, trusted_hosts="*")

# API routes
app.include_router(main_router)
app.include_router(gdrive_auth_router)
app.include_router(user_auth_router)
app.include_router(gdrive_router)

from mcp.server.sse import SseServerTransport

sse = SseServerTransport("/mcp/messages/")

import hashlib
from fastapi import Request, HTTPException, Depends
from sqlalchemy import select
from app.models.api_token import ApiToken
from app.core.database import get_session
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.mcp_server import mcp_user_id, mcp_is_global

async def verify_mcp_token(request: Request, db: AsyncSession = Depends(get_session)):
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    
    token = auth_header[7:]
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    
    stmt = select(ApiToken).where(ApiToken.token_hash == token_hash)
    api_token = (await db.execute(stmt)).scalar_one_or_none()
    
    if not api_token:
        raise HTTPException(status_code=401, detail="Invalid API Token")
        
    mcp_user_id.set(api_token.user_id)
    mcp_is_global.set(api_token.is_global)
    return api_token

from fastapi.responses import JSONResponse
from app.core.database import async_session_maker

async def sse_asgi_app(scope, receive, send):
    if scope["type"] != "http": return
    if scope["method"] != "GET":
        response = JSONResponse(status_code=405, content={"detail": "Method Not Allowed"})
        return await response(scope, receive, send)
        
    request = Request(scope, receive, send)
    async with async_session_maker() as db:
        try:
            await verify_mcp_token(request, db)
        except HTTPException as e:
            response = JSONResponse(status_code=e.status_code, content={"detail": e.detail})
            return await response(scope, receive, send)

    async with sse.connect_sse(scope, receive, send) as streams:
        await mcp._mcp_server.run(
            streams[0],
            streams[1],
            mcp._mcp_server.create_initialization_options(),
        )

app.mount("/mcp/sse", sse_asgi_app)

async def messages_asgi_app(scope, receive, send):
    if scope["type"] != "http": return
    if scope["method"] != "POST":
        response = JSONResponse(status_code=405, content={"detail": "Method Not Allowed"})
        return await response(scope, receive, send)
        
    request = Request(scope, receive, send)
    async with async_session_maker() as db:
        try:
            await verify_mcp_token(request, db)
        except HTTPException as e:
            response = JSONResponse(status_code=e.status_code, content={"detail": e.detail})
            return await response(scope, receive, send)
            
    await sse.handle_post_message(scope, receive, send)

app.mount("/mcp/messages", messages_asgi_app)


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
