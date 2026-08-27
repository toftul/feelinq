from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

from feelinq.db import postgres
from feelinq.platforms.telegram.handlers.reminder import send_reminder


async def checkin_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    assert update.effective_chat and update.message
    platform_id = str(update.effective_chat.id)

    user = await postgres.get_user_by_platform("telegram", platform_id)
    if not user:
        await update.message.reply_text("Please /start first.", parse_mode="HTML")
        return

    await send_reminder(user["user_id"], force=True)


def get_handler() -> CommandHandler:
    return CommandHandler("checkin", checkin_command)
