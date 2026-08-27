from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

from feelinq.core.i18n import t
from feelinq.db import postgres
from feelinq.platforms.telegram.handlers.reminder import send_weekly_report


async def weekly_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    assert update.effective_chat and update.message
    platform_id = str(update.effective_chat.id)

    user = await postgres.get_user_by_platform("telegram", platform_id)
    if not user:
        await update.message.reply_text("Please /start first.", parse_mode="HTML")
        return

    if not await send_weekly_report(user["user_id"]):
        await update.message.reply_text(t(user["language"], "weekly.no_data"), parse_mode="HTML")


def get_handler() -> CommandHandler:
    return CommandHandler("weekly", weekly_command)
