import logging
import random
from datetime import datetime, timedelta, timezone
from typing import Callable, Awaitable

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from feelinq.db import postgres

log = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler | None = None
_reminder_callbacks: dict[str, Callable[[str], Awaitable[None]]] = {}
_weekly_callbacks: dict[str, Callable[[str], Awaitable[None]]] = {}


def get_scheduler() -> AsyncIOScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = AsyncIOScheduler(timezone="UTC")
    return _scheduler


def register_reminder_callback(
    platform: str,
    callback: Callable[[str], Awaitable[None]],
) -> None:
    _reminder_callbacks[platform] = callback
    log.info("Registered reminder callback for platform: %s", platform)


def register_weekly_callback(
    platform: str,
    callback: Callable[[str], Awaitable[None]],
) -> None:
    _weekly_callbacks[platform] = callback
    log.info("Registered weekly summary callback for platform: %s", platform)


async def _fire_weekly(user_id: str, platform: str) -> None:
    callback = _weekly_callbacks.get(platform)
    if not callback:
        log.error("No weekly callback for platform '%s'", platform)
        return
    try:
        await callback(user_id)
    except Exception:
        log.exception("Error firing weekly summary for user %s", user_id)


def compute_fire_time(due_min_h: int, due_max_h: int) -> datetime:
    hours = random.uniform(due_min_h, due_max_h)
    return datetime.now(timezone.utc) + timedelta(hours=hours)


async def _fire_reminder(user_id: str, platform: str) -> None:
    callback = _reminder_callbacks.get(platform)
    if not callback:
        log.error("No reminder callback for platform '%s'", platform)
        return
    try:
        await callback(user_id)
    except Exception:
        log.exception("Error firing reminder for user %s", user_id)


def schedule_reminder(user_id: str, platform: str, fire_at: datetime) -> None:
    scheduler = get_scheduler()
    job_id = f"reminder:{user_id}"
    # Remove existing job if any
    existing = scheduler.get_job(job_id)
    if existing:
        existing.remove()
    scheduler.add_job(
        _fire_reminder,
        "date",
        run_date=fire_at,
        args=[user_id, platform],
        id=job_id,
        replace_existing=True,
    )
    log.debug("Scheduled reminder for user %s at %s", user_id, fire_at)


def cancel_reminder(user_id: str) -> None:
    scheduler = get_scheduler()
    job_id = f"reminder:{user_id}"
    existing = scheduler.get_job(job_id)
    if existing:
        existing.remove()
        log.debug("Cancelled reminder for user %s", user_id)


def reschedule(user_id: str, platform: str, fire_at: datetime) -> None:
    cancel_reminder(user_id)
    schedule_reminder(user_id, platform, fire_at)


async def schedule_all_users() -> None:
    users = await postgres.get_all_active_users()
    count = 0
    for user in users:
        fire_at = compute_fire_time(user["due_min_h"], user["due_max_h"])
        schedule_reminder(user["user_id"], user["platform"], fire_at)
        count += 1
    log.info("Scheduled reminders for %d active users", count)

    weekly_users = await postgres.get_all_weekly_users()
    weekly_count = 0
    for user in weekly_users:
        schedule_weekly_summary(
            user["user_id"], user["platform"], user["weekly_summary_day"],
        )
        weekly_count += 1
    log.info("Scheduled weekly summaries for %d users", weekly_count)


def schedule_weekly_summary(
    user_id: str,
    platform: str,
    day_of_week: int,
    hour: int = 10,
) -> None:
    scheduler = get_scheduler()
    job_id = f"weekly:{user_id}"
    days = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
    scheduler.add_job(
        _fire_weekly,
        "cron",
        day_of_week=days[day_of_week],
        hour=hour,
        args=[user_id, platform],
        id=job_id,
        replace_existing=True,
    )
    log.debug("Scheduled weekly summary for user %s on %s at %d:00",
              user_id, days[day_of_week], hour)


def cancel_weekly(user_id: str) -> None:
    scheduler = get_scheduler()
    job_id = f"weekly:{user_id}"
    existing = scheduler.get_job(job_id)
    if existing:
        existing.remove()
        log.debug("Cancelled weekly summary for user %s", user_id)


def start() -> None:
    scheduler = get_scheduler()
    if not scheduler.running:
        scheduler.start()
        log.info("Scheduler started")
