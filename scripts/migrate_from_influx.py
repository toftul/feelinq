#!/usr/bin/env python3
# /// script
# requires-python = ">=3.12"
# dependencies = ["influxdb-client", "asyncpg"]
# ///
"""
Migrate mood entries from InfluxDB (old bot) to TimescaleDB (new bot).

Usage:
    uv run migrate_from_influx.py --telegram-id 123456789
    uv run migrate_from_influx.py --telegram-id 123456789 --dry-run
    uv run migrate_from_influx.py --telegram-id 123456789 --list-measurements
"""

import argparse
import asyncio
import json
import sys
import uuid
from datetime import datetime, timezone

import asyncpg
from influxdb_client import InfluxDBClient

INFLUX_URL    = "http://alma:8086"
INFLUX_ORG    = "home"
INFLUX_BUCKET = "howwasyourday"
INFLUX_TOKEN  = "FjwSYV0T4mf_GpUbQKH3A0hsWgX-eOl7WvvkPPCWCLxAu1g4uH4QSKxKGTr7sAXeKQhAxrMmnBwVMR4rYyMkqQ=="

POSTGRES_DSN = "postgresql://feelinq:feelinq@localhost:5432/feelinq"


def get_influx_client() -> InfluxDBClient:
    return InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG)


def list_measurements(client: InfluxDBClient) -> list[str]:
    flux = f'''
import "influxdata/influxdb/schema"
schema.measurements(bucket: "{INFLUX_BUCKET}")
'''
    tables = client.query_api().query(flux)
    return [row.values["_value"] for table in tables for row in table.records]


def _parse_emotions(raw: str) -> list[str]:
    """Convert old-style emotion strings to lowercase keys used by the new bot."""
    if not raw:
        return []
    if raw.startswith("["):
        parts = json.loads(raw)
    else:
        parts = [e.strip() for e in raw.split(",") if e.strip()]
    return [p.lower() for p in parts]


def query_mood_entries(client: InfluxDBClient, telegram_id: str) -> list[dict]:
    """
    Returns all mood entries for the user, pivoted so each timestamp is one dict:
      {time, emotions, mean_valence, mean_arousal}
    """
    flux = f'''
from(bucket: "{INFLUX_BUCKET}")
  |> range(start: 1970-01-01T00:00:00Z)
  |> filter(fn: (r) => r._measurement == "emotion_measurement")
  |> filter(fn: (r) => r.user == "{telegram_id}")
  |> pivot(rowKey: ["_time"], columnKey: ["_field"], valueColumn: "_value")
'''
    tables = client.query_api().query(flux)

    results: list[dict] = []
    for table in tables:
        for rec in table.records:
            v = rec.values
            results.append({
                "time":         rec.get_time(),
                "emotions":     _parse_emotions(v.get("emotions") or ""),
                "mean_valence": float(v.get("mean_valence") or 0.0),
                "mean_arousal": float(v.get("mean_arousal") or 0.0),
            })

    return sorted(results, key=lambda r: r["time"])


def query_selected_emotions(client: InfluxDBClient, telegram_id: str) -> list[str]:
    """
    The old bot stored each selected emotion as a separate row with tag `emotion`
    and field `value=1`. We take the latest timestamp where value=1 as the
    current selection.
    """
    # Get the most recent timestamp for this user
    flux_last = f'''
from(bucket: "{INFLUX_BUCKET}")
  |> range(start: 1970-01-01T00:00:00Z)
  |> filter(fn: (r) => r._measurement == "selected_emotions")
  |> filter(fn: (r) => r.user == "{telegram_id}")
  |> filter(fn: (r) => r._field == "value")
  |> last()
  |> keep(columns: ["_time", "emotion", "_value"])
'''
    tables = client.query_api().query(flux_last)
    selected = []
    for table in tables:
        for rec in table.records:
            if rec.get_value() == 1:
                emotion = rec.values.get("emotion", "")
                if emotion:
                    selected.append(emotion.lower())
    return selected


async def get_or_create_user(conn: asyncpg.Connection, telegram_id: str) -> asyncpg.Record:
    row = await conn.fetchrow(
        "SELECT * FROM user_settings WHERE platform = 'telegram' AND platform_id = $1",
        telegram_id,
    )
    if row:
        return row
    user_id = str(uuid.uuid4())
    await conn.execute(
        """INSERT INTO user_settings (user_id, platform, platform_id)
           VALUES ($1, 'telegram', $2)
           ON CONFLICT (platform, platform_id) DO NOTHING""",
        user_id, telegram_id,
    )
    return await conn.fetchrow(
        "SELECT * FROM user_settings WHERE platform = 'telegram' AND platform_id = $1",
        telegram_id,
    )  # type: ignore[return-value]


async def count_existing_entries(conn: asyncpg.Connection, user_id: str) -> int:
    return await conn.fetchval(
        "SELECT COUNT(*) FROM mood_entry WHERE user_id = $1", user_id
    )


async def migrate(telegram_id: str, dry_run: bool, postgres_dsn: str) -> None:
    print(f"\n=== Migration for Telegram ID: {telegram_id} ===")
    print(f"Mode: {'DRY RUN' if dry_run else 'LIVE'}\n")

    print("Connecting to InfluxDB...")
    with get_influx_client() as influx:
        entries = query_mood_entries(influx, telegram_id)
        selected_emotions = query_selected_emotions(influx, telegram_id)

    if not entries:
        print("No mood entries found in InfluxDB for this Telegram ID.")
        return

    print(f"Found {len(entries)} mood entries in InfluxDB.")
    print(f"Date range: {entries[0]['time']} → {entries[-1]['time']}")
    print(f"Selected emotions (latest): {selected_emotions or '(none found)'}")

    print("\nEntries preview:")
    for i, e in enumerate(entries[:5]):
        print(f"  [{i+1}] {e['time']}  v={e['mean_valence']:+.3f}  "
              f"a={e['mean_arousal']:+.3f}  {e['emotions']}")
    if len(entries) > 5:
        print(f"  ... and {len(entries) - 5} more")

    if dry_run:
        print("\n[DRY RUN] No changes written. Re-run without --dry-run to apply.")
        return

    print("\nConnecting to PostgreSQL...")

    conn = await asyncpg.connect(postgres_dsn)
    await conn.set_type_codec(
        "jsonb", encoder=json.dumps, decoder=json.loads,
        schema="pg_catalog", format="text",
    )
    try:
        user = await get_or_create_user(conn, telegram_id)
        user_id: str = user["user_id"]
        print(f"PostgreSQL user_id: {user_id} (existing: {user['created_at'] != user['updated_at'] or True})")

        existing = await count_existing_entries(conn, user_id)
        print(f"Existing mood entries in TimescaleDB: {existing}")

        print(f"Inserting {len(entries)} mood entries...")
        inserted = 0
        for e in entries:
            ts: datetime = e["time"]
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            await conn.execute(
                """INSERT INTO mood_entry
                       (time, user_id, platform, platform_id, mean_valence, mean_arousal, emotions, timezone)
                   VALUES ($1, $2, 'telegram', $3, $4, $5, $6, NULL)
                   ON CONFLICT DO NOTHING""",
                ts, user_id, telegram_id,
                e["mean_valence"], e["mean_arousal"],
                ",".join(e["emotions"]),
            )
            inserted += 1

        print(f"  Inserted {inserted} entries.")

        if selected_emotions:
            row = await conn.fetchrow(
                "SELECT extra FROM user_settings WHERE user_id = $1", user_id
            )
            extra = (row["extra"] if row and row["extra"] else {}) or {}
            if isinstance(extra, str):
                extra = json.loads(extra)
            extra["emotions"] = selected_emotions
            await conn.execute(
                "UPDATE user_settings SET extra = $2, updated_at = now() WHERE user_id = $1",
                user_id, json.dumps(extra),
            )
            print(f"  Set selected emotions: {selected_emotions}")

        print("\nMigration complete!")

    finally:
        await conn.close()


async def list_measurements_cmd() -> None:
    print(f"Measurements in bucket '{INFLUX_BUCKET}':")
    with get_influx_client() as influx:
        for m in list_measurements(influx):
            print(f"  - {m}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate InfluxDB → TimescaleDB mood data")
    parser.add_argument("--telegram-id", "-t")
    parser.add_argument("--dry-run", "-n", action="store_true")
    parser.add_argument("--postgres-dsn", default=POSTGRES_DSN)
    parser.add_argument("--list-measurements", action="store_true")
    args = parser.parse_args()

    if args.list_measurements:
        asyncio.run(list_measurements_cmd())
        return

    if not args.telegram_id:
        parser.error("--telegram-id is required unless --list-measurements is used")

    asyncio.run(migrate(
        telegram_id=args.telegram_id,
        dry_run=args.dry_run,
        postgres_dsn=args.postgres_dsn,
    ))


if __name__ == "__main__":
    main()
