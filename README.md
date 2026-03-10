# Feelinq

Telegram bot that tracks your mood over time using the [Russell circumplex model of affect](https://doi.org/10.1037/h0077714). It periodically asks how you feel, maps your emotions to valence/arousal coordinates, and generates charts of your trends.

## Setup

Requires Python 3.12+, PostgreSQL, and InfluxDB 2.x.

```sh
cp .env.example .env   # fill in TELEGRAM_BOT_TOKEN, DB credentials
pip install .
feelinq                # or: python -m feelinq.main
```

### Container deployment (Podman Quadlet)

```sh
cp quadlet/*.container ~/.config/containers/systemd/
systemctl --user daemon-reload
systemctl --user start feelinq.service
```

## Commands

| Command | Description |
|---------|-------------|
| `/start` | Onboarding (language, timezone) |
| `/settings` | Reminder window, timezone, language, weekly summary |
| `/stats` | Mood charts (valence, arousal, circumplex, frequency, heatmap) |
| `/help` | How the bot works |
| `/feedback <text>` | Send feedback to admins |

## Configuration

All via environment variables (see `.env.example`):

- `TELEGRAM_BOT_TOKEN` — from BotFather
- `POSTGRES_DSN` — asyncpg connection string
- `INFLUX_URL`, `INFLUX_TOKEN`, `INFLUX_ORG`, `INFLUX_BUCKET`
- `ADMIN_USER_IDS` — comma-separated Telegram chat IDs
- `WEBHOOK_URL` — optional; uses polling if absent
- `LOG_LEVEL` — `DEBUG` or `INFO`
