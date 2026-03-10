from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

from feelinq.core.i18n import t
from feelinq.db import postgres


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    assert update.effective_chat and update.message
    platform_id = str(update.effective_chat.id)

    user = await postgres.get_user_by_platform("telegram", platform_id)
    lang = user["language"] if user else "en"

    await update.message.reply_text(t(lang, "help.text"), parse_mode="HTML")


def get_handler() -> CommandHandler:
    return CommandHandler("help", help_command)
