# Feelinq

Chat bot that tracks your mood over time using the [Russell circumplex model of affect](https://doi.org/10.1037/h0077714). It periodically asks how you feel, maps your emotions to valence/arousal coordinates, and generates charts of your trends. Currently supports only Telegram interface. 

## Emotion theory

The brain has two independent neurophysiological systems for affect, making emotional states inherently two-dimensional ([Colibazzi et al., 2010](https://doi.org/10.1037/a0018484); [Posner et al., 2009](https://doi.org/10.1037/h0077714)). Feelinq uses the **Russell circumplex model** ([Russell, 1980](https://doi.org/10.1037/h0077714)):

- **Valence** (x-axis): pleasant (+1) to unpleasant (−1)
- **Arousal** (y-axis): energised (+1) to calm (−1)

Examples: *Excited* = high valence, high arousal; *Relaxed* = high valence, low arousal; *Angry* = low valence, high arousal; *Bored* = low valence, low arousal.

When multiple emotions are selected, the bot stores their mean valence and arousal — a single point on the circumplex representing your overall state for that entry.

![Russell circumplex model of affect](docs/images/russel_map.png)

## Setup

Requires PostgreSQL and InfluxDB 3 Core. You can run everything locally or use containers.

### Option 1: Run locally

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/). PostgreSQL and InfluxDB must be running separately.

```sh
cp .env.example .env   # fill in TELEGRAM_BOT_TOKEN, DB credentials
uv sync
uv run feelinq
```

### Option 2: Container deployment (Podman Quadlet)

Runs the bot, PostgreSQL, and InfluxDB as rootless Podman containers managed by systemd.

```sh
# Build the bot image
podman build -t feelinq:latest .

# Set up the env file
mkdir -p ~/.config/feelinq
cp .env.example ~/.config/feelinq/.env  # fill in TELEGRAM_BOT_TOKEN

# Install and start the quadlet units
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
- `LOG_LEVEL` — `DEBUG` or `INFO`
