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


async def get_credentials(session: AsyncSession) -> Credentials:
    """Get and automatically refresh OAuth credentials from the database."""
    stmt = select(AppConfig).where(AppConfig.id == 1)
    config = (await session.execute(stmt)).scalar_one_or_none()

    if not config or not config.gdrive_refresh_token:
        raise ValueError("Google Drive is not connected.")

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
        logger.info("Refreshing Google Drive access token...")
        creds.refresh(Request())
        config.gdrive_access_token = creds.token
        if creds.expiry:
            config.gdrive_token_expiry = creds.expiry.replace(
                tzinfo=timezone.utc
            ).timestamp()
        await session.commit()

    return creds


def _resolve_newest_file(service, folder_id: str, is_calls: bool) -> str:
    """Find the newest XML file in the specified folder based on type."""
    # Build query to search inside the specific folder
    query = f"'{folder_id}' in parents and trashed = false"
    
    # Optional: basic naming convention checks based on typical SMS Backup & Restore names
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


def _download_file(service, file_id: str, dest_path: Path) -> Path:
    """Download a file from Google Drive to a local path."""
    request = service.files().get_media(fileId=file_id)
    with open(dest_path, "wb") as fh:
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            status, done = downloader.next_chunk()
            if status:
                logger.info(f"Download progress: {int(status.progress() * 100)}%")
    logger.info(f"Downloaded to {dest_path}")
    return dest_path


async def download_xml(is_calls: bool = False, last_modified: str | None = None) -> tuple[Path | None, str | None]:
    """Download the newest XML backup file from the configured Google Drive folder.

    Args:
        is_calls: If True, look for calls backup; otherwise SMS/MMS.
        last_modified: The last known modifiedTime to check against.

    Returns:
        Tuple of (Path to the downloaded XML file or None if skipped, new modifiedTime)
    """
    dest = Path(f"/tmp/{'calls' if is_calls else 'sms'}_backup.xml")

    # Use a short-lived DB session to get credentials and folder ID
    async with async_session_maker() as session:
        creds = await get_credentials(session)
        
        stmt = select(AppConfig).where(AppConfig.id == 1)
        config = (await session.execute(stmt)).scalar_one_or_none()
        if not config or not config.gdrive_sync_folder_id:
            raise ValueError("No sync folder selected in Google Drive settings.")
        folder_id = config.gdrive_sync_folder_id

    loop = asyncio.get_event_loop()

    # Run synchronous Google API calls in a thread
    def _sync_download():
        service = build("drive", "v3", credentials=creds, cache_discovery=False)
        resolved_id, mod_time = _resolve_newest_file(service, folder_id, is_calls)
        
        if last_modified and mod_time and mod_time <= last_modified:
            logger.info(f"File hasn't changed since {last_modified}. Skipping download.")
            return None, mod_time
            
        return _download_file(service, resolved_id, dest), mod_time

    return await loop.run_in_executor(None, _sync_download)
