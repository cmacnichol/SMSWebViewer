"""OAuth2 Authentication endpoints for Google Drive."""

from datetime import timezone
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from google_auth_oauthlib.flow import Flow

from app.core.config import get_settings
from app.core.database import get_session
from app.core.security import get_current_user
from app.models.user import User
from app.models.config import AppConfig

router = APIRouter(prefix="/api/auth", tags=["auth"])

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]


def get_flow():
    """Create a Google Auth Flow from application settings."""
    settings = get_settings()
    if not settings.GCP_CLIENT_ID or not settings.GCP_CLIENT_SECRET:
        raise HTTPException(
            status_code=500, detail="OAuth credentials not configured in environment"
        )

    client_config = {
        "web": {
            "client_id": settings.GCP_CLIENT_ID,
            "project_id": "smsviewer",
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
            "client_secret": settings.GCP_CLIENT_SECRET,
            "redirect_uris": [settings.OAUTH_REDIRECT_URI],
        }
    }

    return Flow.from_client_config(
        client_config, scopes=SCOPES, redirect_uri=settings.OAUTH_REDIRECT_URI
    )


@router.get("/login")
async def login(current_user: User = Depends(get_current_user)):
    """Initiate the OAuth flow, returning the Google login URL."""
    try:
        flow = get_flow()
        auth_url, _ = flow.authorization_url(
            access_type="offline", include_granted_scopes="true", prompt="consent"
        )
        return {"url": auth_url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/callback")
async def callback(code: str, session: AsyncSession = Depends(get_session), current_user: User = Depends(get_current_user)):
    """Handle the OAuth callback, exchanging code for tokens."""
    try:
        flow = get_flow()
        flow.fetch_token(code=code)
        credentials = flow.credentials

        # Save to DB
        stmt = select(AppConfig).where(AppConfig.user_id == current_user.id)
        config = (await session.execute(stmt)).scalar_one_or_none()

        if not config:
            config = AppConfig(user_id=current_user.id)
            session.add(config)

        # Only update refresh token if we received a new one
        if credentials.refresh_token:
            config.gdrive_refresh_token = credentials.refresh_token
            
        config.gdrive_access_token = credentials.token
        if credentials.expiry:
            config.gdrive_token_expiry = credentials.expiry.replace(
                tzinfo=timezone.utc
            ).timestamp()

        await session.commit()

        # Redirect back to frontend
        return RedirectResponse(url="/static/index.html?auth=success")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"OAuth callback failed: {str(e)}")


@router.get("/status")
async def status(session: AsyncSession = Depends(get_session), current_user: User = Depends(get_current_user)):
    """Check if the application is linked to a Google Drive account."""
    stmt = select(AppConfig).where(AppConfig.user_id == current_user.id)
    config = (await session.execute(stmt)).scalar_one_or_none()

    is_connected = bool(config and config.gdrive_refresh_token)
    return {
        "connected": is_connected,
        "folder_id": config.gdrive_sync_folder_id if config else None,
        "sync_schedule": config.sync_schedule if config else "manual",
        "notification_urls": config.notification_urls if config else None,
        "notify_on_success": config.notify_on_success if config else False,
        "notify_on_failure": config.notify_on_failure if config else True,
    }

@router.post("/disconnect")
async def disconnect(session: AsyncSession = Depends(get_session), current_user: User = Depends(get_current_user)):
    """Disconnect Google Drive by clearing the OAuth tokens."""
    stmt = select(AppConfig).where(AppConfig.user_id == current_user.id)
    config = (await session.execute(stmt)).scalar_one_or_none()
    
    if config:
        config.gdrive_refresh_token = None
        config.gdrive_access_token = None
        config.gdrive_token_expiry = None
        await session.commit()
    
    return {"status": "success"}
