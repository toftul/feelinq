# Migration from InfluxDB (v2 bot)

The old bot stored data in InfluxDB 2. The new bot uses TimescaleDB (PostgreSQL).
`scripts/migrate_from_influx.py` migrates a single user's data by Telegram ID.

## What is migrated

| Data | InfluxDB source | TimescaleDB target |
|---|---|---|
| Mood entries | `emotion_measurement` (tag: `user`) | `mood_entry` table |
| Selected emotions | `selected_emotions` (tag: `user`, `emotion`) | `user_settings.extra.emotions` |

Each mood entry carries: timestamp, `mean_valence`, `mean_arousal`, comma-separated `emotions`.
Selected emotions are taken from the **latest** snapshot in `selected_emotions`.

## Requirements

[uv](https://docs.astral.sh/uv/) (no other setup needed — dependencies are declared inline in the script).

## Usage

```bash
# Preview without writing anything
uv run migrate_from_influx.py --telegram-id 63688320 --dry-run

# Apply
uv run migrate_from_influx.py --telegram-id 63688320

# Custom Postgres DSN (default: postgresql://feelinq:feelinq@localhost:5432/feelinq)
uv run migrate_from_influx.py --telegram-id 63688320 --postgres-dsn postgresql://user:pass@host/db

# Inspect InfluxDB measurements (useful for debugging)
uv run migrate_from_influx.py --list-measurements
```

## Running against the Podman deployment

The Postgres container is on an internal Podman network (`systemd-feelinq`) with no host port
mapping. Run the script inside a temporary container on the same network:

```bash
podman run --rm \
  --network systemd-feelinq \
  -v /home/ivan/feelinq/migrate_from_influx.py:/migrate.py:ro \
  python:3.12-slim \
  bash -c "pip install -q influxdb-client asyncpg && \
           python /migrate.py \
             --telegram-id 63688320 \
             --postgres-dsn 'postgresql://feelinq:feelinq@systemd-postgres:5432/feelinq'"
```

## Notes

- Re-running is safe — inserts use `ON CONFLICT DO NOTHING`.
- If the user does not yet exist in `user_settings`, a minimal row is created automatically.
- The old bot stored emotion names in title case ("Excited, Calm"). The script lowercases them
  to match the new catalog keys.
- The old bot allowed selecting all 20 emotions. The new bot enforces a cap of 12. If the
  migrated selection exceeds that, the user will be prompted to pick a new set next time they
  open the emotion picker.
