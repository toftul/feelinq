import logging

from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

from feelinq.core.i18n import t
from feelinq.db import postgres

log = logging.getLogger(__name__)


async def feedback_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    assert update.effective_chat and update.message
    platform_id = str(update.effective_chat.id)

    user = await postgres.get_user_by_platform("telegram", platform_id)
    if not user:
        await update.message.reply_text("Please /start first.", parse_mode="HTML")
        return

    lang = user["language"]
    text = update.message.text or ""
    # Strip the /feedback prefix
    parts = text.split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        await update.message.reply_text(t(lang, "feedback.missing"), parse_mode="HTML")
        return

    feedback_text = parts[1].strip()
    user_id = user["user_id"]

    # Forward to all admins
    admins = await postgres.get_admins()
    for admin in admins:
        try:
            admin_chat_id = int(admin["platform_id"])
            admin_lang = admin["language"]
            await context.bot.send_message(
                chat_id=admin_chat_id,
                text=t(admin_lang, "feedback.incoming", user_id=user_id, text=feedback_text),
                parse_mode="HTML",
            )
        except Exception:
            log.exception("Failed to forward feedback to admin %s", admin["user_id"])

    await update.message.reply_text(t(lang, "feedback.sent"), parse_mode="HTML")
    log.info("Feedback from user %s forwarded to %d admins", user_id, len(admins))


async def admin_stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    assert update.effective_chat and update.message
    platform_id = str(update.effective_chat.id)

    user = await postgres.get_user_by_platform("telegram", platform_id)
    if not user or not user["is_admin"]:
        return  # Silently ignore

    from feelinq.core.admin import get_admin_stats
    stats = await get_admin_stats()
    lang = user["language"]
    platforms_str = ", ".join(f"{k}: {v}" for k, v in stats["platform_breakdown"].items())

    await update.message.reply_text(
        t(lang, "admin.stats",
          total_users=stats["total_users"],
          active_7d=stats["active_7d"],
          total_entries=stats["total_entries"],
          platforms=platforms_str or "—"),
        parse_mode="HTML",
    )


def get_handlers() -> list[CommandHandler]:
    return [
        CommandHandler("feedback", feedback_command),
        CommandHandler("admin_stats", admin_stats_command),
    ]
