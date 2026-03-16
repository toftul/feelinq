import logging
from datetime import datetime, timezone

from feelinq.db.postgres import _get_pool

log = logging.getLogger(__name__)


async def ensure_schema() -> None:
    pool = _get_pool()
    async with pool.acquire() as conn:
        await conn.execute("CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;")
        await conn.execute("""\
            CREATE TABLE IF NOT EXISTS mood_entry (
                time         TIMESTAMPTZ      NOT NULL,
                user_id      TEXT             NOT NULL,
                platform     TEXT             NOT NULL,
                platform_id  TEXT             NOT NULL,
                mean_valence DOUBLE PRECISION NOT NULL,
                mean_arousal DOUBLE PRECISION NOT NULL,
                emotions     TEXT             NOT NULL
            );
        """)
        await conn.execute(
            "SELECT create_hypertable('mood_entry', 'time', if_not_exists => TRUE);"
        )
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_mood_entry_user_time "
            "ON mood_entry (user_id, time DESC);"
        )
    log.info("TimescaleDB mood_entry hypertable ready")


async def write_mood_entry(
    user_id: str,
    platform: str,
    platform_id: str,
    mean_valence: float,
    mean_arousal: float,
    emotions: list[str],
    timestamp: datetime | None = None,
) -> None:
    pool = _get_pool()
    ts = timestamp or datetime.now(timezone.utc)
    await pool.execute(
        "INSERT INTO mood_entry (time, user_id, platform, platform_id, "
        "mean_valence, mean_arousal, emotions) VALUES ($1, $2, $3, $4, $5, $6, $7)",
        ts, user_id, platform, platform_id,
        mean_valence, mean_arousal, ",".join(emotions),
    )
    log.debug("Wrote mood entry for user %s", user_id)


async def query_mood_entries(
    user_id: str,
    range_days: int | None = 30,
) -> list[dict]:
    pool = _get_pool()
    if range_days is None:
        rows = await pool.fetch(
            "SELECT time, mean_valence, mean_arousal, emotions "
            "FROM mood_entry "
            "WHERE user_id = $1 "
            "ORDER BY time",
            user_id,
        )
    else:
        rows = await pool.fetch(
            "SELECT time, mean_valence, mean_arousal, emotions "
            "FROM mood_entry "
            "WHERE user_id = $1 AND time >= now() - make_interval(days => $2) "
            "ORDER BY time",
            user_id, range_days,
        )
    return [dict(r) for r in rows]


async def count_entries(user_id: str) -> int:
    pool = _get_pool()
    return await pool.fetchval(
        "SELECT COUNT(*) FROM mood_entry WHERE user_id = $1", user_id
    )


async def count_all_entries() -> int:
    pool = _get_pool()
    return await pool.fetchval("SELECT COUNT(*) FROM mood_entry")
