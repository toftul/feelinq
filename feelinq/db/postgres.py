import uuid
import logging
from datetime import datetime

import asyncpg

from feelinq.config import settings

log = logging.getLogger(__name__)

_pool: asyncpg.Pool | None = None

SCHEMA = """\
CREATE TABLE IF NOT EXISTS user_settings (
    user_id               TEXT PRIMARY KEY,
    platform              TEXT NOT NULL,
    platform_id           TEXT NOT NULL,
    language              TEXT DEFAULT 'en',
    timezone              TEXT DEFAULT 'UTC',
    due_min_h             REAL DEFAULT 4,
    due_max_h             REAL DEFAULT 6,
    reminders_toggle      BOOLEAN DEFAULT true,
    weekly_summary_toggle BOOLEAN DEFAULT true,
    weekly_summary_day    INT DEFAULT 0,
    is_admin              BOOLEAN DEFAULT false,
    last_entry_at         TIMESTAMPTZ,
    next_reminder_at      TIMESTAMPTZ,
    extra                 JSONB,
    created_at            TIMESTAMPTZ DEFAULT now(),
    updated_at            TIMESTAMPTZ DEFAULT now(),
    UNIQUE (platform, platform_id)
);
"""


async def init() -> None:
    global _pool
    _pool = await asyncpg.create_pool(settings.postgres_dsn, min_size=2, max_size=10)
    async with _pool.acquire() as conn:
        await conn.execute(SCHEMA)
    log.info("PostgreSQL pool initialised")


async def close() -> None:
    if _pool:
        await _pool.close()


def _get_pool() -> asyncpg.Pool:
    assert _pool is not None, "Database pool not initialised"
    return _pool


async def get_user_by_platform(platform: str, platform_id: str) -> asyncpg.Record | None:
    pool = _get_pool()
    return await pool.fetchrow(
        "SELECT * FROM user_settings WHERE platform = $1 AND platform_id = $2",
        platform, platform_id,
    )


async def get_user(user_id: str) -> asyncpg.Record | None:
    pool = _get_pool()
    return await pool.fetchrow("SELECT * FROM user_settings WHERE user_id = $1", user_id)


async def create_user(platform: str, platform_id: str, language: str = "en") -> asyncpg.Record:
    pool = _get_pool()
    user_id = str(uuid.uuid4())
    is_admin = platform_id in settings.admin_ids_list
    await pool.execute(
        """INSERT INTO user_settings (user_id, platform, platform_id, language, is_admin)
           VALUES ($1, $2, $3, $4, $5)""",
        user_id, platform, platform_id, language, is_admin,
    )
    return await get_user(user_id)  # type: ignore[return-value]


async def update_user(user_id: str, **fields: object) -> None:
    pool = _get_pool()
    sets = ", ".join(f"{k} = ${i+2}" for i, k in enumerate(fields))
    sets += ", updated_at = now()"
    await pool.execute(
        f"UPDATE user_settings SET {sets} WHERE user_id = $1",
        user_id, *fields.values(),
    )


async def update_after_entry(
    user_id: str,
    last_entry_at: datetime,
    next_reminder_at: datetime,
) -> None:
    await update_user(
        user_id,
        last_entry_at=last_entry_at,
        next_reminder_at=next_reminder_at,
    )


async def get_all_active_users() -> list[asyncpg.Record]:
    pool = _get_pool()
    return await pool.fetch(
        "SELECT * FROM user_settings WHERE reminders_toggle = true"
    )


async def get_admins() -> list[asyncpg.Record]:
    pool = _get_pool()
    return await pool.fetch("SELECT * FROM user_settings WHERE is_admin = true")


async def sync_admins(admin_platform_ids: list[str]) -> None:
    pool = _get_pool()
    await pool.execute(
        """UPDATE user_settings
           SET is_admin = (platform_id = ANY($1::text[])),
               updated_at = now()
           WHERE platform = 'telegram'""",
        admin_platform_ids,
    )
    log.info("Admin sync complete for %d platform IDs", len(admin_platform_ids))


async def get_total_users() -> int:
    pool = _get_pool()
    return await pool.fetchval("SELECT COUNT(*) FROM user_settings")


async def get_active_users_last_7d() -> int:
    pool = _get_pool()
    return await pool.fetchval(
        "SELECT COUNT(*) FROM user_settings WHERE last_entry_at > now() - interval '7 days'"
    )


async def get_platform_breakdown() -> list[asyncpg.Record]:
    pool = _get_pool()
    return await pool.fetch(
        "SELECT platform, COUNT(*) as cnt FROM user_settings GROUP BY platform"
    )
