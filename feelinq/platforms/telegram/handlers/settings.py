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

MENU, REMINDER_MIN, REMINDER_MAX, TZ_REGION, TZ_CITY, LANG, WEEKLY, EMOTIONS = range(8)


async def _get_user_lang(update: Update) -> tuple[str, str, str]:
    """Returns (user_id, platform_id, lang)."""
    assert update.effective_chat
    platform_id = str(update.effective_chat.id)
    user = await postgres.get_user_by_platform("telegram", platform_id)
    if not user:
        return "", platform_id, "en"
    return user["user_id"], platform_id, user["language"]


async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id, platform_id, lang = await _get_user_lang(update)
    if not user_id:
        await update.message.reply_text("Please /start first.", parse_mode="HTML")  # type: ignore[union-attr]
        return ConversationHandler.END

    await update.message.reply_text(  # type: ignore[union-attr]
        t(lang, "settings.title"),
        reply_markup=keyboards.settings_menu_keyboard(lang),
        parse_mode="HTML",
    )
    return MENU


async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    assert query and query.data
    await query.answer()

    user_id, platform_id, lang = await _get_user_lang(update)
    if not user_id:
        return ConversationHandler.END

    user = await postgres.get_user(user_id)
    assert user is not None
    action = query.data.split(":")[1]

    if action == "close":
        await query.edit_message_text(t(lang, "settings.saved"), parse_mode="HTML")
        return ConversationHandler.END

    if action == "back":
        await query.edit_message_text(
            t(lang, "settings.title"),
            reply_markup=keyboards.settings_menu_keyboard(lang),
            parse_mode="HTML",
        )
        return MENU

    if action == "emotions":
        current = postgres.get_user_emotions(user)
        selected = set(current) if current else set()
        assert context.user_data is not None
        context.user_data["set_emotions"] = selected
        await query.edit_message_text(
            t(lang, "emotions_chooser.prompt"),
            reply_markup=keyboards.emotion_chooser_keyboard(lang, selected),
            parse_mode="HTML",
        )
        return EMOTIONS

    if action == "reminder":
        await query.edit_message_text(
            t(lang, "settings.reminder_current", min=user["due_min_h"], max=user["due_max_h"]),
            parse_mode="HTML",
        )
        return REMINDER_MIN

    if action == "reminders_toggle":
        current = user["reminders_toggle"]
        new_val = not current
        await postgres.update_user(user_id, reminders_toggle=new_val)
        if new_val:
            fire_at = scheduler.compute_fire_time(user["due_min_h"], user["due_max_h"])
            await postgres.update_user(user_id, next_reminder_at=fire_at)
            scheduler.schedule_reminder(user_id, "telegram", fire_at)
            text = t(lang, "settings.reminders_enabled", min=user["due_min_h"], max=user["due_max_h"])
        else:
            scheduler.cancel_reminder(user_id)
            text = t(lang, "settings.reminders_disabled")
        await query.edit_message_text(
            text,
            reply_markup=keyboards.settings_menu_keyboard(lang),
            parse_mode="HTML",
        )
        return MENU

    if action == "tz":
        await query.edit_message_text(
            t(lang, "onboarding.choose_timezone"),
            reply_markup=keyboards.timezone_regions_keyboard(),
            parse_mode="HTML",
        )
        return TZ_REGION

    if action == "lang":
        await query.edit_message_text(
            t(lang, "onboarding.welcome"),
            reply_markup=keyboards.language_keyboard(),
            parse_mode="HTML",
        )
        return LANG

    if action == "weekly":
        is_on = user["weekly_summary_toggle"]
        day_name = t(lang, f"days.{user['weekly_summary_day']}")
        status = t(lang, "settings.weekly_toggle_off") if is_on else t(lang, "settings.weekly_toggle_on")
        await query.edit_message_text(
            t(lang, "settings.weekly_status", status="ON" if is_on else "OFF", day=day_name),
            reply_markup=keyboards.weekly_summary_keyboard(lang, is_on),
            parse_mode="HTML",
        )
        return WEEKLY

    return MENU


async def reminder_min_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    assert update.message and update.message.text
    user_id, _, lang = await _get_user_lang(update)
    if not user_id:
        return ConversationHandler.END

    try:
        val = float(update.message.text.strip())
        if not (0.01 <= val <= 23):
            raise ValueError
    except ValueError:
        await update.message.reply_text(t(lang, "settings.reminder_invalid", lo=0.01, hi=23), parse_mode="HTML")
        return REMINDER_MIN

    assert context.user_data is not None
    context.user_data["set_min_h"] = val
    await update.message.reply_text(t(lang, "settings.reminder_max", min=val), parse_mode="HTML")
    return REMINDER_MAX


async def reminder_max_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    assert update.message and update.message.text
    user_id, _, lang = await _get_user_lang(update)
    if not user_id:
        return ConversationHandler.END

    assert context.user_data is not None
    min_h = context.user_data.get("set_min_h", 1)

    try:
        val = float(update.message.text.strip())
        if not (min_h <= val <= 23):
            raise ValueError
    except ValueError:
        await update.message.reply_text(t(lang, "settings.reminder_invalid", lo=min_h, hi=23), parse_mode="HTML")
        return REMINDER_MAX

    await postgres.update_user(user_id, due_min_h=min_h, due_max_h=val)

    # Reschedule
    fire_at = scheduler.compute_fire_time(min_h, val)
    await postgres.update_user(user_id, next_reminder_at=fire_at)
    scheduler.reschedule(user_id, "telegram", fire_at)

    await update.message.reply_text(
        t(lang, "settings.reminder_saved", min=min_h, max=val),
        reply_markup=keyboards.settings_menu_keyboard(lang),
        parse_mode="HTML",
    )
    return MENU


async def tz_region_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    assert query and query.data
    await query.answer()

    user_id, _, lang = await _get_user_lang(update)
    if not user_id:
        return ConversationHandler.END

    if query.data == "tz:UTC":
        await postgres.update_user(user_id, timezone="UTC")
        await query.edit_message_text(
            t(lang, "settings.tz_saved", tz="UTC"),
            reply_markup=keyboards.settings_menu_keyboard(lang),
            parse_mode="HTML",
        )
        return MENU

    region = query.data.split(":")[1]
    assert context.user_data is not None
    context.user_data["set_tz_region"] = region
    await query.edit_message_text(
        t(lang, "onboarding.choose_city"),
        reply_markup=keyboards.timezone_cities_keyboard(region),
        parse_mode="HTML",
    )
    return TZ_CITY


async def tz_city_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    assert query and query.data
    await query.answer()

    user_id, _, lang = await _get_user_lang(update)
    if not user_id:
        return ConversationHandler.END

    if query.data == "tz_back":
        await query.edit_message_text(
            t(lang, "onboarding.choose_timezone"),
            reply_markup=keyboards.timezone_regions_keyboard(),
            parse_mode="HTML",
        )
        return TZ_REGION

    tz_name = query.data.split(":", 1)[1]
    await postgres.update_user(user_id, timezone=tz_name)
    await query.edit_message_text(
        t(lang, "settings.tz_saved", tz=tz_name),
        reply_markup=keyboards.settings_menu_keyboard(lang),
        parse_mode="HTML",
    )
    return MENU


async def tz_typed(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    assert update.message and update.message.text
    user_id, _, lang = await _get_user_lang(update)
    if not user_id:
        return ConversationHandler.END

    tz_text = update.message.text.strip()
    try:
        ZoneInfo(tz_text)
    except (ZoneInfoNotFoundError, KeyError):
        await update.message.reply_text(t(lang, "onboarding.invalid_timezone"), parse_mode="HTML")
        return TZ_CITY

    await postgres.update_user(user_id, timezone=tz_text)
    await update.message.reply_text(
        t(lang, "settings.tz_saved", tz=tz_text),
        reply_markup=keyboards.settings_menu_keyboard(lang),
        parse_mode="HTML",
    )
    return MENU


async def lang_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    assert query and query.data
    await query.answer()

    user_id, _, _ = await _get_user_lang(update)
    if not user_id:
        return ConversationHandler.END

    new_lang = query.data.split(":")[1]
    await postgres.update_user(user_id, language=new_lang)
    await query.edit_message_text(
        t(new_lang, "settings.lang_saved"),
        reply_markup=keyboards.settings_menu_keyboard(new_lang),
        parse_mode="HTML",
    )
    return MENU


async def weekly_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    assert query and query.data
    await query.answer()

    user_id, _, lang = await _get_user_lang(update)
    if not user_id:
        return ConversationHandler.END

    user = await postgres.get_user(user_id)
    assert user is not None

    data = query.data
    if data == "weekly:toggle":
        new_val = not user["weekly_summary_toggle"]
        await postgres.update_user(user_id, weekly_summary_toggle=new_val)
        is_on = new_val
        day_name = t(lang, f"days.{user['weekly_summary_day']}")
        await query.edit_message_text(
            t(lang, "settings.weekly_status", status="ON" if is_on else "OFF", day=day_name),
            reply_markup=keyboards.weekly_summary_keyboard(lang, is_on),
            parse_mode="HTML",
        )
        return WEEKLY

    if data.startswith("weekly:day:"):
        day = int(data.split(":")[2])
        await postgres.update_user(user_id, weekly_summary_day=day)
        day_name = t(lang, f"days.{day}")
        await query.edit_message_text(
            t(lang, "settings.weekly_saved"),
            reply_markup=keyboards.settings_menu_keyboard(lang),
            parse_mode="HTML",
        )
        return MENU

    # back
    await query.edit_message_text(
        t(lang, "settings.title"),
        reply_markup=keyboards.settings_menu_keyboard(lang),
        parse_mode="HTML",
    )
    return MENU


async def emotions_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    assert query and query.data
    await query.answer()

    user_id, _, lang = await _get_user_lang(update)
    if not user_id:
        return ConversationHandler.END

    assert context.user_data is not None
    selected: set[str] = context.user_data.get("set_emotions", set())
    key = query.data.split(":")[1]

    if key == "_noop":
        return EMOTIONS

    if key == "done":
        error = validate_emotion_selection(selected)
        if error:
            await query.answer(t(lang, f"emotions_chooser.error_{error}"), show_alert=True)
            return EMOTIONS

        await postgres.set_user_emotions(user_id, sorted(selected))
        await query.edit_message_text(
            t(lang, "emotions_chooser.saved"),
            reply_markup=keyboards.settings_menu_keyboard(lang),
            parse_mode="HTML",
        )
        return MENU

    # Toggle
    if key in selected:
        selected.discard(key)
    else:
        selected.add(key)
    context.user_data["set_emotions"] = selected

    await query.edit_message_reply_markup(
        reply_markup=keyboards.emotion_chooser_keyboard(lang, selected),
    )
    return EMOTIONS


def get_conversation_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[CommandHandler("settings", settings_command)],
        states={
            MENU: [
                CallbackQueryHandler(menu_callback, pattern=r"^set:"),
            ],
            REMINDER_MIN: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, reminder_min_input),
            ],
            REMINDER_MAX: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, reminder_max_input),
            ],
            TZ_REGION: [
                CallbackQueryHandler(tz_region_callback, pattern=r"^tz_region:|^tz:UTC$"),
            ],
            TZ_CITY: [
                CallbackQueryHandler(tz_city_callback, pattern=r"^tz:|^tz_back$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, tz_typed),
            ],
            LANG: [
                CallbackQueryHandler(lang_callback, pattern=r"^lang:"),
            ],
            WEEKLY: [
                CallbackQueryHandler(weekly_callback, pattern=r"^weekly:|^set:back$"),
            ],
            EMOTIONS: [
                CallbackQueryHandler(emotions_callback, pattern=r"^echoose:"),
            ],
        },
        fallbacks=[CommandHandler("settings", settings_command)],
        per_message=False,
    )
