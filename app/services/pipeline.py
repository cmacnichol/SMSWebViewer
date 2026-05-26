"""Ingestion pipeline orchestrator: Google Drive -> XML -> Normalize -> DB."""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from app.core.config import get_settings
from app.core.database import async_session_maker
from app.services.dedup import bulk_insert_calls, bulk_insert_mms, bulk_insert_sms
from app.services.gdrive import download_xml
from app.services.normalization import compute_hash, normalize_phone
from app.services.xml_parser import parse_calls_xml, parse_sms_mms_xml

logger = logging.getLogger(__name__)

STATE_FILE = Path("/data/sync_state.json")

def _load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            pass
    return {}

def _save_state(state: dict):
    STATE_FILE.write_text(json.dumps(state))

# In-process sync state (no Redis needed)
_last_sync: dict = {
    "status": "never",
    "timestamp": None,
    "error": None,
    "stats": {},
}


def get_sync_status() -> dict:
    """Return a copy of the current sync status."""
    if _last_sync["status"] == "running":
        return _last_sync.copy()
        
    state = _load_state()
    if "last_sync_info" in state:
        return state["last_sync_info"]
        
    return _last_sync.copy()


async def ingest_sms_mms_file(xml_path: Path) -> tuple[int, int]:
    """Ingest a local SMS/MMS XML file and return (sms_count, mms_count)."""
    settings = get_settings()
    country = settings.DEFAULT_COUNTRY_CODE
    sms_raw, mms_raw = parse_sms_mms_xml(xml_path)

    # Normalize + hash SMS
    sms_records = []
    for r in sms_raw:
        norm = normalize_phone(r["address"], country)
        h = compute_hash(
            str(r["date_ms"]), norm, str(r["type"]), r.get("body", "")
        )
        sms_records.append({**r, "normalized_address": norm, "hash": h})

    # Normalize + hash MMS (extract _parts separately)
    mms_records = []
    mms_parts_map: list[tuple[str, list[dict]]] = []
    for r in mms_raw:
        norm = normalize_phone(r["address"], country)
        h = compute_hash(
            str(r["date_ms"]),
            norm,
            str(r["msg_box"]),
            r.get("body", ""),
        )
        parts = r.pop("_parts", [])
        mms_records.append({**r, "normalized_address": norm, "hash": h})
        mms_parts_map.append((h, parts))

    async with async_session_maker() as session:
        sms_count = await bulk_insert_sms(session, sms_records)
        mms_count = await bulk_insert_mms(session, mms_records, mms_parts_map)
        await session.commit()

    return sms_count, mms_count


async def ingest_calls_file(xml_path: Path) -> int:
    """Ingest a local Calls XML file and return call_count."""
    settings = get_settings()
    country = settings.DEFAULT_COUNTRY_CODE
    calls_raw = parse_calls_xml(xml_path)

    call_records = []
    for r in calls_raw:
        norm = normalize_phone(r["number"], country)
        h = compute_hash(
            str(r["date_ms"]),
            norm,
            str(r["type"]),
            str(r["duration"]),
        )
        call_records.append({**r, "normalized_number": norm, "hash": h})

    async with async_session_maker() as session:
        call_count = await bulk_insert_calls(session, call_records)
        await session.commit()

    return call_count


async def run_ingestion_pipeline() -> None:
    """Execute the full ingestion pipeline.

    1. Download XML from Google Drive
    2. Parse SMS/MMS and/or Calls
    3. Normalize phone numbers + generate dedup hashes
    4. Bulk upsert into the database
    """
    settings = get_settings()
    country = settings.DEFAULT_COUNTRY_CODE

    try:
        _last_sync["status"] = "running"

        from sqlalchemy import select
        from app.models.config import AppConfig

        # Check if configured
        async with async_session_maker() as session:
            stmt = select(AppConfig).where(AppConfig.id == 1)
            config = (await session.execute(stmt)).scalar_one_or_none()
            if not config or not config.gdrive_sync_folder_id:
                logger.warning("Google Drive not connected or folder not selected. Skipping sync.")
                _last_sync.update({
                    "status": "error",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "error": "Google Drive sync folder not configured.",
                })
                return

        sms_count = mms_count = call_count = 0
        state = _load_state()

        # --- SMS/MMS ingestion ---
        try:
            logger.info("Checking for new SMS/MMS backup...")
            xml_path, new_sms_time = await download_xml(is_calls=False, last_modified=state.get("last_sms_modified"))
            
            if not xml_path:
                logger.info("SMS/MMS backup is already up to date.")
            else:
                sms_count, mms_count = await ingest_sms_mms_file(xml_path)
                xml_path.unlink(missing_ok=True)
                state["last_sms_modified"] = new_sms_time
        except FileNotFoundError as e:
            logger.warning(f"Skipping SMS/MMS ingestion: {e}")

        # --- Calls ingestion ---
        try:
            logger.info("Checking for new Call log backup...")
            calls_path, new_calls_time = await download_xml(is_calls=True, last_modified=state.get("last_calls_modified"))
            
            if not calls_path:
                logger.info("Call log backup is already up to date.")
            else:
                call_count = await ingest_calls_file(calls_path)
                calls_path.unlink(missing_ok=True)
                state["last_calls_modified"] = new_calls_time
        except FileNotFoundError as e:
            logger.warning(f"Skipping Calls ingestion: {e}")

        _last_sync.update(
            {
                "status": "success",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "error": None,
                "stats": {"sms": sms_count, "mms": mms_count, "calls": call_count},
            }
        )
        state["last_sync_info"] = _last_sync.copy()
        _save_state(state)

        logger.info(
            f"Pipeline complete: {sms_count} SMS, {mms_count} MMS, {call_count} calls"
        )

    except Exception as e:
        _last_sync.update(
            {
                "status": "error",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "error": str(e),
            }
        )
        
        # Reload state to avoid overwriting recent changes, then save error state
        state = _load_state()
        state["last_sync_info"] = _last_sync.copy()
        _save_state(state)
        
        logger.exception(f"Ingestion pipeline failed: {e}")
        raise
