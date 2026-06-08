"""Google Drive download service using OAuth2 credentials."""

import asyncio
from datetime import timezone
import logging
from pathlib import Path

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import async_session_maker
from app.models.config import AppConfig

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]


async def get_credentials(session: AsyncSession, user_id: str) -> Credentials:
    """Get and automatically refresh OAuth credentials from the database for a specific user."""
    stmt = select(AppConfig).where(AppConfig.user_id == user_id)
    config = (await session.execute(stmt)).scalar_one_or_none()

    if not config or not config.gdrive_refresh_token:
        raise ValueError(f"Google Drive is not connected for user {user_id}.")

    settings = get_settings()
    creds = Credentials(
        token=config.gdrive_access_token,
        refresh_token=config.gdrive_refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=settings.GCP_CLIENT_ID,
        client_secret=settings.GCP_CLIENT_SECRET,
        scopes=SCOPES,
    )

    if not creds.valid:
        logger.info(f"Refreshing Google Drive access token for user {user_id}...")
        try:
            creds.refresh(Request())
            config.gdrive_access_token = creds.token
            if creds.expiry:
                config.gdrive_token_expiry = creds.expiry.replace(
                    tzinfo=timezone.utc
                ).timestamp()
            await session.commit()
        except Exception as e:
            from google.auth.exceptions import RefreshError
            if isinstance(e, RefreshError):
                logger.error(f"Google Drive token expired or revoked for user {user_id}: {e}")
                # Clear tokens so the UI sees it as disconnected
                config.gdrive_refresh_token = None
                config.gdrive_access_token = None
                await session.commit()
                
                # Send notification if configured
                if getattr(config, 'notify_on_failure', False) and getattr(config, 'notification_urls', None):
                    from app.services.notifier import send_notification
                    import asyncio
                    asyncio.create_task(send_notification(
                        title="SMS Web Viewer - Action Required",
                        body="Your Google Drive authentication token has expired. Please log in to the web interface and re-authenticate.",
                        notification_urls=config.notification_urls
                    ))
                raise ValueError("Google Drive authentication token expired. Please re-authenticate.")
            else:
                raise

    return creds


def _resolve_newest_file(service, folder_id: str, is_calls: bool) -> str:
    """Find the newest XML file in the specified folder based on type."""
    query = f"'{folder_id}' in parents and trashed = false"
    
    if is_calls:
        query += " and name contains 'calls'"
    else:
        query += " and name contains 'sms'"

    results = (
        service.files()
        .list(
            q=query,
            fields="files(id, name, modifiedTime)",
            orderBy="modifiedTime desc",
            pageSize=10,
        )
        .execute()
    )
    files = results.get("files", [])

    if not files:
        file_type = "calls" if is_calls else "sms"
        raise FileNotFoundError(
            f"No {file_type} XML files found in the configured Google Drive folder."
        )

    selected = files[0]
    mod_time = selected.get("modifiedTime", "")
    logger.info(
        f"Resolved newest file: '{selected['name']}' "
        f"(id={selected['id']}, modified={mod_time})"
    )
    return selected["id"], mod_time


def _download_file(service, file_id: str, dest_path: Path, progress_callback=None) -> Path:
    """Download a file from Google Drive to a local path."""
    request = service.files().get_media(fileId=file_id)
    with open(dest_path, "wb") as fh:
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            status, done = downloader.next_chunk()
            if status:
                pct = int(status.progress() * 100)
                if progress_callback:
                    progress_callback(pct)
    logger.info(f"Downloaded to {dest_path}")
    return dest_path


async def download_xml(is_calls: bool = False, last_modified: str | None = None, user_id: str = None, progress_callback=None) -> tuple[Path | None, str | None]:
    """Download the newest XML backup file from the configured Google Drive folder.

    Args:
        is_calls: If True, look for calls backup; otherwise SMS/MMS.
        last_modified: The last known modifiedTime to check against.
        user_id: The ID of the user requesting the download.
        progress_callback: Optional function to call with download percentage.

    Returns:
        Tuple of (Path to the downloaded XML file or None if skipped, new modifiedTime)
    """
    if not user_id:
        raise ValueError("user_id must be provided for download_xml")

    dest = Path(f"/tmp/{user_id}_{'calls' if is_calls else 'sms'}_backup.xml")

    # Use a short-lived DB session to get credentials and folder ID
    async with async_session_maker() as session:
        creds = await get_credentials(session, user_id)
        
        stmt = select(AppConfig).where(AppConfig.user_id == user_id)
        config = (await session.execute(stmt)).scalar_one_or_none()
        if not config or not config.gdrive_sync_folder_id:
            raise ValueError("No sync folder selected in Google Drive settings.")
        folder_id = config.gdrive_sync_folder_id

    loop = asyncio.get_running_loop()

    # Run synchronous Google API calls in a thread
    def _sync_download():
        service = build("drive", "v3", credentials=creds, cache_discovery=False)
        resolved_id, mod_time = _resolve_newest_file(service, folder_id, is_calls)
        
        if last_modified and mod_time and mod_time <= last_modified:
            logger.info(f"File hasn't changed since {last_modified}. Skipping download.")
            return None, mod_time
            
        return _download_file(service, resolved_id, dest, progress_callback), mod_time

    return await loop.run_in_executor(None, _sync_download)
