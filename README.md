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

### Container deployment (Podman Quadlet)

The primary deployment method. Runs the bot, PostgreSQL, and InfluxDB as rootless Podman containers managed by systemd.

- PostgreSQL database and user are created automatically by the official image.
- InfluxDB runs without authentication; its database is created automatically via `ExecStartPost` after the container starts.
- The env file lives at `~/.config/feelinq/.env` (XDG convention), keeping secrets out of the source tree.
- Inside the shared `feelinq.network`, containers reach each other by their systemd-assigned names: `systemd-postgres` and `systemd-influxdb`. **Do not use `localhost`** for these in the env file.

```sh
# Build the bot image
podman build -t feelinq:latest .

# Set up the env file
mkdir -p ~/.config/feelinq
cp .env.example ~/.config/feelinq/.env
# Edit ~/.config/feelinq/.env and fill in TELEGRAM_BOT_TOKEN

# Create persistent data directories
mkdir -p ~/feelinq-data/influx ~/feelinq-data/postgres

# Install quadlet units
mkdir -p ~/.config/containers/systemd
cp quadlet/*.container quadlet/*.network ~/.config/containers/systemd/

# Reload systemd and start
systemctl --user daemon-reload
systemctl --user start feelinq.service
```

Check status:

```sh
systemctl --user status feelinq.service
systemctl --user status postgres.service
systemctl --user status influxdb.service
```

### Running locally (development)

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
   cp .env.example .env
   # Edit .env: set TELEGRAM_BOT_TOKEN, and switch DB hosts to localhost (see comments in the file)
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
| `POSTGRES_DSN` | PostgreSQL connection string (`postgresql://user:pass@host:port/db`) | `postgresql://feelinq:feelinq@systemd-postgres:5432/feelinq` (Quadlet); `localhost` for local dev |
| `INFLUX_HOST` | InfluxDB hostname | `systemd-influxdb` (Quadlet); `localhost` for local dev |
| `INFLUX_PORT` | InfluxDB port | `8181` |
| `INFLUX_TOKEN` | InfluxDB auth token; leave empty if running without authentication | *(empty)* |
| `INFLUX_DATABASE` | InfluxDB database name | `feelinq` |
| `ADMIN_USER_IDS` | Comma-separated Telegram chat IDs for admin access | *(empty)* |
| `LOG_LEVEL` | `DEBUG` or `INFO` | `INFO` |
