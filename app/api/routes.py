"""FastAPI REST API routes for the SMS Web Viewer."""

import asyncio
import aiofiles
import csv
import io
import json
import logging
import mimetypes
import zipfile
import shutil
import tempfile
import os
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, UploadFile, File, Form, BackgroundTasks
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import desc, distinct, func, or_, select, union_all
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_session
from app.core.security import get_current_user
from app.models.user import User
from app.models.call import Call
from app.models.mms import MMS, MMSPart
from app.models.sms import SMS
from app.services.pipeline import get_sync_status, run_ingestion_pipeline

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["api"])

# 4 GB upload size limit
MAX_UPLOAD_BYTES = 4 * 1024 * 1024 * 1024


# ---------------------------------------------------------------------------
# Response Schemas
# ---------------------------------------------------------------------------


class ContactResponse(BaseModel):
    normalized_address: str
    display_name: Optional[str] = None
    message_count: int
    last_message_date: Optional[int] = None


class MediaPart(BaseModel):
    id: int
    content_type: str

class MessageResponse(BaseModel):
    id: int
    source: str  # "sms" or "mms"
    type: int
    body: Optional[str] = None
    readable_date: Optional[str] = None
    date_ms: int
    contact_name: Optional[str] = None
    normalized_address: Optional[str] = None
    has_media: bool = False
    media_parts: list[MediaPart] = []


class CallResponse(BaseModel):
    id: int
    type: int
    duration: int
    readable_date: Optional[str] = None
    date_ms: int
    contact_name: Optional[str] = None


class SyncStatusResponse(BaseModel):
    status: str
    timestamp: Optional[str] = None
    error: Optional[str] = None
    stats: dict = {}


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/contacts", response_model=list[ContactResponse])
async def list_contacts(
    search: Optional[str] = Query(None),
    filter: Optional[str] = Query(None, pattern="^(all|named|unknown)$"),
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """List all contacts with message counts, sorted by most recent activity."""
    sms_sub = select(SMS.normalized_address, SMS.contact_name, SMS.date_ms).where(SMS.user_id == current_user.id)
    mms_sub = select(MMS.normalized_address, MMS.contact_name, MMS.date_ms).where(MMS.user_id == current_user.id)
    combined = union_all(sms_sub, mms_sub).subquery()

    stmt = (
        select(
            combined.c.normalized_address,
            func.max(combined.c.contact_name).label("display_name"),
            func.count().label("message_count"),
            func.max(combined.c.date_ms).label("last_message_date"),
        )
        .group_by(combined.c.normalized_address)
        .order_by(desc("last_message_date"))
    )

    if search:
        pattern = f"%{search}%"
        stmt = stmt.where(
            or_(
                combined.c.contact_name.ilike(pattern),
                combined.c.normalized_address.ilike(pattern),
            )
        )

    if filter == "named":
        stmt = stmt.having(func.max(combined.c.contact_name) != None)  # noqa: E711
        stmt = stmt.having(func.max(combined.c.contact_name) != "(Unknown)")
    elif filter == "unknown":
        stmt = stmt.having(
            or_(
                func.max(combined.c.contact_name) == None,  # noqa: E711
                func.max(combined.c.contact_name) == "(Unknown)",
            )
        )

    result = await session.execute(stmt)
    return [
        ContactResponse(
            normalized_address=r.normalized_address,
            display_name=r.display_name,
            message_count=r.message_count,
            last_message_date=r.last_message_date,
        )
        for r in result.all()
    ]


@router.get(
    "/conversations/{normalized_address}", response_model=list[MessageResponse]
)
async def get_conversation(
    normalized_address: str,
    search: Optional[str] = Query(None),
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Get all messages for a contact, chronologically sorted."""
    sms_stmt = select(SMS).where(
        SMS.user_id == current_user.id,
        SMS.normalized_address == normalized_address
    ).order_by(SMS.date_ms)
    
    if search:
        sms_stmt = sms_stmt.where(SMS.body.ilike(f"%{search}%"))
    sms_results = (await session.execute(sms_stmt)).scalars().all()

    mms_stmt = select(MMS).options(selectinload(MMS.parts)).where(
        MMS.user_id == current_user.id,
        MMS.normalized_address == normalized_address
    ).order_by(MMS.date_ms)
    
    if search:
        mms_stmt = mms_stmt.where(MMS.body.ilike(f"%{search}%"))
    mms_results = (await session.execute(mms_stmt)).scalars().all()

    messages: list[MessageResponse] = []
    for s in sms_results:
        messages.append(
            MessageResponse(
                id=s.id, source="sms", type=s.type, body=s.body,
                readable_date=s.readable_date, date_ms=s.date_ms,
                contact_name=s.contact_name, normalized_address=s.normalized_address,
                has_media=False,
            )
        )
    for m in mms_results:
        messages.append(
            MessageResponse(
                id=m.id, source="mms", type=m.msg_box, body=m.body,
                readable_date=m.readable_date, date_ms=m.date_ms,
                contact_name=m.contact_name, normalized_address=m.normalized_address,
                has_media=bool(m.parts),
                media_parts=[{"id": p.id, "content_type": p.content_type} for p in m.parts if p.data]
            )
        )

    messages.sort(key=lambda m: m.date_ms)
    return messages


@router.get("/search/global", response_model=list[MessageResponse])
async def global_search(
    q: str = Query(..., min_length=1, max_length=500),
    limit: int = Query(50, ge=1, le=500),
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Full-text search across all SMS and MMS messages."""
    pattern = f"%{q}%"

    sms_stmt = (
        select(SMS)
        .where(SMS.user_id == current_user.id, SMS.body.ilike(pattern))
        .order_by(desc(SMS.date_ms))
        .limit(limit)
    )
    
    mms_stmt = (
        select(MMS)
        .options(selectinload(MMS.parts))
        .where(MMS.user_id == current_user.id, MMS.body.ilike(pattern))
        .order_by(desc(MMS.date_ms))
        .limit(limit)
    )

    sms_results = (await session.execute(sms_stmt)).scalars().all()
    mms_results = (await session.execute(mms_stmt)).scalars().all()

    messages: list[MessageResponse] = []
    for s in sms_results:
        messages.append(
            MessageResponse(
                id=s.id, source="sms", type=s.type, body=s.body,
                readable_date=s.readable_date, date_ms=s.date_ms,
                contact_name=s.contact_name, normalized_address=s.normalized_address,
                has_media=False,
            )
        )
    for m in mms_results:
        messages.append(
            MessageResponse(
                id=m.id, source="mms", type=m.msg_box, body=m.body,
                readable_date=m.readable_date, date_ms=m.date_ms,
                contact_name=m.contact_name, normalized_address=m.normalized_address,
                has_media=bool(m.parts),
                media_parts=[{"id": p.id, "content_type": p.content_type} for p in m.parts if p.data]
            )
        )

    messages.sort(key=lambda m: m.date_ms, reverse=True)
    return messages[:limit]


@router.get("/calls/{normalized_address}", response_model=list[CallResponse])
async def get_calls(
    normalized_address: str,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Get call log for a contact."""
    stmt = (
        select(Call)
        .where(Call.user_id == current_user.id, Call.normalized_number == normalized_address)
        .order_by(Call.date_ms)
    )
    results = (await session.execute(stmt)).scalars().all()
    return [
        CallResponse(
            id=c.id, type=c.type, duration=c.duration,
            readable_date=c.readable_date, date_ms=c.date_ms,
            contact_name=c.contact_name,
        )
        for c in results
    ]


@router.get("/stats")
async def get_stats(
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Global statistics."""
    sms_count = (await session.execute(select(func.count(SMS.id)).where(SMS.user_id == current_user.id))).scalar() or 0
    mms_count = (await session.execute(select(func.count(MMS.id)).where(MMS.user_id == current_user.id))).scalar() or 0
    call_count = (await session.execute(select(func.count(Call.id)).where(Call.user_id == current_user.id))).scalar() or 0
    contact_count = (await session.execute(select(func.count(distinct(SMS.normalized_address))).where(SMS.user_id == current_user.id))).scalar() or 0

    return {
        "total_sms": sms_count,
        "total_mms": mms_count,
        "total_calls": call_count,
        "total_contacts": contact_count,
    }


@router.get("/mms/{mms_id}/media/{part_id}")
async def get_mms_media(
    mms_id: int,
    part_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Serve MMS media attachment from the database."""
    stmt = select(MMSPart).join(MMS).where(
        MMSPart.id == part_id, MMSPart.mms_id == mms_id, MMS.user_id == current_user.id
    )
    part = (await session.execute(stmt)).scalar_one_or_none()
    if not part or not part.data:
        raise HTTPException(status_code=404, detail="Media not found")
    return Response(content=part.data, media_type=part.content_type)


@router.get("/export/csv/{normalized_address}")
async def export_csv(
    normalized_address: str,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Export conversation as CSV download (SMS + MMS)."""
    sms_stmt = (
        select(SMS)
        .where(SMS.user_id == current_user.id, SMS.normalized_address == normalized_address)
        .order_by(SMS.date_ms)
    )
    sms_results = (await session.execute(sms_stmt)).scalars().all()

    mms_stmt = (
        select(MMS)
        .where(MMS.user_id == current_user.id, MMS.normalized_address == normalized_address)
        .order_by(MMS.date_ms)
    )
    mms_results = (await session.execute(mms_stmt)).scalars().all()

    # Merge and sort by timestamp
    rows = []
    for msg in sms_results:
        rows.append({
            "date_ms": msg.date_ms,
            "name": msg.contact_name or "Unknown",
            "phone": normalized_address,
            "date": msg.readable_date,
            "type": "Received" if msg.type == 1 else "Sent",
            "message": msg.body or "",
            "source": "SMS",
        })
    for msg in mms_results:
        rows.append({
            "date_ms": msg.date_ms,
            "name": msg.contact_name or "Unknown",
            "phone": normalized_address,
            "date": msg.readable_date,
            "type": "Received" if msg.msg_box == 1 else "Sent",
            "message": msg.body or "[Media]",
            "source": "MMS",
        })
    rows.sort(key=lambda r: r["date_ms"])

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Name", "Phone", "Date", "Type", "Source", "Message"])
    for row in rows:
        writer.writerow([row["name"], row["phone"], row["date"], row["type"], row["source"], row["message"]])

    logger.info(f"User {current_user.username} initiated CSV export for contact {normalized_address}")

    return Response(
        content=output.getvalue(), media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="conversation_{normalized_address}.csv"'},
    )


@router.get("/export/json/{normalized_address}")
async def export_json(
    normalized_address: str,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Export conversation as JSON download (SMS + MMS)."""
    sms_stmt = (
        select(SMS)
        .where(SMS.user_id == current_user.id, SMS.normalized_address == normalized_address)
        .order_by(SMS.date_ms)
    )
    sms_results = (await session.execute(sms_stmt)).scalars().all()

    mms_stmt = (
        select(MMS)
        .where(MMS.user_id == current_user.id, MMS.normalized_address == normalized_address)
        .order_by(MMS.date_ms)
    )
    mms_results = (await session.execute(mms_stmt)).scalars().all()

    data = []
    for msg in sms_results:
        data.append({
            "date_ms": msg.date_ms,
            "name": msg.contact_name,
            "phone": normalized_address,
            "date": msg.readable_date,
            "type": msg.type,
            "source": "sms",
            "body": msg.body,
        })
    for msg in mms_results:
        data.append({
            "date_ms": msg.date_ms,
            "name": msg.contact_name,
            "phone": normalized_address,
            "date": msg.readable_date,
            "type": msg.msg_box,
            "source": "mms",
            "body": msg.body,
        })
    data.sort(key=lambda r: r["date_ms"])
    # Remove internal sort key from output
    for r in data:
        del r["date_ms"]

    logger.info(f"User {current_user.username} initiated JSON export for contact {normalized_address}")

    return Response(
        content=json.dumps(data, indent=2), media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="conversation_{normalized_address}.json"'},
    )


@router.get("/export/media/{normalized_address}")
async def export_media(
    normalized_address: str,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Export all media attachments for a conversation as a ZIP file."""
    # Query only the MMSPart and the dates directly to avoid loading entire MMS objects
    stmt = (
        select(MMSPart, MMS.readable_date, MMS.date_ms)
        .join(MMS)
        .where(MMS.user_id == current_user.id, MMS.normalized_address == normalized_address)
        .where(MMSPart.data.isnot(None))
        .order_by(MMS.date_ms)
    )
    
    # Use yield_per to stream results from the database, preventing OOM
    results = await session.stream(stmt.execution_options(yield_per=100))

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".zip")
    tmp_name = tmp.name
    count = 0

    try:
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zf:
            async for part, readable_date, date_ms in results:
                ext = mimetypes.guess_extension(part.content_type) or ".bin"
                if ext == ".jpe": ext = ".jpg"
                date_str = (readable_date or f"ts_{date_ms}").replace(":", "-").replace(" ", "_").replace("/", "-")
                filename = f"{date_str}_{part.id}{ext}"
                zf.writestr(filename, part.data)
                count += 1
    except Exception as e:
        tmp.close()
        os.unlink(tmp_name)
        raise e
        
    tmp.close()
    
    if count == 0:
        os.unlink(tmp_name)
        raise HTTPException(status_code=404, detail="No media attachments found for this contact.")

    # Clean up the temp file after the response is sent
    background_tasks.add_task(os.unlink, tmp_name)
    
    logger.info(f"User {current_user.username} initiated Media ZIP export for contact {normalized_address} ({count} attachments)")
    
    return FileResponse(
        path=tmp_name,
        media_type="application/zip",
        filename=f'media_{normalized_address}.zip'
    )


@router.post("/sync")
async def trigger_sync(current_user: User = Depends(get_current_user)):
    """Manually trigger the ingestion pipeline (runs in background)."""
    asyncio.create_task(run_ingestion_pipeline(current_user.id))
    return {"message": "Sync started", "status": "running"}


@router.get("/sync/status", response_model=SyncStatusResponse)
async def get_sync_status_endpoint(current_user: User = Depends(get_current_user)):
    """Get the current sync status for the current user."""
    return await get_sync_status(current_user.id)


@router.post("/upload")
async def upload_xml(
    request: Request,
    file: UploadFile = File(...),
    file_type: str = Form(...),
    current_user: User = Depends(get_current_user)
):
    """Manually upload and ingest an XML backup. Maximum file size: 4 GB."""
    # Enforce 4 GB size limit by streaming in chunks
    temp_path = Path(f"/tmp/manual_upload_{current_user.id}_{file.filename}")
    bytes_written = 0
    chunk_size = 1024 * 1024  # 1 MB chunks

    try:
        async with aiofiles.open(temp_path, "wb") as buffer:
            while True:
                chunk = await file.read(chunk_size)
                if not chunk:
                    break
                bytes_written += len(chunk)
                if bytes_written > MAX_UPLOAD_BYTES:
                    raise HTTPException(
                        status_code=413,
                        detail=f"File too large. Maximum upload size is {MAX_UPLOAD_BYTES // (1024**3)} GB."
                    )
                await buffer.write(chunk)

        from app.services.pipeline import ingest_sms_mms_file, ingest_calls_file
        if file_type == "calls":
            call_count = await ingest_calls_file(temp_path, current_user.id)
            logger.info(f"User {current_user.username} manually uploaded a Calls XML backup ({call_count} calls).")
            return {"message": "Calls ingested successfully", "calls": call_count}
        else:
            sms_count, mms_count = await ingest_sms_mms_file(temp_path, current_user.id)
            logger.info(f"User {current_user.username} manually uploaded an SMS/MMS XML backup ({sms_count} SMS, {mms_count} MMS).")
            return {"message": "SMS/MMS ingested successfully", "sms": sms_count, "mms": mms_count}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Manual upload ingestion failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        temp_path.unlink(missing_ok=True)
