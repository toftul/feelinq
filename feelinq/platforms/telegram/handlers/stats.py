import io
import logging

from telegram import InputMediaPhoto, Update
from telegram.ext import CommandHandler, ContextTypes

from feelinq.core.i18n import t
from feelinq.core import stats_engine
from feelinq.db import postgres

log = logging.getLogger(__name__)


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    assert update.effective_chat and update.message
    platform_id = str(update.effective_chat.id)

    user = await postgres.get_user_by_platform("telegram", platform_id)
    if not user:
        await update.message.reply_text("Please /start first.", parse_mode="HTML")
        return

    lang = user["language"]
    charts = await stats_engine.generate_all(user["user_id"])

    if charts is None:
        await update.message.reply_text(t(lang, "stats.not_enough_data", min=stats_engine.MIN_ENTRIES), parse_mode="HTML")
        return

    # Send as individual photos with captions
    for caption, img_bytes in charts:
        await update.message.reply_photo(
            photo=io.BytesIO(img_bytes),
            caption=caption,
        )


def get_handler() -> CommandHandler:
    return CommandHandler("stats", stats_command)
