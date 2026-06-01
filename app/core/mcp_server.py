"""Model Context Protocol (MCP) server with tools for AI agent access."""

import json
import logging
import os
import contextvars
from datetime import datetime

from mcp.server.fastmcp import FastMCP, Image
from sqlalchemy import func, or_, select
from sqlalchemy.orm import selectinload

from app.core.database import async_session_maker
from app.models.call import Call
from app.models.mms import MMS, MMSPart
from app.models.sms import SMS

logger = logging.getLogger(__name__)

mcp = FastMCP("SMS Viewer")

# Context variables populated by the FastAPI route
mcp_user_id = contextvars.ContextVar("mcp_user_id", default=None)
mcp_is_global = contextvars.ContextVar("mcp_is_global", default=False)

def apply_tenant_filter(stmt, model):
    """Applies the tenant user_id filter if the token is not global."""
    if mcp_is_global.get():
        return stmt
    
    uid = mcp_user_id.get()
    if not uid:
        raise ValueError("MCP Context Error: No user_id found and token is not global.")
        
    return stmt.where(model.user_id == uid)


@mcp.tool()
async def query_contacts(search: str) -> list[dict]:
    """Look up contacts by name or normalized phone number. Search string must be 1-200 characters."""
    if not search or len(search) > 200:
        return [{"error": "Search string must be between 1 and 200 characters."}]
    async with async_session_maker() as session:
        pattern = f"%{search}%"
        stmt = (
            select(
                SMS.normalized_address,
                SMS.contact_name,
                func.count(SMS.id).label("message_count"),
            )
            .where(
                or_(
                    SMS.contact_name.ilike(pattern),
                    SMS.normalized_address.ilike(pattern),
                    SMS.address.ilike(pattern),
                )
            )
        )
        stmt = apply_tenant_filter(stmt, SMS)
        stmt = stmt.group_by(SMS.normalized_address, SMS.contact_name).limit(50)
        
        result = await session.execute(stmt)
        return [
            {
                "normalized_address": r.normalized_address,
                "contact_name": r.contact_name,
                "message_count": r.message_count,
            }
            for r in result.all()
        ]


@mcp.tool()
async def search_messages(query: str, limit: int = 50) -> list[dict]:
    """Full-text search across all SMS and MMS messages. Query must be 1-500 characters."""
    if not query or len(query) > 500:
        return [{"error": "Search query must be between 1 and 500 characters."}]
    async with async_session_maker() as session:
        pattern = f"%{query}%"

        sms_stmt = (
            select(
                SMS.normalized_address,
                SMS.contact_name,
                SMS.body,
                SMS.readable_date,
                SMS.type,
            )
            .where(SMS.body.ilike(pattern))
            .order_by(SMS.date_ms.desc())
            .limit(limit)
        )
        sms_stmt = apply_tenant_filter(sms_stmt, SMS)
        
        mms_stmt = (
            select(
                MMS.normalized_address,
                MMS.contact_name,
                MMS.body,
                MMS.readable_date,
                MMS.msg_box,
            )
            .where(MMS.body.ilike(pattern))
            .order_by(MMS.date_ms.desc())
            .limit(limit)
        )
        mms_stmt = apply_tenant_filter(mms_stmt, MMS)

        sms_results = (await session.execute(sms_stmt)).all()
        mms_results = (await session.execute(mms_stmt)).all()

        results = []
        for r in sms_results:
            results.append(
                {
                    "type": "sms",
                    "address": r.normalized_address,
                    "contact": r.contact_name,
                    "body": r.body,
                    "date": r.readable_date,
                    "direction": "received" if r.type == 1 else "sent",
                }
            )
        for r in mms_results:
            results.append(
                {
                    "type": "mms",
                    "address": r.normalized_address,
                    "contact": r.contact_name,
                    "body": r.body,
                    "date": r.readable_date,
                    "direction": "received" if r.msg_box == 1 else "sent",
                }
            )
        return results[:limit]


@mcp.tool()
async def get_conversation_context(
    normalized_number: str, last_n: int = 20
) -> list[dict]:
    """Retrieve the last N messages with a specific number. 
    If a message contains media, it will list the attachment IDs which can be retrieved using the get_media_attachment tool.
    """
    async with async_session_maker() as session:
        # Fetch SMS
        sms_stmt = (
            select(SMS)
            .where(SMS.normalized_address == normalized_number)
            .order_by(SMS.date_ms.desc())
            .limit(last_n)
        )
        sms_stmt = apply_tenant_filter(sms_stmt, SMS)
        sms_results = (await session.execute(sms_stmt)).scalars().all()
        
        # Fetch MMS
        mms_stmt = (
            select(MMS)
            .options(selectinload(MMS.parts))
            .where(MMS.normalized_address == normalized_number)
            .order_by(MMS.date_ms.desc())
            .limit(last_n)
        )
        mms_stmt = apply_tenant_filter(mms_stmt, MMS)
        mms_results = (await session.execute(mms_stmt)).scalars().all()

        combined = []
        for r in sms_results:
            combined.append({
                "type": "sms",
                "body": r.body,
                "date": r.readable_date,
                "direction": "received" if r.type == 1 else "sent",
                "date_ms": r.date_ms,
            })
            
        for r in mms_results:
            attachments = []
            for p in r.parts:
                if p.data:
                    attachments.append({
                        "mms_id": r.id,
                        "part_id": p.id,
                        "content_type": p.content_type
                    })
            
            combined.append({
                "type": "mms",
                "body": r.body,
                "date": r.readable_date,
                "direction": "received" if r.msg_box == 1 else "sent",
                "date_ms": r.date_ms,
                "attachments": attachments
            })
            
        combined.sort(key=lambda x: x["date_ms"], reverse=True)
        results = combined[:last_n]
        return list(reversed(results))

@mcp.tool()
async def get_media_attachment(mms_id: int, part_id: int):
    """Fetch an image or media attachment from an MMS message using IDs returned by get_conversation_context."""
    async with async_session_maker() as session:
        # Must join with MMS to verify ownership
        stmt = select(MMSPart).join(MMS).where(MMSPart.id == part_id, MMSPart.mms_id == mms_id)
        stmt = apply_tenant_filter(stmt, MMS)
        part = (await session.execute(stmt)).scalar_one_or_none()
        
        if not part or not part.data:
            return f"Media part {part_id} for MMS {mms_id} not found."
            
        if part.content_type.startswith("image/"):
            fmt = part.content_type.split("/")[-1]
            return Image(data=part.data, format=fmt)
        else:
            return f"[Media Attachment: {part.content_type}] Audio or video cannot be viewed natively via MCP Image tool. Text preview: {part.text or 'None'}"


@mcp.tool()
async def get_call_stats(normalized_number: str) -> dict:
    """Summarize call history (duration, missed vs. answered) for a specific number."""
    async with async_session_maker() as session:
        stmt = select(Call).where(Call.normalized_number == normalized_number)
        stmt = apply_tenant_filter(stmt, Call)
        results = (await session.execute(stmt)).scalars().all()

        total = len(results)
        incoming = sum(1 for c in results if c.type == 1)
        outgoing = sum(1 for c in results if c.type == 2)
        missed = sum(1 for c in results if c.type == 3)
        total_duration = sum(c.duration for c in results)
        avg_duration = total_duration / total if total > 0 else 0

        return {
            "normalized_number": normalized_number,
            "total_calls": total,
            "incoming": incoming,
            "outgoing": outgoing,
            "missed": missed,
            "total_duration_seconds": total_duration,
            "average_duration_seconds": round(avg_duration, 1),
        }

@mcp.tool()
async def get_recent_active_contacts(limit: int = 10) -> list[dict]:
    """Return the most recently active contacts/conversations."""
    async with async_session_maker() as session:
        stmt = (
            select(
                SMS.normalized_address,
                SMS.contact_name,
                func.max(SMS.date_ms).label("last_active")
            )
        )
        stmt = apply_tenant_filter(stmt, SMS)
        stmt = (
            stmt.group_by(SMS.normalized_address, SMS.contact_name)
            .order_by(func.max(SMS.date_ms).desc())
            .limit(limit)
        )
        results = (await session.execute(stmt)).all()
        return [
            {
                "normalized_address": r.normalized_address,
                "contact_name": r.contact_name,
                "last_active_ms": r.last_active,
                "last_active_date": datetime.fromtimestamp(r.last_active / 1000).strftime("%Y-%m-%d %H:%M:%S") if r.last_active else None
            }
            for r in results
        ]

@mcp.tool()
async def get_messages_by_date_range(
    normalized_number: str, start_date_iso: str, end_date_iso: str
) -> list[dict]:
    """Retrieve messages with a specific number within a date range. Dates should be ISO format (e.g. 2024-01-01T00:00:00)."""
    try:
        start_dt = datetime.fromisoformat(start_date_iso.replace("Z", "+00:00"))
        end_dt = datetime.fromisoformat(end_date_iso.replace("Z", "+00:00"))
        start_ms = int(start_dt.timestamp() * 1000)
        end_ms = int(end_dt.timestamp() * 1000)
    except ValueError as e:
        return [{"error": f"Invalid date format. Use ISO format. Details: {str(e)}"}]

    async with async_session_maker() as session:
        sms_stmt = (
            select(SMS)
            .where(SMS.normalized_address == normalized_number)
            .where(SMS.date_ms >= start_ms)
            .where(SMS.date_ms <= end_ms)
        )
        sms_stmt = apply_tenant_filter(sms_stmt, SMS)
        sms_results = (await session.execute(sms_stmt)).scalars().all()
        
        mms_stmt = (
            select(MMS)
            .options(selectinload(MMS.parts))
            .where(MMS.normalized_address == normalized_number)
            .where(MMS.date_ms >= start_ms)
            .where(MMS.date_ms <= end_ms)
        )
        mms_stmt = apply_tenant_filter(mms_stmt, MMS)
        mms_results = (await session.execute(mms_stmt)).scalars().all()

        combined = []
        for r in sms_results:
            combined.append({
                "type": "sms",
                "body": r.body,
                "date": r.readable_date,
                "direction": "received" if r.type == 1 else "sent",
                "date_ms": r.date_ms,
            })
            
        for r in mms_results:
            attachments = []
            for p in r.parts:
                if p.data:
                    attachments.append({
                        "mms_id": r.id,
                        "part_id": p.id,
                        "content_type": p.content_type
                    })
            
            combined.append({
                "type": "mms",
                "body": r.body,
                "date": r.readable_date,
                "direction": "received" if r.msg_box == 1 else "sent",
                "date_ms": r.date_ms,
                "attachments": attachments
            })
            
        combined.sort(key=lambda x: x["date_ms"])
        return combined

@mcp.tool()
async def get_database_stats() -> dict:
    """Get high-level statistics about the message database and sync state."""
    async with async_session_maker() as session:
        total_sms = (await session.execute(apply_tenant_filter(select(func.count(SMS.id)), SMS))).scalar()
        total_mms = (await session.execute(apply_tenant_filter(select(func.count(MMS.id)), MMS))).scalar()
        total_calls = (await session.execute(apply_tenant_filter(select(func.count(Call.id)), Call))).scalar()
        
        first_sms_ms = (await session.execute(apply_tenant_filter(select(func.min(SMS.date_ms)), SMS))).scalar()
        last_sms_ms = (await session.execute(apply_tenant_filter(select(func.max(SMS.date_ms)), SMS))).scalar()

        sync_state = "Never synced"
        if mcp_is_global.get():
            sync_state = "Global mode - check individual user sync status"
        else:
            from app.services.pipeline import get_sync_status
            s = await get_sync_status(mcp_user_id.get())
            if s.get("timestamp"):
                sync_state = f"Synced at {s['timestamp']} ({s['status']})"

        return {
            "total_sms": total_sms,
            "total_mms": total_mms,
            "total_calls": total_calls,
            "first_message_date": datetime.fromtimestamp(first_sms_ms / 1000).strftime("%Y-%m-%d %H:%M:%S") if first_sms_ms else None,
            "last_message_date": datetime.fromtimestamp(last_sms_ms / 1000).strftime("%Y-%m-%d %H:%M:%S") if last_sms_ms else None,
            "sync_status": sync_state
        }

@mcp.tool()
async def get_conversation_text(normalized_number: str, days: int = 30) -> str:
    """Retrieve the raw text of the conversation over the last X days. 
    Useful for feeding into an LLM to generate summaries of the conversation."""
    try:
        now_ms = int(datetime.now().timestamp() * 1000)
        start_ms = now_ms - (days * 24 * 60 * 60 * 1000)
    except Exception:
        start_ms = 0

    async with async_session_maker() as session:
        sms_stmt = (
            select(SMS)
            .where(SMS.normalized_address == normalized_number)
            .where(SMS.date_ms >= start_ms)
        )
        sms_stmt = apply_tenant_filter(sms_stmt, SMS)
        
        mms_stmt = (
            select(MMS)
            .where(MMS.normalized_address == normalized_number)
            .where(MMS.date_ms >= start_ms)
        )
        mms_stmt = apply_tenant_filter(mms_stmt, MMS)
        
        sms_results = (await session.execute(sms_stmt)).scalars().all()
        mms_results = (await session.execute(mms_stmt)).scalars().all()
        
        combined = []
        for r in sms_results:
            combined.append({
                "body": r.body,
                "date_ms": r.date_ms,
                "readable_date": r.readable_date,
                "is_me": r.type != 1,
                "contact_name": r.contact_name or r.normalized_address
            })
        for r in mms_results:
            combined.append({
                "body": r.body,
                "date_ms": r.date_ms,
                "readable_date": r.readable_date,
                "is_me": r.msg_box != 1,
                "contact_name": r.contact_name or r.normalized_address
            })
            
        if not combined:
            return f"No messages found in the last {days} days."
            
        combined.sort(key=lambda x: x["date_ms"])
        
        lines = []
        for c in combined:
            speaker = "Me" if c["is_me"] else c["contact_name"]
            body = c["body"] or "[Media/Empty]"
            lines.append(f"[{c['readable_date']}] {speaker}: {body}")
            
        return "\n".join(lines)


@mcp.tool()
async def get_communication_frequency(normalized_number: str) -> dict:
    """Return a breakdown of message volume per month for a contact."""
    from datetime import datetime
    async with async_session_maker() as session:
        # Fetch all messages with timestamps and compute month grouping in Python
        # (avoids SQLite-specific strftime which breaks on PostgreSQL)
        sms_stmt = select(SMS.date_ms).where(SMS.normalized_address == normalized_number)
        sms_stmt = apply_tenant_filter(sms_stmt, SMS)
        
        mms_stmt = select(MMS.date_ms).where(MMS.normalized_address == normalized_number)
        mms_stmt = apply_tenant_filter(mms_stmt, MMS)
        
        sms_dates = (await session.execute(sms_stmt)).scalars().all()
        mms_dates = (await session.execute(mms_stmt)).scalars().all()

    freq: dict[str, int] = {}
    for date_ms in sms_dates:
        if date_ms:
            month = datetime.fromtimestamp(date_ms / 1000).strftime("%Y-%m")
            freq[month] = freq.get(month, 0) + 1
    for date_ms in mms_dates:
        if date_ms:
            month = datetime.fromtimestamp(date_ms / 1000).strftime("%Y-%m")
            freq[month] = freq.get(month, 0) + 1

    sorted_freq = dict(sorted(freq.items()))
    return {
        "normalized_number": normalized_number,
        "monthly_message_count": sorted_freq
    }

_background_tasks = set()

@mcp.tool()
async def trigger_background_sync() -> str:
    """Triggers an immediate background sync with Google Drive to pull the latest backups."""
    from app.services.pipeline import run_ingestion_pipeline
    import asyncio
    
    uid = mcp_user_id.get()
    if not uid:
        return "Error: Cannot trigger background sync with a global token. A user token is required."
        
    task = asyncio.create_task(run_ingestion_pipeline(uid))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    
    return "Background sync pipeline has been triggered. Please wait a few minutes for it to complete, and then query the database or use get_database_stats to check the sync_status."
