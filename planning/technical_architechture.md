# Feelinq bot — Technical Architecture

---

## Project structure

```
feelinq/
├── core/
│   ├── __init__.py
│   ├── emotions.py          # emotion catalog with valence/arousal values
│   ├── i18n.py              # translation loader
│   ├── scheduler.py         # APScheduler setup, reminder scheduling
│   ├── entry_handler.py     # saves mood entry to InfluxDB
│   ├── stats_engine.py      # generates charts
│   └── admin.py             # admin stats helpers
├── db/
│   ├── postgres.py          # user_settings CRUD
│   └── influx.py            # mood entry read/write
├── locales/
│   ├── en.json
│   └── ru.json
├── platforms/
│   └── telegram/
│       ├── __init__.py
│       ├── bot.py           # Application setup, registers all handlers
│       ├── handlers/
│       │   ├── start.py         # /start, onboarding ConversationHandler
│       │   ├── reminder.py      # reminder ConversationHandler (emotion picker)
│       │   ├── settings.py      # /settings ConversationHandler
│       │   ├── stats.py         # /stats handler
│       │   ├── help.py          # /help handler
│       │   └── feedback.py      # /feedback handler
│       └── keyboards.py         # InlineKeyboardMarkup builders
├── config.py                # env var loading (pydantic-settings)
├── main.py                  # entrypoint
├── .env.example
├── quadlet/                 # Podman Quadlet unit files
│   ├── feelinq.container
│   ├── postgres.container
│   └── influxdb.container
└── pyproject.toml
```

---

## Core module

Owns the business logic. Platform modules are thin adapters — they only handle
I/O and call into core.

### Emotion catalog (`core/emotions.py`)

A static list of emotions, each with:
- `key`: short identifier (e.g. `"happy"`)
- `label`: display name (e.g. `"Happy"`)
- `valence`: float in [-1, 1]
- `arousal`: float in [-1, 1]

Example subset (Russell circumplex positions):

| key        | label      | valence | arousal |
|------------|------------|---------|---------|
| excited    | Excited    | +0.8    | +0.8    |
| happy      | Happy      | +0.8    | +0.2    |
| content    | Content    | +0.6    | -0.3    |
| relaxed    | Relaxed    | +0.5    | -0.7    |
| bored      | Bored      | -0.3    | -0.7    |
| sad        | Sad        | -0.7    | -0.4    |
| anxious    | Anxious    | -0.5    | +0.7    |
| angry      | Angry      | -0.8    | +0.8    |
| neutral    | Neutral    | 0.0     | 0.0     |

~16–20 emotions total, covering all four quadrants evenly.

### Scheduler (`core/scheduler.py`)

Uses **APScheduler** (AsyncIOScheduler).

**On startup:** load all users with `reminders_toggle=true` from Postgres. For
each, schedule a fresh one-shot job at:

```
fire_time = now() + random_hours(due_min_h, due_max_h)
```

No attempt is made to recover the pre-restart schedule. Every restart gives
every active user a clean reminder window from the current moment. This is
simple and predictable — a restart never silently skips or immediately spams
a reminder.

**After each saved entry:** cancel the old job for that user, compute a new
`fire_time = now() + random_hours(due_min_h, due_max_h)`, save it to
`next_reminder_at` in Postgres, and schedule the new job.

**When the user changes `due_min_h` / `due_max_h` in settings:** cancel the
current job and reschedule using the new window from `now()`.

The scheduler calls a platform-registered callback — see **Core ↔ Platform
interface** below.

### Entry handler (`core/entry_handler.py`)

```python
async def save_entry(user_id: str, platform: str, platform_id: str, emotion_keys: list[str]) -> MoodEntry:
    emotions = [EMOTION_CATALOG[k] for k in emotion_keys]
    mean_valence = mean(e.valence for e in emotions)
    mean_arousal = mean(e.arousal for e in emotions)
    entry = MoodEntry(user_id, platform, platform_id, mean_valence, mean_arousal, emotion_keys)
    await influx.write(entry)
    next_reminder_at = now() + random_hours(settings.due_min_h, settings.due_max_h)
    await postgres.update_after_entry(user_id, last_entry_at=entry.timestamp, next_reminder_at=next_reminder_at)
    scheduler.reschedule(user_id, fire_at=next_reminder_at)
    return entry
```

### Stats engine (`core/stats_engine.py`)

Queries InfluxDB for a user's history and returns PNG byte buffers.

**Charts generated:**

| Chart | Description |
|---|---|
| Valence over time | Line chart, last 30 days, daily average |
| Arousal over time | Line chart, last 30 days, daily average |
| Circumplex scatter | Russell 2D scatter of all entries; colour = recency |
| Emotion frequency | Horizontal bar chart of top emotions |
| Weekly heatmap | 7-day × N-week grid, cell colour = mean valence |

Library: **matplotlib** (static PNG). Sent as `bot.send_photo(photo=BytesIO(...))`.

Minimum entries required before showing charts: **5** (otherwise show a friendly
"not enough data yet" message).

### Weekly summary

Triggered by a separate APScheduler cron job (per user, fires on
`weekly_summary_day` at 09:00 user-local time).

Sends: short text summary (avg valence/arousal for the week) + circumplex
scatter chart for that week.

### Admin module (`core/admin.py`)

Admins can send `/admin_stats` (hidden from normal /help).

Returns:
- total registered users
- active users last 7 days
- total entries
- platform breakdown

**Admin reconciliation on startup:**

`ADMIN_USER_IDS` is a comma-separated list of Telegram `platform_id` values
(raw Telegram chat IDs). On every bot startup, before the scheduler runs:

```python
async def sync_admins(admin_platform_ids: list[str]):
    # grant admin to anyone in the list who is registered
    await postgres.execute("""
        UPDATE user_settings SET is_admin = (platform_id = ANY($1))
        WHERE platform = 'telegram'
    """, admin_platform_ids)
```

This sets `is_admin=true` for listed IDs and `is_admin=false` for any
previously-granted users no longer in the list. Unregistered IDs in the list
are silently ignored — they will receive admin rights automatically when they
first `/start` the bot.

During runtime, `is_admin` in Postgres is the sole source of truth. The env
var is only read at startup to sync the table.

---

## i18n (`core/i18n.py` + `locales/`)

All user-facing strings live in locale JSON files. The bot never has hardcoded
message text.

### File structure

```
locales/
├── en.json
└── ru.json
```

### JSON schema

Each file is a flat-ish dict with dot-namespaced keys:

```json
{
  "onboarding.welcome":        "Welcome! Choose your language:",
  "onboarding.choose_timezone": "What's your timezone?",
  "onboarding.done":           "You're all set! Your first check-in will arrive in {min}–{max} hours.",

  "reminder.prompt":           "How are you feeling? Pick all that apply 👇",
  "reminder.done_button":      "✅ Done",
  "reminder.saved":            "Saved! 📊 Your mood: {valence} valence, {arousal} arousal",
  "reminder.confirm":          "You selected: {emotions}\nMean valence: {valence}  Mean arousal: {arousal}",

  "settings.title":            "⚙️ Settings",
  "settings.reminder_window":  "Current window: {min}–{max} h after last check-in.\nSet minimum hours (1–23):",

  "stats.not_enough_data":     "Not enough data yet — you need at least 5 check-ins.",

  "help.text":                 "...",
  "feedback.sent":             "Thanks! Your feedback has been sent.",
  "feedback.missing":          "Please add your message: /feedback <text>",
  "errors.use_buttons":        "Please use the buttons 👆",

  "emotions.excited":  "Excited",
  "emotions.happy":    "Happy",
  "emotions.content":  "Content",
  "emotions.relaxed":  "Relaxed",
  "emotions.bored":    "Bored",
  "emotions.sad":      "Sad",
  "emotions.anxious":  "Anxious",
  "emotions.angry":    "Angry",
  "emotions.neutral":  "Neutral"
}
```

Emotion labels are under the `emotions.*` namespace so the same keys are used
when building the keyboard and when formatting the confirmation message.

### Usage (`core/i18n.py`)

```python
_locales: dict[str, dict] = {}

def load_locales(locales_dir: Path):
    for f in locales_dir.glob("*.json"):
        _locales[f.stem] = json.loads(f.read_text())

def t(lang: str, key: str, **kwargs) -> str:
    template = _locales.get(lang, _locales["en"]).get(key) or _locales["en"][key]
    return template.format(**kwargs) if kwargs else template
```

Fallback chain: requested language → English → `KeyError` (caught at startup
to ensure all keys exist in all locale files).

### Adding a new language

Add a new `locales/<code>.json` file with all keys present. The bot picks it
up on restart. Add the language button to the onboarding and settings keyboards.

---

## Core ↔ Platform interface

Each platform registers a `send_reminder` callback with the scheduler:

```python
# platforms/telegram/bot.py
scheduler.register_reminder_callback("telegram", telegram_send_reminder)

async def telegram_send_reminder(user_id: str):
    # resolve internal user_id → platform_id (Telegram chat_id)
    user = await postgres.get_user(user_id)
    await application.bot.send_message(chat_id=user.platform_id, ...)
    # then triggers the reminder ConversationHandler
```

The scheduler only knows about the internal `user_id` + `platform`. It looks
up the right callback by platform name. The platform module is responsible for
resolving `platform_id` from `user_id`. This keeps core decoupled from
Telegram internals.

---

## Databases

### PostgreSQL — user_settings

```sql
CREATE TABLE user_settings (
    user_id               TEXT PRIMARY KEY,  -- bot-generated UUID (internal, never exposed)
    platform              TEXT NOT NULL,     -- 'telegram', 'discord', etc.
    platform_id           TEXT NOT NULL,     -- raw ID from the platform (e.g. Telegram chat_id)
    language              TEXT DEFAULT 'en',
    timezone              TEXT DEFAULT 'UTC',
    due_min_h             INT DEFAULT 4,
    due_max_h             INT DEFAULT 6,
    reminders_toggle      BOOLEAN DEFAULT true,
    weekly_summary_toggle BOOLEAN DEFAULT true,
    weekly_summary_day    INT DEFAULT 0,     -- 0=Monday … 6=Sunday
    is_admin              BOOLEAN DEFAULT false,
    last_entry_at         TIMESTAMPTZ,       -- when the user last submitted an entry
    next_reminder_at      TIMESTAMPTZ,       -- when the next reminder job is scheduled to fire
    extra                 JSONB,             -- future-proof; future use: persisted conversation state
    created_at            TIMESTAMPTZ DEFAULT now(),
    updated_at            TIMESTAMPTZ DEFAULT now(),
    UNIQUE (platform, platform_id)           -- one account per platform identity
);
```

**`user_id`** is a UUID4 generated by the bot on first registration (e.g.
`"a3f2c1d0-8e4b-4f7a-b6c5-1234567890ab"`). Using UUID ensures it never
coincidentally matches any platform's native numeric or string IDs.

**`platform_id`** is the raw identifier from the originating platform (e.g.
Telegram `chat_id` integer as string). Lookups from platform events use
`WHERE platform = $1 AND platform_id = $2` to find the internal `user_id`.

`last_entry_at` — timestamp of the last saved mood entry. NULL = never submitted.
`next_reminder_at` — persists the scheduled fire time so it is visible in
settings and can be shown to the user ("next check-in in ~3 h").

### InfluxDB — mood entries

- **Bucket:** `feelinq`
- **Measurement:** `mood_entry`
- **Tags:** `user_id` (internal UUID), `platform`, `platform_id`
- **Fields:** `mean_valence` (float), `mean_arousal` (float), `emotions` (string, comma-separated)
- **Timestamp:** UTC

Example line protocol:
```
mood_entry,user_id=a3f2c1d0-8e4b-4f7a-b6c5-1234567890ab,platform=telegram,platform_id=123456 mean_valence=0.65,mean_arousal=0.2,emotions="happy,content" 1741600000000000000
```

Queries are always by internal `user_id`. `platform` and `platform_id` are
carried as tags for debugging and potential cross-platform analytics.

---

## Telegram platform

Uses **python-telegram-bot v20+** (async, Application builder pattern).

**Deployment:** polling during development; webhook in production (set via
`application.run_webhook()`). Parse mode: **HTML** throughout.

### BotFather command list

```
start     - Set up your account
settings  - Change your preferences
stats     - View your mood charts
help      - How the bot works
feedback  - Send feedback to the team
```

---

### Handler table

| Handler | Trigger | Notes |
|---|---|---|
| `/start` | any time | Entry to onboarding ConversationHandler |
| `/settings` | any time | Settings ConversationHandler |
| `/stats` | any time | Calls stats engine, sends photos |
| `/help` | any time | Static message + circumplex image |
| `/feedback <text>` | any time | Forwards to all admins |
| `/admin_stats` | admins only | Usage stats |
| Reminder flow | scheduler fires | Reminder ConversationHandler |
| Fallback text | during active conv | "Please use the buttons" |

---

### Onboarding ConversationHandler (`/start`)

On first `/start`: generate a UUID4 `user_id`, store alongside `platform="telegram"`
and `platform_id=<Telegram chat_id>` in Postgres. Set `is_admin=true` if this
`platform_id` is present in `ADMIN_USER_IDS`.

Re-entrant: running `/start` again jumps to settings if user already exists.

```
State LANGUAGE:
  Bot: "Welcome! Choose your language:"
  Keyboard: [🇬🇧 English] [🇷🇺 Русский] (extend as needed)
  → save language to DB
  → all subsequent onboarding messages are sent in the selected language

State TIMEZONE:
  Bot: "What's your timezone?"
  Keyboard: region buttons (Europe, Americas, Asia, Africa, Pacific, UTC)
  → tapping a region shows cities in that region (or user can type a city name)
  → on valid tz selected: save to DB

State DONE:
  Bot: short explainer about the Russell model + how reminders work
  "You're all set! Your first check-in will arrive in {due_min_h}–{due_max_h} hours."
  → schedule first reminder
  → END
```

---

### Reminder ConversationHandler

Triggered by scheduler calling `telegram_send_reminder`, which sends the
opening message and sets the conversation state.

```
State EMOTION_SELECT:
  Bot sends:
    "How are you feeling? Pick all that apply 👇"
    + InlineKeyboardMarkup (emotion grid, see below)
    + "✅ Done" button (disabled / greyed label until ≥1 emotion selected)

  On emotion button tap:
    → toggle selection in user session data (selected = set stored in context.user_data)
    → edit_message_reply_markup to redraw keyboard with ✅ on selected items
    → if first selection: replace "Done" button label to active style

State CONFIRM:
  User taps Done → bot edits message to:
    "You selected: Happy, Excited
     Mean valence: +0.7  Mean arousal: +0.6
     [💾 Save]  [🔄 Reset]"

  On Save:
    → call core.entry_handler.save_entry(...)
    → bot sends: "Saved! 📊 Your mood: +0.7 valence, +0.6 arousal"
    → END

  On Reset:
    → clear selection, return to EMOTION_SELECT state, redraw picker

Timeout (4 h):
  → silently expire (ConversationHandler.TIMEOUT or job-based)
  → no message sent to user
```

**Emotion grid layout** (4 columns, ~4–5 rows):

Each button label: `"Happy"` when unselected, `"✅ Happy"` when selected.
Buttons are arranged roughly by circumplex quadrant (high-arousal top,
low-arousal bottom; positive-valence left, negative-valence right).

---

### Settings ConversationHandler (`/settings`)

```
SETTINGS_MENU:
  Bot: "⚙️ Settings" + inline keyboard:
    [🔔 Reminder window]
    [🌍 Timezone]
    [🌐 Language]
    [📊 Weekly summary]
    [❌ Close]

REMINDER_WINDOW:
  Bot: "Current window: 4–6 h after last check-in.
        Set minimum hours (1–23):"
  User sends a number → validate → ask for max hours → save both → back to menu

TIMEZONE:
  Same region→city flow as onboarding
  → save → back to menu

LANGUAGE:
  Keyboard with language options → save → back to menu

WEEKLY_SUMMARY:
  Bot: "Weekly summary is currently ON/OFF" + inline:
    [Toggle ON/OFF]
    [Change day: Mon Tue Wed Thu Fri Sat Sun]
  → save → back to menu
```

---

### /stats handler

1. Fetch user settings (timezone, language).
2. Call `stats_engine.generate_all(user_id, platform)`.
3. If < 5 entries: reply with text only.
4. Otherwise: send a **media group** (up to 10 images) or sequential
   `send_photo` calls, each with a short caption.

---

### /help handler

Static reply (HTML-formatted) explaining:
- The Russell circumplex model (brief)
- How to read valence/arousal
- Bot commands list
- Link or inline image of the 2D circumplex diagram

---

### /feedback handler

`/feedback <text>` — inline (no conversation needed).

- Validate that text is provided.
- Forward to all users where `is_admin=true`, prefixed with:
  `"📬 Feedback from user {user_id}:\n\n{text}"`
- Reply to user: "Thanks! Your feedback has been sent."

---

### Error / edge cases

| Situation | Handling |
|---|---|
| User sends text during emotion picker | Reply: "Please use the buttons 👆" (auto-delete after 5s optional) |
| User opens two reminder sessions | Second trigger is ignored if a session is already active (check context.user_data) |
| Unknown /command | Ignore or reply "Unknown command. Use /help." |
| DB unavailable at startup | Log and exit; systemd restarts via Quadlet |
| InfluxDB write failure | Log error, notify user "Could not save, try again" |
| Bot restarts mid-conversation | Conversation state is intentionally reset; user must restart the flow. Future improvement: persist state in `extra` JSONB and restore on startup. |

---

## Configuration (`config.py`)

All secrets and tunables via environment variables (loaded with `pydantic-settings`):

```
TELEGRAM_BOT_TOKEN
POSTGRES_DSN          # postgresql+asyncpg://...
INFLUX_URL
INFLUX_TOKEN
INFLUX_ORG
INFLUX_BUCKET
ADMIN_USER_IDS        # comma-separated Telegram platform_ids; synced to is_admin on startup
WEBHOOK_URL           # optional; polling used if absent
LOG_LEVEL             # DEBUG / INFO
```

---

## Deployment

Uses **Podman Quadlet** — the systemd-native way to run Podman containers.
Each service is declared as a `.container` unit file under `quadlet/` and
managed by systemd directly (no daemon, rootless by default).

**Unit files:**

| File | Service |
|---|---|
| `feelinq.container` | the bot application |
| `postgres.container` | PostgreSQL |
| `influxdb.container` | InfluxDB |

Each `.container` file specifies the image, env file, volumes, and
`After=` / `Requires=` dependencies so systemd starts them in order.

**Deployment steps:**

```sh
# copy unit files to the user's Quadlet directory
cp quadlet/*.container ~/.config/containers/systemd/

# reload systemd and start
systemctl --user daemon-reload
systemctl --user start feelinq.service
```

- **Logging**: stdout → `journald` via systemd; query with `journalctl --user -u feelinq.service`.
- **Restarts**: `Restart=on-failure` in the unit file.
- On restart, scheduler reloads all users from Postgres and reschedules jobs.

---

## Platforms (future)

### Discord
*(to be designed)*

### WhatsApp
*(to be designed)*
