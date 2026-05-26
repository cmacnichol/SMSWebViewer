import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select

from app.core.database import async_session_maker
from app.models.config import AppConfig
from app.services.pipeline import run_ingestion_pipeline

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


async def setup_scheduler() -> None:
    """Configure and start the scheduler with the configured cron expression."""
    async with async_session_maker() as session:
        stmt = select(AppConfig).where(AppConfig.id == 1)
        config = (await session.execute(stmt)).scalar_one_or_none()
        
    schedule = config.sync_schedule if config and config.sync_schedule else "manual"
    
    _apply_schedule(schedule)
    scheduler.start()


def _apply_schedule(schedule: str) -> None:
    if schedule == "manual":
        if scheduler.get_job("ingestion_pipeline"):
            scheduler.remove_job("ingestion_pipeline")
        logger.info("Sync schedule set to manual. Automatic sync disabled.")
        return

    try:
        trigger = CronTrigger.from_crontab(schedule)
        scheduler.add_job(
            run_ingestion_pipeline,
            trigger=trigger,
            id="ingestion_pipeline",
            replace_existing=True,
            misfire_grace_time=3600,
        )
        logger.info(f"Scheduler active with schedule: {schedule}")
    except Exception as e:
        logger.error(f"Failed to setup scheduler: {e}")


async def reschedule_sync_job(new_schedule: str) -> None:
    """Dynamically update the schedule."""
    _apply_schedule(new_schedule)


def shutdown_scheduler() -> None:
    """Gracefully shut down the scheduler."""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Scheduler shut down")
