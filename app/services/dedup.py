"""Bulk upsert logic with ON CONFLICT DO NOTHING for deduplication."""

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sms import SMS
from app.models.mms import MMS, MMSPart
from app.models.call import Call

logger = logging.getLogger(__name__)


async def bulk_upsert(
    session: AsyncSession,
    model: Any,
    records: list[dict],
    batch_size: int = 500,
) -> int:
    """Insert records with ON CONFLICT (hash) DO NOTHING. Processes in batches."""
    if not records:
        return 0

    inserted = 0
    dialect = session.bind.dialect.name

    for i in range(0, len(records), batch_size):
        batch = records[i : i + batch_size]
        if dialect == "sqlite":
            stmt = (
                sqlite_insert(model)
                .values(batch)
                .on_conflict_do_nothing(index_elements=["hash"])
            )
        else:
            stmt = (
                pg_insert(model)
                .values(batch)
                .on_conflict_do_nothing(index_elements=["hash"])
            )
        result = await session.execute(stmt)
        inserted += result.rowcount if result.rowcount else 0

    return inserted


async def bulk_insert_sms(session: AsyncSession, records: list[dict]) -> int:
    """Insert SMS records with deduplication."""
    count = await bulk_upsert(session, SMS, records)
    logger.info(f"Inserted {count} new SMS records (of {len(records)} total)")
    return count


async def bulk_insert_mms(
    session: AsyncSession,
    records: list[dict],
    parts_map: list[tuple[str, list[dict]]] | None = None,
) -> int:
    """Insert MMS records with deduplication, then insert associated parts."""
    count = await bulk_upsert(session, MMS, records)
    logger.info(f"Inserted {count} new MMS records (of {len(records)} total)")

    # Insert parts for newly-inserted MMS records
    if parts_map and count > 0:
        parts_inserted = 0
        for mms_hash, parts in parts_map:
            if not parts:
                continue
            # Look up the MMS id by hash
            result = await session.execute(
                select(MMS.id).where(MMS.hash == mms_hash)
            )
            mms_id = result.scalar_one_or_none()
            if mms_id is None:
                continue  # was a duplicate, skip parts
            for part in parts:
                part_record = MMSPart(
                    mms_id=mms_id,
                    seq=part.get("seq", 0),
                    content_type=part.get("content_type", "application/octet-stream"),
                    name=part.get("name"),
                    text=part.get("text"),
                    data=part.get("data"),
                )
                session.add(part_record)
                parts_inserted += 1
        await session.flush()
        logger.info(f"Inserted {parts_inserted} MMS parts")

    return count


async def bulk_insert_calls(session: AsyncSession, records: list[dict]) -> int:
    """Insert Call records with deduplication."""
    count = await bulk_upsert(session, Call, records)
    logger.info(f"Inserted {count} new Call records (of {len(records)} total)")
    return count
