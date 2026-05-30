import asyncio
import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select

from app.core.database import async_session_maker, init_db
from app.models.config import AppConfig
from app.services.pipeline import run_ingestion_pipeline

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("worker")

scheduler = AsyncIOScheduler()
_current_schedules = {}

async def sync_schedules_from_db():
    """Poll the database for schedule changes and update APScheduler."""
    async with async_session_maker() as session:
        stmt = select(AppConfig).where(AppConfig.sync_schedule.isnot(None))
        configs = (await session.execute(stmt)).scalars().all()
        
    active_users = set()
    
    for config in configs:
        if not config.user_id:
            continue
            
        active_users.add(config.user_id)
        job_id = f"ingestion_pipeline_{config.user_id}"
        schedule = config.sync_schedule
        
        if _current_schedules.get(config.user_id) != schedule:
            _current_schedules[config.user_id] = schedule
            
            if schedule == "manual":
                if scheduler.get_job(job_id):
                    scheduler.remove_job(job_id)
                logger.info(f"Sync schedule set to manual for {config.user_id}.")
                continue
                
            try:
                trigger = CronTrigger.from_crontab(schedule)
                scheduler.add_job(
                    run_ingestion_pipeline,
                    trigger=trigger,
                    args=[config.user_id],
                    id=job_id,
                    replace_existing=True,
                    misfire_grace_time=3600,
                )
                logger.info(f"Scheduler active for {config.user_id} with schedule: {schedule}")
            except Exception as e:
                logger.error(f"Failed to setup scheduler for {config.user_id}: {e}")
                
    # Remove jobs for users that no longer have configs
    for user_id in list(_current_schedules.keys()):
        if user_id not in active_users:
            job_id = f"ingestion_pipeline_{user_id}"
            if scheduler.get_job(job_id):
                scheduler.remove_job(job_id)
            del _current_schedules[user_id]

async def main():
    logger.info("Initializing database from worker...")
    await init_db()
    
    logger.info("Starting background worker scheduler...")
    scheduler._eventloop = asyncio.get_running_loop()
    scheduler.start()
    
    while True:
        try:
            await sync_schedules_from_db()
        except Exception as e:
            logger.error(f"Error syncing schedules from DB: {e}")
        await asyncio.sleep(60)

if __name__ == "__main__":
    asyncio.run(main())
