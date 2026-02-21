"""APScheduler wrapper for Hoonbot's scheduled and interval jobs."""
import logging
from typing import Callable

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler = AsyncIOScheduler(timezone="UTC")


def start() -> None:
    if not _scheduler.running:
        _scheduler.start()
        logger.info("[Scheduler] Started")


def shutdown() -> None:
    if _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("[Scheduler] Stopped")


def add_interval_job(func: Callable, seconds: int, job_id: str) -> None:
    if _scheduler.get_job(job_id):
        _scheduler.remove_job(job_id)
    _scheduler.add_job(func, IntervalTrigger(seconds=seconds), id=job_id, replace_existing=True)
    logger.info(f"[Scheduler] Interval job added: {job_id} every {seconds}s")


def add_cron_job(func: Callable, cron_expr: str, job_id: str) -> None:
    """Add a cron job. cron_expr format: 'minute hour day month day_of_week'."""
    parts = cron_expr.split()
    if len(parts) != 5:
        raise ValueError(f"Invalid cron expression: {cron_expr!r} (expected 5 fields)")
    minute, hour, day, month, day_of_week = parts
    if _scheduler.get_job(job_id):
        _scheduler.remove_job(job_id)
    _scheduler.add_job(
        func,
        CronTrigger(minute=minute, hour=hour, day=day, month=month, day_of_week=day_of_week),
        id=job_id,
        replace_existing=True,
    )
    logger.info(f"[Scheduler] Cron job added: {job_id} @ {cron_expr}")


def remove_job(job_id: str) -> bool:
    if _scheduler.get_job(job_id):
        _scheduler.remove_job(job_id)
        logger.info(f"[Scheduler] Job removed: {job_id}")
        return True
    return False
