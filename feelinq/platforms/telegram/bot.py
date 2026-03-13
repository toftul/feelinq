import logging

from telegram.ext import Application

from feelinq.config import settings
from feelinq.core import scheduler
from feelinq.core.i18n import load_locales
from feelinq.db import postgres, timescale
from feelinq.platforms.telegram.handlers import (
    start,
    reminder,
    settings as settings_handler,
    stats,
    help as help_handler,
    theory,
    feedback,
)

log = logging.getLogger(__name__)

_application: Application | None = None


def get_application() -> Application:
    assert _application is not None, "Application not built yet"
    return _application


async def post_init(application: Application) -> None:
    """Called after the Application is fully initialised."""
    await postgres.init()
    await timescale.ensure_schema()
    load_locales()

    # Sync admin list
    if settings.admin_ids_list:
        await postgres.sync_admins(settings.admin_ids_list)

    # Register reminder callback and schedule all users
    scheduler.register_reminder_callback("telegram", reminder.send_reminder)
    await scheduler.schedule_all_users()
    scheduler.start()

    log.info("Bot initialised")


async def post_shutdown(application: Application) -> None:
    """Called on shutdown."""
    sched = scheduler.get_scheduler()
    if sched.running:
        sched.shutdown(wait=False)
    await postgres.close()
    log.info("Bot shut down")


def build_application() -> Application:
    global _application

    builder = Application.builder().token(settings.telegram_bot_token)
    application = builder.post_init(post_init).post_shutdown(post_shutdown).build()

    # Register handlers — order matters
    # ConversationHandlers first (they consume callback queries)
    application.add_handler(start.get_conversation_handler(), group=0)
    application.add_handler(settings_handler.get_conversation_handler(), group=0)
    application.add_handler(reminder.get_conversation_handler(), group=1)

    # Simple command handlers
    application.add_handler(stats.get_handler())
    application.add_handler(help_handler.get_handler())
    application.add_handler(theory.get_handler())
    for h in feedback.get_handlers():
        application.add_handler(h)

    _application = application
    return application
