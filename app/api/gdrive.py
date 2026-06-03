"""Google Drive API endpoints for listing folders and managing settings."""

import asyncio
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from googleapiclient.discovery import build
from apscheduler.triggers.cron import CronTrigger

from app.core.database import get_session
from app.core.security import get_current_user
from app.models.user import User
from app.models.config import AppConfig
from app.services.gdrive import get_credentials

router = APIRouter(prefix="/api/gdrive", tags=["gdrive"])


class FolderSettingsUpdate(BaseModel):
    folder_id: str
    sync_schedule: str = "manual"
    notification_urls: str | None = None
    notify_on_success: bool = False
    notify_on_failure: bool = True

    @field_validator("sync_schedule")
    @classmethod
    def validate_sync_schedule(cls, v: str) -> str:
        if v == "manual":
            return v
        try:
            CronTrigger.from_crontab(v)
        except Exception:
            raise ValueError(
                f"Invalid cron expression: '{v}'. "
                "Use standard 5-field cron syntax (e.g. '0 2 * * *') or 'manual'."
            )
        return v


@router.get("/folders")
async def list_folders(
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """List all folders in the authenticated user's Google Drive."""
    stmt = select(AppConfig).where(AppConfig.user_id == current_user.id)
    config = (await session.execute(stmt)).scalar_one_or_none()

    if not config or not config.gdrive_refresh_token:
        raise HTTPException(status_code=401, detail="Google Drive not connected")

    try:
        credentials = await get_credentials(session, current_user.id)
        
        loop = asyncio.get_running_loop()
        def _fetch_folders():
            service = build("drive", "v3", credentials=credentials, cache_discovery=False)
            query = "mimeType='application/vnd.google-apps.folder' and trashed=false"
            folders = []
            page_token = None
            while True:
                results = service.files().list(
                    q=query,
                    fields="nextPageToken, files(id, name)",
                    orderBy="name",
                    pageSize=1000,
                    pageToken=page_token
                ).execute()
                folders.extend(results.get("files", []))
                page_token = results.get("nextPageToken")
                if not page_token:
                    break
            return folders

        folders = await loop.run_in_executor(None, _fetch_folders)
        return folders
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/settings")
async def update_settings(
    update: FolderSettingsUpdate, 
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Save the selected Google Drive sync folder ID, sync schedule, and notification settings."""
    stmt = select(AppConfig).where(AppConfig.user_id == current_user.id)
    config = (await session.execute(stmt)).scalar_one_or_none()

    if not config:
        config = AppConfig(user_id=current_user.id)
        session.add(config)

    config.gdrive_sync_folder_id = update.folder_id
    config.sync_schedule = update.sync_schedule
    config.notification_urls = update.notification_urls
    config.notify_on_success = update.notify_on_success
    config.notify_on_failure = update.notify_on_failure
    await session.commit()
    
    # The worker polls the DB every 60s and will pick up the new schedule automatically.
    
    return {
        "status": "ok", 
        "folder_id": config.gdrive_sync_folder_id, 
        "sync_schedule": config.sync_schedule,
        "notification_urls": config.notification_urls,
        "notify_on_success": config.notify_on_success,
        "notify_on_failure": config.notify_on_failure
    }

class NotificationTest(BaseModel):
    urls: str

@router.post("/test-notification")
async def test_notification(
    payload: NotificationTest,
    current_user: User = Depends(get_current_user)
):
    """Test notification URLs."""
    from app.services.notifier import send_notification
    success = await send_notification(
        title="SMS Web Viewer: Test",
        body="This is a test notification from your SMS Web Viewer instance.",
        notification_urls=payload.urls
    )
    if success:
        return {"status": "ok", "message": "Notification sent successfully"}
    else:
        raise HTTPException(status_code=400, detail="Failed to send notification. Check URLs.")
