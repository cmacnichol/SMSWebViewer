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
    if not records:
        return 0

    # 1. Fetch existing hashes to prevent duplicate MMSPart insertion
    existing_hashes = set()
    all_hashes = [r["hash"] for r in records]
    for i in range(0, len(all_hashes), 500):
        batch_hashes = all_hashes[i : i + 500]
        result = await session.execute(
            select(MMS.hash).where(MMS.hash.in_(batch_hashes))
        )
        existing_hashes.update(result.scalars().all())

    # 2. Filter records to only those that are new
    new_records = [r for r in records if r["hash"] not in existing_hashes]
    if not new_records:
        return 0

    # 3. Insert new MMS records
    count = await bulk_upsert(session, MMS, new_records)
    logger.info(f"Inserted {count} new MMS records (of {len(records)} total)")

    # 4. Insert parts only for the newly inserted records
    if parts_map and count > 0:
        new_hashes = [r["hash"] for r in new_records]
        
        # Fetch the IDs of the newly inserted MMS records
        hash_to_id = {}
        for i in range(0, len(new_hashes), 500):
            batch_hashes = new_hashes[i : i + 500]
            result = await session.execute(
                select(MMS.id, MMS.hash).where(MMS.hash.in_(batch_hashes))
            )
            for mms_id, mms_hash in result.all():
                hash_to_id[mms_hash] = mms_id

        # Prepare parts for bulk insert
        parts_to_insert = []
        for mms_hash, parts in parts_map:
            if mms_hash not in hash_to_id or not parts:
                continue
            mms_id = hash_to_id[mms_hash]
            for part in parts:
                parts_to_insert.append({
                    "mms_id": mms_id,
                    "seq": part.get("seq", 0),
                    "content_type": part.get("content_type", "application/octet-stream"),
                    "name": part.get("name"),
                    "text": part.get("text"),
                    "data": part.get("data")
                })

        if parts_to_insert:
            # Insert parts in batches
            for i in range(0, len(parts_to_insert), 500):
                batch_parts = parts_to_insert[i : i + 500]
                await session.execute(sqlite_insert(MMSPart).values(batch_parts) if session.bind.dialect.name == "sqlite" else pg_insert(MMSPart).values(batch_parts))
            
            logger.info(f"Inserted {len(parts_to_insert)} MMS parts")

    return count


async def bulk_insert_calls(session: AsyncSession, records: list[dict]) -> int:
    """Insert Call records with deduplication."""
    count = await bulk_upsert(session, Call, records)
    logger.info(f"Inserted {count} new Call records (of {len(records)} total)")
    return count
