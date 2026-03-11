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

Requires TimescaleDB (PostgreSQL with the TimescaleDB extension). The bot creates all tables and hypertables automatically on startup.

### Container deployment (Podman Quadlet)

The primary deployment method. Runs the bot and TimescaleDB as rootless Podman containers managed by systemd.

- The database and user are created automatically by the official TimescaleDB image.
- The TimescaleDB extension and hypertables are set up by the bot on startup.
- The env file lives at `~/.config/feelinq/.env` (XDG convention), keeping secrets out of the source tree.
- Inside the shared `feelinq.network`, the container is reachable as `systemd-postgres`. **Do not use `localhost`** in the env file.

```sh
# Build the bot image
podman build -t feelinq:latest .

# Set up the env file
mkdir -p ~/.config/feelinq
cp .env.example ~/.config/feelinq/.env
# Edit ~/.config/feelinq/.env and fill in TELEGRAM_BOT_TOKEN

# Create persistent data directories
mkdir -p ~/feelinq-data/postgres

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
```

### Running locally (development)

Requires Python 3.12+, [uv](https://docs.astral.sh/uv/), and TimescaleDB running separately.

1. Create the PostgreSQL database:
   ```sql
   CREATE USER feelinq WITH PASSWORD 'feelinq';
   CREATE DATABASE feelinq OWNER feelinq;
   ```

2. Start the bot:
   ```sh
   cp .env.example .env
   # Edit .env: set TELEGRAM_BOT_TOKEN, and switch DB host to localhost (see comments in the file)
   uv sync
   uv run feelinq
   ```

The bot will create the `user_settings` table and `mood_entry` hypertable automatically on startup.

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
| `ADMIN_USER_IDS` | Comma-separated Telegram chat IDs for admin access | *(empty)* |
| `LOG_LEVEL` | `DEBUG` or `INFO` | `INFO` |
