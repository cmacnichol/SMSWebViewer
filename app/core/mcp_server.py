"""Model Context Protocol (MCP) server with tools for AI agent access."""

import json
import logging
import os
from datetime import datetime

from mcp.server.fastmcp import FastMCP, Image
from sqlalchemy import func, or_, select

from app.core.database import async_session_maker
from app.models.call import Call
from app.models.mms import MMS, MMSPart
from sqlalchemy.orm import selectinload
from app.models.sms import SMS

logger = logging.getLogger(__name__)

mcp = FastMCP("SMS Viewer")


@mcp.tool()
async def query_contacts(search: str) -> list[dict]:
    """Look up contacts by name or normalized phone number."""
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
            .group_by(SMS.normalized_address, SMS.contact_name)
            .limit(50)
        )
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
    """Full-text search across all SMS and MMS messages."""
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
        sms_results = (await session.execute(sms_stmt)).scalars().all()
        
        # Fetch MMS
        mms_stmt = (
            select(MMS)
            .options(selectinload(MMS.parts))
            .where(MMS.normalized_address == normalized_number)
            .order_by(MMS.date_ms.desc())
            .limit(last_n)
        )
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
        stmt = select(MMSPart).where(MMSPart.id == part_id, MMSPart.mms_id == mms_id)
        part = (await session.execute(stmt)).scalar_one_or_none()
        
        if not part or not part.data:
            return f"Media part {part_id} for MMS {mms_id} not found."
            
        if part.content_type.startswith("image/"):
            # Format usually jpeg, png, etc.
            fmt = part.content_type.split("/")[-1]
            return Image(data=part.data, format=fmt)
        else:
            return f"[Media Attachment: {part.content_type}] Audio or video cannot be viewed natively via MCP Image tool. Text preview: {part.text or 'None'}"


@mcp.tool()
async def get_call_stats(normalized_number: str) -> dict:
    """Summarize call history (duration, missed vs. answered) for a specific number."""
    async with async_session_maker() as session:
        stmt = select(Call).where(Call.normalized_number == normalized_number)
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
            .group_by(SMS.normalized_address, SMS.contact_name)
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
        sms_results = (await session.execute(sms_stmt)).scalars().all()
        
        mms_stmt = (
            select(MMS)
            .options(selectinload(MMS.parts))
            .where(MMS.normalized_address == normalized_number)
            .where(MMS.date_ms >= start_ms)
            .where(MMS.date_ms <= end_ms)
        )
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
        total_sms = (await session.execute(select(func.count(SMS.id)))).scalar()
        total_mms = (await session.execute(select(func.count(MMS.id)))).scalar()
        total_calls = (await session.execute(select(func.count(Call.id)))).scalar()
        
        first_sms_ms = (await session.execute(select(func.min(SMS.date_ms)))).scalar()
        last_sms_ms = (await session.execute(select(func.max(SMS.date_ms)))).scalar()

        sync_state = "Never synced"
        try:
            if os.path.exists("/data/sync_state.json"):
                with open("/data/sync_state.json", "r") as f:
                    state = json.load(f)
                    sync_state = f"Synced at {datetime.fromtimestamp(state.get('last_sync_time', 0)).strftime('%Y-%m-%d %H:%M:%S')}"
        except Exception:
            pass

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
        mms_stmt = (
            select(MMS)
            .where(MMS.normalized_address == normalized_number)
            .where(MMS.date_ms >= start_ms)
        )
        
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
    async with async_session_maker() as session:
        # We can group by month using sqlite strftime
        stmt_sms = select(
            func.strftime('%Y-%m', func.datetime(SMS.date_ms / 1000, 'unixepoch')).label('month'),
            func.count(SMS.id).label('count')
        ).where(SMS.normalized_address == normalized_number).group_by('month')
        
        stmt_mms = select(
            func.strftime('%Y-%m', func.datetime(MMS.date_ms / 1000, 'unixepoch')).label('month'),
            func.count(MMS.id).label('count')
        ).where(MMS.normalized_address == normalized_number).group_by('month')
        
        sms_res = (await session.execute(stmt_sms)).all()
        mms_res = (await session.execute(stmt_mms)).all()
        
        freq = {}
        for r in sms_res:
            freq[r.month] = freq.get(r.month, 0) + r.count
        for r in mms_res:
            freq[r.month] = freq.get(r.month, 0) + r.count
            
        # Sort chronologically
        sorted_freq = dict(sorted(freq.items()))
        return {
            "normalized_number": normalized_number,
            "monthly_message_count": sorted_freq
        }

@mcp.tool()
async def trigger_background_sync() -> str:
    """Triggers an immediate background sync with Google Drive to pull the latest backups."""
    from app.services.pipeline import trigger_sync_pipeline
    import asyncio
    
    asyncio.create_task(trigger_sync_pipeline())
    return "Background sync pipeline has been triggered. Please wait a few minutes for it to complete, and then query the database or use get_database_stats to check the sync_status."
