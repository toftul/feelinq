from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from feelinq.core.emotions import (
    EMOTION_CATALOG,
    QUADRANT_LABELS,
    emotions_by_quadrant,
    make_grid,
    validate_emotion_selection,
    MIN_USER_EMOTIONS,
    MAX_USER_EMOTIONS,
)
from feelinq.core.i18n import t

# Timezone regions and representative cities
TIMEZONE_REGIONS: dict[str, list[tuple[str, str]]] = {
    "Europe": [
        ("Europe/London", "London (GMT)"),
        ("Europe/Berlin", "Berlin (CET)"),
        ("Europe/Moscow", "Moscow (MSK)"),
        ("Europe/Istanbul", "Istanbul"),
        ("Europe/Kyiv", "Kyiv"),
        ("Europe/Warsaw", "Warsaw"),
        ("Europe/Rome", "Rome"),
        ("Europe/Paris", "Paris"),
    ],
    "Americas": [
        ("America/New_York", "New York (ET)"),
        ("America/Chicago", "Chicago (CT)"),
        ("America/Denver", "Denver (MT)"),
        ("America/Los_Angeles", "Los Angeles (PT)"),
        ("America/Sao_Paulo", "São Paulo"),
        ("America/Toronto", "Toronto"),
        ("America/Mexico_City", "Mexico City"),
    ],
    "Asia": [
        ("Asia/Dubai", "Dubai"),
        ("Asia/Kolkata", "Kolkata"),
        ("Asia/Bangkok", "Bangkok"),
        ("Asia/Shanghai", "Shanghai"),
        ("Asia/Tokyo", "Tokyo"),
        ("Asia/Seoul", "Seoul"),
        ("Asia/Singapore", "Singapore"),
    ],
    "Africa": [
        ("Africa/Cairo", "Cairo"),
        ("Africa/Lagos", "Lagos"),
        ("Africa/Nairobi", "Nairobi"),
        ("Africa/Johannesburg", "Johannesburg"),
    ],
    "Pacific": [
        ("Pacific/Auckland", "Auckland"),
        ("Australia/Sydney", "Sydney"),
        ("Australia/Melbourne", "Melbourne"),
        ("Pacific/Honolulu", "Honolulu"),
    ],
}


def language_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("English", callback_data="lang:en"),
            InlineKeyboardButton("Русский", callback_data="lang:ru"),
        ],
    ])


def timezone_regions_keyboard() -> InlineKeyboardMarkup:
    rows = []
    for region in TIMEZONE_REGIONS:
        rows.append([InlineKeyboardButton(region, callback_data=f"tz_region:{region}")])
    rows.append([InlineKeyboardButton("UTC", callback_data="tz:UTC")])
    return InlineKeyboardMarkup(rows)


def timezone_cities_keyboard(region: str) -> InlineKeyboardMarkup:
    cities = TIMEZONE_REGIONS.get(region, [])
    rows = []
    for tz_name, label in cities:
        rows.append([InlineKeyboardButton(label, callback_data=f"tz:{tz_name}")])
    rows.append([InlineKeyboardButton("« Back", callback_data="tz_back")])
    return InlineKeyboardMarkup(rows)


def emotion_picker_keyboard(
    lang: str,
    selected: set[str],
    emotion_keys: list[str] | None = None,
) -> InlineKeyboardMarkup:
    grid = make_grid(emotion_keys) if emotion_keys else make_grid(list(EMOTION_CATALOG.keys()))
    rows = []
    for row_keys in grid:
        buttons = []
        for key in row_keys:
            label = t(lang, f"emotions.{key}")
            if key in selected:
                label = f"✅ {label}"
            buttons.append(InlineKeyboardButton(label, callback_data=f"emo:{key}"))
        rows.append(buttons)
    # Done button
    if selected:
        done_label = t(lang, "reminder.done_button")
    else:
        done_label = t(lang, "reminder.done_button_disabled")
    rows.append([InlineKeyboardButton(done_label, callback_data="emo:done")])
    return InlineKeyboardMarkup(rows)


def emotion_chooser_keyboard(lang: str, selected: set[str]) -> InlineKeyboardMarkup:
    """Keyboard for choosing which emotions to track (onboarding / settings)."""
    rows: list[list[InlineKeyboardButton]] = []
    by_q = emotions_by_quadrant()

    for q_key, q_label in QUADRANT_LABELS.items():
        # Section header (non-clickable)
        rows.append([InlineKeyboardButton(f"— {t(lang, f'quadrant.{q_key}')} —", callback_data="echoose:_noop")])
        keys = by_q[q_key]
        for row_keys in make_grid(keys):
            buttons = []
            for key in row_keys:
                label = t(lang, f"emotions.{key}")
                if key in selected:
                    label = f"✅ {label}"
                buttons.append(InlineKeyboardButton(label, callback_data=f"echoose:{key}"))
            rows.append(buttons)

    # Done button with count
    error = validate_emotion_selection(selected)
    count = len(selected)
    if error:
        done_label = t(lang, "emotions_chooser.count", count=count, min=MIN_USER_EMOTIONS, max=MAX_USER_EMOTIONS)
    else:
        done_label = t(lang, "emotions_chooser.done_button", count=count)
    rows.append([InlineKeyboardButton(done_label, callback_data="echoose:done")])
    return InlineKeyboardMarkup(rows)


def settings_menu_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(t(lang, "settings.emotions"), callback_data="set:emotions")],
        [InlineKeyboardButton(t(lang, "settings.reminders"), callback_data="set:reminders")],
        [InlineKeyboardButton(t(lang, "settings.timezone"), callback_data="set:tz")],
        [InlineKeyboardButton(t(lang, "settings.language"), callback_data="set:lang")],
        [InlineKeyboardButton(t(lang, "settings.close"), callback_data="set:close")],
    ])


CHECKIN_WINDOWS = [(1, 3), (3, 5), (4, 6), (6, 12), (12, 24)]


def _fmt_hours(v: float) -> str:
    return str(int(v)) if v == int(v) else str(v)


def reminders_submenu_keyboard(
    lang: str,
    reminders_on: bool,
    weekly_on: bool,
    due_min: float,
    due_max: float,
    weekly_day: int,
) -> InlineKeyboardMarkup:
    all_on = reminders_on and weekly_on
    all_label = t(lang, "settings.all_reminders_on") if all_on else t(lang, "settings.all_reminders_off")
    checkin_label = t(lang, "settings.checkin_on") if reminders_on else t(lang, "settings.checkin_off")
    weekly_label = t(lang, "settings.weekly_on") if weekly_on else t(lang, "settings.weekly_off")

    rows: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(all_label, callback_data="rem:toggle")],
        [InlineKeyboardButton(checkin_label, callback_data="rem:toggle_checkin")],
    ]
    if reminders_on:
        window_label = t(lang, "settings.checkin_window", min=_fmt_hours(due_min), max=_fmt_hours(due_max))
        rows.append([InlineKeyboardButton(window_label, callback_data="rem:checkin")])
    rows.append([InlineKeyboardButton(weekly_label, callback_data="rem:toggle_weekly")])
    if weekly_on:
        day_label = t(lang, "settings.weekly_day_label", day=t(lang, f"days.{weekly_day}"))
        rows.append([InlineKeyboardButton(day_label, callback_data="rem:weekly_day")])
    rows.append([InlineKeyboardButton(t(lang, "settings.back"), callback_data="rem:back")])
    return InlineKeyboardMarkup(rows)


def checkin_window_keyboard(lang: str, current_min: float, current_max: float) -> InlineKeyboardMarkup:
    rows = []
    for min_h, max_h in CHECKIN_WINDOWS:
        label = t(lang, "settings.hours_range", min=min_h, max=max_h)
        if min_h == current_min and max_h == current_max:
            label = f"✅ {label}"
        rows.append([InlineKeyboardButton(label, callback_data=f"rem:w:{min_h}:{max_h}")])
    rows.append([InlineKeyboardButton(t(lang, "settings.back"), callback_data="rem:back_sub")])
    return InlineKeyboardMarkup(rows)


def weekly_day_picker_keyboard(lang: str) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(t(lang, "settings.weekly_choose_day"), callback_data="_noop")],
    ]
    day_buttons = []
    for i in range(7):
        day_buttons.append(InlineKeyboardButton(t(lang, f"days.{i}")[:3], callback_data=f"weekly:day:{i}"))
    rows.append(day_buttons)
    rows.append([InlineKeyboardButton(t(lang, "settings.back"), callback_data="weekly:back")])
    return InlineKeyboardMarkup(rows)
