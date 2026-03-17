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

MENU, REMINDERS, TZ_REGION, TZ_CITY, LANG, WEEKLY, EMOTIONS = range(7)


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

    if action == "reminders":
        await query.edit_message_text(
            t(lang, "settings.reminders"),
            reply_markup=_reminders_kb(lang, user),
            parse_mode="HTML",
        )
        return REMINDERS

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

    return MENU


def _reminders_kb(lang: str, user: dict):
    return keyboards.reminders_submenu_keyboard(
        lang,
        user["reminders_toggle"],
        user["weekly_summary_toggle"],
        user["due_min_h"],
        user["due_max_h"],
        user["weekly_summary_day"],
    )


async def reminders_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    assert query and query.data
    await query.answer()

    user_id, _, lang = await _get_user_lang(update)
    if not user_id:
        return ConversationHandler.END

    user = await postgres.get_user(user_id)
    assert user is not None

    data = query.data

    if data == "rem:back":
        await query.edit_message_text(
            t(lang, "settings.title"),
            reply_markup=keyboards.settings_menu_keyboard(lang),
            parse_mode="HTML",
        )
        return MENU

    if data == "rem:toggle":
        # Master: if both ON → set both OFF; otherwise set both ON
        all_on = user["reminders_toggle"] and user["weekly_summary_toggle"]
        new_val = not all_on
        await postgres.update_user(user_id, reminders_toggle=new_val, weekly_summary_toggle=new_val)
        if new_val:
            fire_at = scheduler.compute_fire_time(user["due_min_h"], user["due_max_h"])
            await postgres.update_user(user_id, next_reminder_at=fire_at)
            scheduler.schedule_reminder(user_id, "telegram", fire_at)
            scheduler.schedule_weekly_summary(user_id, "telegram", user["weekly_summary_day"], tz=user.get("timezone") or "UTC")
        else:
            scheduler.cancel_reminder(user_id)
            scheduler.cancel_weekly(user_id)
        user = await postgres.get_user(user_id)
        assert user is not None
        await query.edit_message_text(
            t(lang, "settings.reminders"),
            reply_markup=_reminders_kb(lang, user),
            parse_mode="HTML",
        )
        return REMINDERS

    if data == "rem:toggle_checkin":
        new_val = not user["reminders_toggle"]
        await postgres.update_user(user_id, reminders_toggle=new_val)
        if new_val:
            fire_at = scheduler.compute_fire_time(user["due_min_h"], user["due_max_h"])
            await postgres.update_user(user_id, next_reminder_at=fire_at)
            scheduler.schedule_reminder(user_id, "telegram", fire_at)
        else:
            scheduler.cancel_reminder(user_id)
        user = await postgres.get_user(user_id)
        assert user is not None
        await query.edit_message_text(
            t(lang, "settings.reminders"),
            reply_markup=_reminders_kb(lang, user),
            parse_mode="HTML",
        )
        return REMINDERS

    if data == "rem:toggle_weekly":
        new_val = not user["weekly_summary_toggle"]
        await postgres.update_user(user_id, weekly_summary_toggle=new_val)
        if new_val:
            scheduler.schedule_weekly_summary(user_id, "telegram", user["weekly_summary_day"], tz=user.get("timezone") or "UTC")
        else:
            scheduler.cancel_weekly(user_id)
        user = await postgres.get_user(user_id)
        assert user is not None
        await query.edit_message_text(
            t(lang, "settings.reminders"),
            reply_markup=_reminders_kb(lang, user),
            parse_mode="HTML",
        )
        return REMINDERS

    if data == "rem:checkin":
        await query.edit_message_text(
            t(lang, "settings.checkin_prompt"),
            reply_markup=keyboards.checkin_window_keyboard(lang, user["due_min_h"], user["due_max_h"]),
            parse_mode="HTML",
        )
        return REMINDERS

    if data.startswith("rem:w:"):
        parts = data.split(":")
        min_h, max_h = int(parts[2]), int(parts[3])
        await postgres.update_user(user_id, due_min_h=min_h, due_max_h=max_h)
        if user["reminders_toggle"]:
            fire_at = scheduler.compute_fire_time(min_h, max_h)
            await postgres.update_user(user_id, next_reminder_at=fire_at)
            scheduler.reschedule(user_id, "telegram", fire_at)
        user = await postgres.get_user(user_id)
        assert user is not None
        await query.edit_message_text(
            t(lang, "settings.reminders"),
            reply_markup=_reminders_kb(lang, user),
            parse_mode="HTML",
        )
        return REMINDERS

    if data == "rem:weekly_day":
        await query.edit_message_text(
            t(lang, "settings.weekly_choose_day"),
            reply_markup=keyboards.weekly_day_picker_keyboard(lang),
            parse_mode="HTML",
        )
        return WEEKLY

    if data == "rem:back_sub":
        await query.edit_message_text(
            t(lang, "settings.reminders"),
            reply_markup=_reminders_kb(lang, user),
            parse_mode="HTML",
        )
        return REMINDERS

    return REMINDERS


async def tz_region_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    assert query and query.data
    await query.answer()

    user_id, _, lang = await _get_user_lang(update)
    if not user_id:
        return ConversationHandler.END

    if query.data == "tz:UTC":
        await postgres.update_user(user_id, timezone="UTC")
        user = await postgres.get_user(user_id)
        if user and user["weekly_summary_toggle"]:
            scheduler.schedule_weekly_summary(user_id, "telegram", user["weekly_summary_day"], tz="UTC")
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
    user = await postgres.get_user(user_id)
    if user and user["weekly_summary_toggle"]:
        scheduler.schedule_weekly_summary(user_id, "telegram", user["weekly_summary_day"], tz=tz_name)
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
    user = await postgres.get_user(user_id)
    if user and user["weekly_summary_toggle"]:
        scheduler.schedule_weekly_summary(user_id, "telegram", user["weekly_summary_day"], tz=tz_text)
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
    if data.startswith("weekly:day:"):
        day = int(data.split(":")[2])
        await postgres.update_user(user_id, weekly_summary_day=day)
        if user["weekly_summary_toggle"]:
            scheduler.schedule_weekly_summary(user_id, "telegram", day, tz=user.get("timezone") or "UTC")
        user = await postgres.get_user(user_id)
        assert user is not None
        await query.edit_message_text(
            t(lang, "settings.reminders"),
            reply_markup=_reminders_kb(lang, user),
            parse_mode="HTML",
        )
        return REMINDERS

    # back → reminders submenu
    await query.edit_message_text(
        t(lang, "settings.reminders"),
        reply_markup=_reminders_kb(lang, user),
        parse_mode="HTML",
    )
    return REMINDERS


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
            REMINDERS: [
                CallbackQueryHandler(reminders_callback, pattern=r"^rem:"),
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
                CallbackQueryHandler(weekly_callback, pattern=r"^weekly:"),
            ],
            EMOTIONS: [
                CallbackQueryHandler(emotions_callback, pattern=r"^echoose:"),
            ],
        },
        fallbacks=[CommandHandler("settings", settings_command)],
        per_message=False,
    )
