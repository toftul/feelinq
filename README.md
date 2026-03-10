# Feelinq

Chat bot that tracks your mood over time using the [Russell circumplex model of affect](https://doi.org/10.1037/h0077714). It periodically asks how you feel, maps your emotions to valence/arousal coordinates, and generates charts of your trends. Currently supports only Telegram interface. 

## Emotion theory

The brain has two independent neurophysiological systems for affect, making emotional states inherently two-dimensional ([Colibazzi et al., 2010](https://doi.org/10.1037/a0018484); [Posner et al., 2009](https://doi.org/10.1037/h0077714)). Feelinq uses the **Russell circumplex model** ([Russell, 1980](https://doi.org/10.1037/h0077714)):

- **Valence** (x-axis): pleasant (+1) to unpleasant (−1)
- **Arousal** (y-axis): energised (+1) to calm (−1)

Examples: *Excited* = high valence, high arousal; *Relaxed* = high valence, low arousal; *Angry* = low valence, high arousal; *Bored* = low valence, low arousal.

When multiple emotions are selected, the bot stores their mean valence and arousal — a single point on the circumplex representing your overall state for that entry.

## Setup

Requires Python 3.12+, PostgreSQL, and InfluxDB 3 Core.

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
- `INFLUX_HOST`, `INFLUX_PORT`, `INFLUX_TOKEN`, `INFLUX_DATABASE`
- `ADMIN_USER_IDS` — comma-separated Telegram chat IDs
- `WEBHOOK_URL` — optional; uses polling if absent
- `LOG_LEVEL` — `DEBUG` or `INFO`
