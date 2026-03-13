import io

from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

from feelinq.core.i18n import t
from feelinq.core.stats_engine import generate_circumplex_reference
from feelinq.db import postgres


async def theory_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    assert update.effective_chat and update.message
    platform_id = str(update.effective_chat.id)

    user = await postgres.get_user_by_platform("telegram", platform_id)
    lang = user["language"] if user else "en"

    await update.message.reply_text(t(lang, "theory.text"), parse_mode="HTML")

    img = generate_circumplex_reference()
    await update.message.reply_photo(photo=io.BytesIO(img))


def get_handler() -> CommandHandler:
    return CommandHandler("theory", theory_command)
