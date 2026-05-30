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
    """Configure and start the scheduler for all configured users."""
    import asyncio
    scheduler._eventloop = asyncio.get_running_loop()
    
    async with async_session_maker() as session:
        stmt = select(AppConfig).where(AppConfig.sync_schedule.isnot(None))
        configs = (await session.execute(stmt)).scalars().all()
        
    for config in configs:
        if config.user_id:
            _apply_schedule(config.sync_schedule, config.user_id)
            
    scheduler.start()


def _apply_schedule(schedule: str, user_id: str) -> None:
    job_id = f"ingestion_pipeline_{user_id}"
    if schedule == "manual":
        if scheduler.get_job(job_id):
            scheduler.remove_job(job_id)
        logger.info(f"Sync schedule set to manual for {user_id}. Automatic sync disabled.")
        return

    try:
        trigger = CronTrigger.from_crontab(schedule)
        scheduler.add_job(
            run_ingestion_pipeline,
            trigger=trigger,
            args=[user_id],
            id=job_id,
            replace_existing=True,
            misfire_grace_time=3600,
        )
        logger.info(f"Scheduler active for {user_id} with schedule: {schedule}")
    except Exception as e:
        logger.error(f"Failed to setup scheduler for {user_id}: {e}")


async def reschedule_sync_job(new_schedule: str, user_id: str) -> None:
    """Dynamically update the schedule for a user."""
    _apply_schedule(new_schedule, user_id)


def shutdown_scheduler() -> None:
    """Gracefully shut down the scheduler."""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Scheduler shut down")
