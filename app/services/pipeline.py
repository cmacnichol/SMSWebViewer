"""Ingestion pipeline orchestrator: Google Drive -> XML -> Normalize -> DB."""

import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any

from sqlalchemy import select, update

from app.core.config import get_settings
from app.core.database import async_session_maker
from app.models.config import AppConfig
from app.services.dedup import bulk_insert_calls, bulk_insert_mms, bulk_insert_sms
from app.services.gdrive import download_xml
from app.services.normalization import compute_hash, normalize_phone
from app.services.xml_parser import parse_calls_xml, parse_sms_mms_xml

logger = logging.getLogger(__name__)

# In-process sync state per user (for short-lived "running" state tracking)
_last_sync: Dict[str, Dict[str, Any]] = {}


async def get_sync_status(user_id: str) -> dict:
    """Return the current sync status for a user."""
    # Check if running in current process
    user_sync = _last_sync.get(user_id, {})
    if user_sync.get("status") == "running":
        return user_sync.copy()
        
    # Otherwise read from database
    async with async_session_maker() as session:
        stmt = select(AppConfig).where(AppConfig.user_id == user_id).limit(1)
        config = (await session.execute(stmt)).scalar_one_or_none()
        
        if config:
            stats = {}
            if config.last_sync_stats:
                try:
                    stats = json.loads(config.last_sync_stats)
                except Exception:
                    pass
            return {
                "status": config.last_sync_status or "never",
                "timestamp": config.last_sync_time,
                "error": config.last_sync_error,
                "stats": stats
            }
            
    return {"status": "never", "timestamp": None, "error": None, "stats": {}}


async def _update_db_status(user_id: str, status: str, error: str = None, stats: dict = None, sms_mod: str = None, calls_mod: str = None) -> None:
    async with async_session_maker() as session:
        values = {
            "last_sync_status": status,
            "last_sync_time": datetime.now(timezone.utc).isoformat(),
        }
        if error is not None:
            values["last_sync_error"] = error
        if stats is not None:
            values["last_sync_stats"] = json.dumps(stats)
        if sms_mod is not None:
            values["last_sms_modified"] = sms_mod
        if calls_mod is not None:
            values["last_calls_modified"] = calls_mod
            
        stmt = update(AppConfig).where(AppConfig.user_id == user_id).values(**values)
        await session.execute(stmt)
        await session.commit()


def make_progress_callback(u_id: str, file_type: str):
    loop = asyncio.get_running_loop()
    def callback(pct: int):
        if u_id not in _last_sync:
            _last_sync[u_id] = {"status": "running", "stats": {}}
        _last_sync[u_id]["stats"]["progress"] = pct
        _last_sync[u_id]["stats"]["progress_type"] = file_type
        
        # Flush progress to DB so the web container can read it
        asyncio.run_coroutine_threadsafe(
            _update_db_status(u_id, "running", stats=_last_sync[u_id]["stats"]),
            loop
        )
    return callback


async def ingest_sms_mms_file(xml_path: Path, user_id: str) -> tuple[int, int]:
    """Ingest a local SMS/MMS XML file and return (sms_count, mms_count)."""
    settings = get_settings()
    country = settings.DEFAULT_COUNTRY_CODE
    sms_raw, mms_raw = await asyncio.to_thread(parse_sms_mms_xml, xml_path)

    # Normalize + hash SMS
    sms_records = []
    for r in sms_raw:
        norm = normalize_phone(r["address"], country)
        h = compute_hash(str(r["date_ms"]), norm, str(r["type"]), r.get("body", ""))
        sms_records.append({**r, "normalized_address": norm, "hash": h, "user_id": user_id})

    # Normalize + hash MMS
    mms_records = []
    mms_parts_map: list[tuple[str, list[dict]]] = []
    for r in mms_raw:
        norm = normalize_phone(r["address"], country)
        h = compute_hash(str(r["date_ms"]), norm, str(r["msg_box"]), r.get("body", ""))
        parts = r.pop("_parts", [])
        mms_records.append({**r, "normalized_address": norm, "hash": h, "user_id": user_id})
        mms_parts_map.append((h, parts))

    async with async_session_maker() as session:
        sms_count = await bulk_insert_sms(session, sms_records)
        mms_count = await bulk_insert_mms(session, mms_records, mms_parts_map)
        await session.commit()

    return sms_count, mms_count


async def ingest_calls_file(xml_path: Path, user_id: str) -> int:
    """Ingest a local Calls XML file and return call_count."""
    settings = get_settings()
    country = settings.DEFAULT_COUNTRY_CODE
    calls_raw = await asyncio.to_thread(parse_calls_xml, xml_path)

    call_records = []
    for r in calls_raw:
        norm = normalize_phone(r["number"], country)
        h = compute_hash(str(r["date_ms"]), norm, str(r["type"]), str(r["duration"]))
        call_records.append({**r, "normalized_number": norm, "hash": h, "user_id": user_id})

    async with async_session_maker() as session:
        call_count = await bulk_insert_calls(session, call_records)
        await session.commit()

    return call_count


async def run_ingestion_pipeline(user_id: str) -> None:
    """Execute the full ingestion pipeline for a specific user."""
    settings = get_settings()
    country = settings.DEFAULT_COUNTRY_CODE
    
    if user_id not in _last_sync:
        _last_sync[user_id] = {"status": "never", "timestamp": None, "error": None, "stats": {}}

    try:
        _last_sync[user_id]["status"] = "running"
        await _update_db_status(user_id, "running")

        # Check if configured
        async with async_session_maker() as session:
            stmt = select(AppConfig).where(AppConfig.user_id == user_id).limit(1)
            config = (await session.execute(stmt)).scalar_one_or_none()
            if not config or not config.gdrive_sync_folder_id:
                logger.warning(f"Google Drive not connected for user {user_id}. Skipping sync.")
                _last_sync[user_id].update({
                    "status": "error",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "error": "Google Drive sync folder not configured.",
                })
                await _update_db_status(user_id, "error", error="Google Drive sync folder not configured.")
                return
                
            last_sms_modified = config.last_sms_modified
            last_calls_modified = config.last_calls_modified

        sms_count = mms_count = call_count = 0
        xml_path = None
        calls_path = None

        # --- SMS/MMS ingestion ---
        try:
            logger.info(f"Checking for new SMS/MMS backup for {user_id}...")
            xml_path, new_sms_time = await download_xml(is_calls=False, last_modified=last_sms_modified, user_id=user_id, progress_callback=make_progress_callback(user_id, "SMS"))
            
            if not xml_path:
                logger.info("SMS/MMS backup is already up to date.")
            else:
                _last_sync[user_id]["stats"]["processing"] = "SMS/MMS"
                await _update_db_status(user_id, "running", stats=_last_sync[user_id]["stats"])
                sms_count, mms_count = await ingest_sms_mms_file(xml_path, user_id)
                xml_path.unlink(missing_ok=True)
                last_sms_modified = new_sms_time
        except FileNotFoundError as e:
            logger.warning(f"Skipping SMS/MMS ingestion: {e}")

        # --- Calls ingestion ---
        try:
            logger.info(f"Checking for new Call log backup for {user_id}...")
            calls_path, new_calls_time = await download_xml(is_calls=True, last_modified=last_calls_modified, user_id=user_id, progress_callback=make_progress_callback(user_id, "Calls"))
            
            if not calls_path:
                logger.info("Call log backup is already up to date.")
            else:
                _last_sync[user_id]["stats"]["processing"] = "Calls"
                await _update_db_status(user_id, "running", stats=_last_sync[user_id]["stats"])
                call_count = await ingest_calls_file(calls_path, user_id)
                calls_path.unlink(missing_ok=True)
                last_calls_modified = new_calls_time
        except FileNotFoundError as e:
            logger.warning(f"Skipping Calls ingestion: {e}")

        stats = {"sms": sms_count, "mms": mms_count, "calls": call_count}
        _last_sync[user_id].update({
            "status": "success",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "error": None,
            "stats": stats,
        })
        
        await _update_db_status(user_id, "success", error="", stats=stats, sms_mod=last_sms_modified, calls_mod=last_calls_modified)

        logger.info(f"Pipeline complete for {user_id}: {sms_count} SMS, {mms_count} MMS, {call_count} calls")

        if config.notify_on_success and (sms_count > 0 or mms_count > 0 or call_count > 0):
            from app.services.notifier import send_notification
            import asyncio
            asyncio.create_task(send_notification(
                title="SMS Web Viewer Sync",
                body=f"Successfully synced {sms_count} SMS, {mms_count} MMS, and {call_count} calls.",
                notification_urls=config.notification_urls
            ))

    except Exception as e:
        _last_sync[user_id].update({
            "status": "error",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "error": str(e),
        })
        
        await _update_db_status(user_id, "error", error=str(e))
        
        logger.exception(f"Ingestion pipeline failed for {user_id}: {e}")
        
        if 'config' in locals() and config and getattr(config, 'notify_on_failure', False):
            from app.services.notifier import send_notification
            import asyncio
            asyncio.create_task(send_notification(
                title="SMS Web Viewer Sync Failed",
                body=f"Sync failed for user {user_id}:\n{str(e)}",
                notification_urls=getattr(config, 'notification_urls', None)
            ))
            
        raise
    finally:
        if xml_path:
            xml_path.unlink(missing_ok=True)
        if calls_path:
            calls_path.unlink(missing_ok=True)
