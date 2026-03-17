import io
import logging

from telegram import Update
from telegram.ext import (
    CallbackQueryHandler,
    ConversationHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from feelinq.core.emotions import quadrant_diagram
from feelinq.core.entry_handler import save_entry
from feelinq.core.i18n import t
from feelinq.core import scheduler, stats_engine
from feelinq.db import postgres
from feelinq.platforms.telegram import keyboards

log = logging.getLogger(__name__)

EMOTION_SELECT = 0

# Key in user_data for tracking active reminder sessions
_SESSION_KEY = "reminder_active"
_SELECTED_KEY = "reminder_selected"
_MSG_ID_KEY = "reminder_msg_id"


async def send_reminder(user_id: str) -> None:
    """Called by the scheduler. Sends the emotion picker to the user."""
    from feelinq.platforms.telegram.bot import get_application

    app = get_application()
    user = await postgres.get_user(user_id)
    if not user:
        return

    platform_id = int(user["platform_id"])
    lang = user["language"]

    # Check if there's already an active reminder session
    user_data = app.user_data.get(platform_id, {})
    if user_data.get(_SESSION_KEY):
        log.debug("Skipping reminder for user %s — session already active", user_id)
        return

    user_emotions = postgres.get_user_emotions(user)
    msg = await app.bot.send_message(
        chat_id=platform_id,
        text=t(lang, "reminder.prompt"),
        reply_markup=keyboards.emotion_picker_keyboard(lang, set(), emotion_keys=user_emotions),
        parse_mode="HTML",
    )

    # Store session state
    if platform_id not in app.user_data:
        app.user_data[platform_id] = {}
    app.user_data[platform_id][_SESSION_KEY] = True
    app.user_data[platform_id][_SELECTED_KEY] = set()
    app.user_data[platform_id][_MSG_ID_KEY] = msg.message_id


async def send_weekly_summary(user_id: str) -> None:
    """Called by the scheduler. Sends the weekly circumplex chart."""
    from feelinq.platforms.telegram.bot import get_application

    app = get_application()
    user = await postgres.get_user(user_id)
    if not user:
        return

    platform_id = int(user["platform_id"])

    result = await stats_engine.generate_weekly(user_id, user_tz=user.get("timezone") or "UTC")
    if not result:
        return

    caption, img_bytes = result
    await app.bot.send_photo(
        chat_id=platform_id,
        photo=io.BytesIO(img_bytes),
        caption=caption,
    )


async def emotion_toggled(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    assert query and query.data
    await query.answer()

    assert context.user_data is not None
    assert update.effective_chat

    platform_id = str(update.effective_chat.id)
    user = await postgres.get_user_by_platform("telegram", platform_id)
    if not user:
        return ConversationHandler.END
    lang = user["language"]

    selected: set[str] = context.user_data.get(_SELECTED_KEY, set())
    key = query.data.split(":")[1]

    if key == "done":
        if not selected:
            await query.answer(t(lang, "reminder.done_button_disabled"), show_alert=True)
            return EMOTION_SELECT

        emotion_keys = sorted(selected)
        emotion_labels = ", ".join(t(lang, f"emotions.{k}") for k in emotion_keys)

        mean_v, mean_a = await save_entry(
            user_id=user["user_id"],
            platform="telegram",
            platform_id=platform_id,
            emotion_keys=emotion_keys,
            timezone_str=user.get("timezone"),
        )

        diagram = quadrant_diagram(mean_v, mean_a)
        await query.edit_message_text(
            t(lang, "reminder.saved", emotions=emotion_labels, diagram=diagram),
            parse_mode="HTML",
        )

        # Clear session
        context.user_data.pop(_SESSION_KEY, None)
        context.user_data.pop(_SELECTED_KEY, None)
        context.user_data.pop(_MSG_ID_KEY, None)

        return ConversationHandler.END

    # Toggle emotion
    if key in selected:
        selected.discard(key)
    else:
        selected.add(key)
    context.user_data[_SELECTED_KEY] = selected

    user_emotions = postgres.get_user_emotions(user)
    await query.edit_message_reply_markup(
        reply_markup=keyboards.emotion_picker_keyboard(lang, selected, emotion_keys=user_emotions),
    )
    return EMOTION_SELECT


async def text_during_picker(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    assert update.effective_chat
    platform_id = str(update.effective_chat.id)
    user = await postgres.get_user_by_platform("telegram", platform_id)
    lang = user["language"] if user else "en"
    await update.message.reply_text(t(lang, "errors.use_buttons"), parse_mode="HTML")  # type: ignore[union-attr]
    return EMOTION_SELECT


async def _timeout(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Clean up session state and reschedule so reminders keep coming."""
    if context.user_data:
        context.user_data.pop(_SESSION_KEY, None)
        context.user_data.pop(_SELECTED_KEY, None)
        context.user_data.pop(_MSG_ID_KEY, None)

    # Reschedule next reminder — the one-shot job was consumed when the picker was sent
    if update.effective_chat:
        platform_id = str(update.effective_chat.id)
        user = await postgres.get_user_by_platform("telegram", platform_id)
        if user and user["reminders_toggle"]:
            fire_at = scheduler.compute_fire_time(user["due_min_h"], user["due_max_h"])
            scheduler.schedule_reminder(user["user_id"], "telegram", fire_at)

    return ConversationHandler.END


def get_conversation_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            CallbackQueryHandler(emotion_toggled, pattern=r"^emo:"),
        ],
        states={
            EMOTION_SELECT: [
                CallbackQueryHandler(emotion_toggled, pattern=r"^emo:"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, text_during_picker),
            ],
            ConversationHandler.TIMEOUT: [
                MessageHandler(filters.ALL, _timeout),
            ],
        },
        fallbacks=[
            MessageHandler(filters.TEXT & ~filters.COMMAND, text_during_picker),
        ],
        per_message=True,
        conversation_timeout=4 * 3600,  # 4 hours
    )
