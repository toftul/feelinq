import logging
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from telegram import Update
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ConversationHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from feelinq.core.emotions import validate_emotion_selection
from feelinq.core.i18n import t
from feelinq.core import scheduler
from feelinq.db import postgres
from feelinq.platforms.telegram import keyboards

log = logging.getLogger(__name__)

LANGUAGE, TIMEZONE_REGION, TIMEZONE_CITY, EMOTIONS = range(4)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    assert update.effective_chat
    platform_id = str(update.effective_chat.id)

    user = await postgres.get_user_by_platform("telegram", platform_id)
    if user:
        # Returning user — send emotion picker directly
        from feelinq.platforms.telegram.handlers.reminder import send_reminder
        await send_reminder(user["user_id"])
        return ConversationHandler.END

    await update.message.reply_text(  # type: ignore[union-attr]
        t("en", "onboarding.welcome"),
        reply_markup=keyboards.language_keyboard(),
        parse_mode="HTML",
    )
    return LANGUAGE


async def language_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    assert query and query.data
    await query.answer()

    lang = query.data.split(":")[1]
    assert context.user_data is not None
    context.user_data["onboard_lang"] = lang

    await query.edit_message_text(
        t(lang, "onboarding.choose_timezone"),
        reply_markup=keyboards.timezone_regions_keyboard(),
        parse_mode="HTML",
    )
    return TIMEZONE_REGION


async def timezone_region_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    assert query and query.data
    await query.answer()

    assert context.user_data is not None
    lang = context.user_data.get("onboard_lang", "en")

    if query.data == "tz:UTC":
        context.user_data["onboard_tz"] = "UTC"
        return await _show_emotion_chooser(update, context)

    region = query.data.split(":")[1]
    context.user_data["onboard_region"] = region

    await query.edit_message_text(
        t(lang, "onboarding.choose_city"),
        reply_markup=keyboards.timezone_cities_keyboard(region),
        parse_mode="HTML",
    )
    return TIMEZONE_CITY


async def timezone_city_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    assert query and query.data
    await query.answer()

    assert context.user_data is not None
    lang = context.user_data.get("onboard_lang", "en")

    if query.data == "tz_back":
        await query.edit_message_text(
            t(lang, "onboarding.choose_timezone"),
            reply_markup=keyboards.timezone_regions_keyboard(),
            parse_mode="HTML",
        )
        return TIMEZONE_REGION

    tz_name = query.data.split(":", 1)[1]
    context.user_data["onboard_tz"] = tz_name
    return await _show_emotion_chooser(update, context)


async def timezone_typed(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    assert update.message and update.message.text
    assert context.user_data is not None
    lang = context.user_data.get("onboard_lang", "en")
    tz_text = update.message.text.strip()

    try:
        ZoneInfo(tz_text)
    except (ZoneInfoNotFoundError, KeyError):
        await update.message.reply_text(
            t(lang, "onboarding.invalid_timezone"),
            parse_mode="HTML",
        )
        return TIMEZONE_CITY

    context.user_data["onboard_tz"] = tz_text
    return await _show_emotion_chooser(update, context)


async def _show_emotion_chooser(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    assert context.user_data is not None
    lang = context.user_data.get("onboard_lang", "en")
    context.user_data["onboard_emotions"] = set()

    text = t(lang, "emotions_chooser.prompt")
    kb = keyboards.emotion_chooser_keyboard(lang, set())
    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=kb, parse_mode="HTML")
    else:
        assert update.effective_chat
        await update.effective_chat.send_message(text, reply_markup=kb, parse_mode="HTML")
    return EMOTIONS


async def emotion_chooser_toggled(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    assert query and query.data
    await query.answer()

    assert context.user_data is not None
    lang = context.user_data.get("onboard_lang", "en")
    selected: set[str] = context.user_data.get("onboard_emotions", set())
    key = query.data.split(":")[1]

    if key == "_noop":
        return EMOTIONS

    if key == "done":
        error = validate_emotion_selection(selected)
        if error:
            await query.answer(t(lang, f"emotions_chooser.error_{error}"), show_alert=True)
            return EMOTIONS
        context.user_data["onboard_emotions"] = selected
        return await _finish_onboarding(update, context)

    # Toggle
    if key in selected:
        selected.discard(key)
    else:
        selected.add(key)
    context.user_data["onboard_emotions"] = selected

    await query.edit_message_reply_markup(
        reply_markup=keyboards.emotion_chooser_keyboard(lang, selected),
    )
    return EMOTIONS


async def _finish_onboarding(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    assert context.user_data is not None
    assert update.effective_chat
    lang = context.user_data["onboard_lang"]
    tz = context.user_data["onboard_tz"]
    platform_id = str(update.effective_chat.id)

    user = await postgres.create_user("telegram", platform_id, language=lang)
    user_id = user["user_id"]
    await postgres.update_user(user_id, timezone=tz)

    chosen_emotions: set[str] = context.user_data.get("onboard_emotions", set())
    if chosen_emotions:
        await postgres.set_user_emotions(user_id, sorted(chosen_emotions))

    due_min = user["due_min_h"]
    due_max = user["due_max_h"]
    fire_at = scheduler.compute_fire_time(due_min, due_max)
    await postgres.update_user(user_id, next_reminder_at=fire_at)
    scheduler.schedule_reminder(user_id, "telegram", fire_at)
    scheduler.schedule_weekly_summary(user_id, "telegram", user["weekly_summary_day"], tz=tz)

    text = t(lang, "onboarding.done", min=due_min, max=due_max)
    if update.callback_query:
        await update.callback_query.edit_message_text(text, parse_mode="HTML")
    else:
        await update.effective_chat.send_message(text, parse_mode="HTML")

    log.info("Onboarded user %s (platform_id=%s, lang=%s, tz=%s)", user_id, platform_id, lang, tz)
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return ConversationHandler.END


def get_conversation_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[CommandHandler("start", start_command)],
        states={
            LANGUAGE: [
                CallbackQueryHandler(language_chosen, pattern=r"^lang:"),
            ],
            TIMEZONE_REGION: [
                CallbackQueryHandler(timezone_region_chosen, pattern=r"^tz_region:|^tz:UTC$"),
            ],
            TIMEZONE_CITY: [
                CallbackQueryHandler(timezone_city_chosen, pattern=r"^tz:|^tz_back$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, timezone_typed),
            ],
            EMOTIONS: [
                CallbackQueryHandler(emotion_chooser_toggled, pattern=r"^echoose:"),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        per_message=False,
    )
