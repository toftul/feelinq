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

Requires PostgreSQL and InfluxDB 3 Core. The bot creates its PostgreSQL tables automatically on startup. InfluxDB uses schema-on-write, so no table setup is needed — only the database must exist.

### Option 1: From scratch

#### Run locally

Requires Python 3.12+, [uv](https://docs.astral.sh/uv/), and both databases running separately.

1. Create the PostgreSQL database:
   ```sql
   CREATE USER feelinq WITH PASSWORD 'feelinq';
   CREATE DATABASE feelinq OWNER feelinq;
   ```

2. Create the InfluxDB database:
   ```sh
   influxdb3 create database feelinq
   ```

3. Start the bot:
   ```sh
   cp .env.example .env   # fill in TELEGRAM_BOT_TOKEN and DB credentials
   uv sync
   uv run feelinq
   ```

#### Container deployment (Podman Quadlet)

Runs the bot, PostgreSQL, and InfluxDB as rootless Podman containers managed by systemd. PostgreSQL database is created automatically by the official image. InfluxDB database is created automatically via the quadlet entrypoint script.

The env file lives at `~/.config/feelinq/.env` (XDG convention), keeping secrets separate from the source tree.

```sh
# Build the bot image
podman build -t feelinq:latest .

# Set up the env file (separate from project to keep secrets out of the repo)
mkdir -p ~/.config/feelinq
cp .env.example ~/.config/feelinq/.env  # fill in TELEGRAM_BOT_TOKEN

# Create dirs
mkdir -p ~/.config/containers/systemd 
mkdir -p ~/feelinq-data/influx
mkdir -p ~/feelinq-data/postgres

# Install quadlet units and network
cp quadlet/*.container quadlet/*.network ~/.config/containers/systemd/
systemctl --user daemon-reload
systemctl --user start feelinq.service
```

### Option 2: With existing databases

If you already have PostgreSQL and InfluxDB running, just point the bot at them:

1. Make sure the PostgreSQL database exists and is accessible with the credentials you provide.

2. Make sure the InfluxDB database exists:
   ```sh
   influxdb3 create database feelinq   # safe to run if it already exists
   ```

3. Configure and start:
   ```sh
   cp .env.example .env
   # Set POSTGRES_DSN to your existing PostgreSQL instance
   # Set INFLUX_HOST, INFLUX_PORT, INFLUX_TOKEN to your existing InfluxDB instance
   uv sync
   uv run feelinq
   ```

The bot will create the `user_settings` table in PostgreSQL if it doesn't exist and start writing mood entries to InfluxDB immediately.

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

| Variable | Description | Default |
|----------|-------------|---------|
| `TELEGRAM_BOT_TOKEN` | Bot token from [@BotFather](https://t.me/BotFather) | **required** |
| `POSTGRES_DSN` | PostgreSQL connection string (`postgresql://user:pass@host:port/db`) | `postgresql://feelinq:feelinq@localhost:5432/feelinq` |
| `INFLUX_HOST` | InfluxDB hostname | `localhost` |
| `INFLUX_PORT` | InfluxDB port | `8181` |
| `INFLUX_TOKEN` | InfluxDB auth token; leave empty if running without authentication | *(empty)* |
| `INFLUX_DATABASE` | InfluxDB database name | `feelinq` |
| `ADMIN_USER_IDS` | Comma-separated Telegram chat IDs for admin access | *(empty)* |
| `LOG_LEVEL` | `DEBUG` or `INFO` | `INFO` |
