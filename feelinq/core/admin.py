from feelinq.db import postgres, timescale


async def get_admin_stats() -> dict:
    total_users = await postgres.get_total_users()
    active_7d = await postgres.get_active_users_last_7d()
    total_entries = await timescale.count_all_entries()
    breakdown = await postgres.get_platform_breakdown()

    return {
        "total_users": total_users,
        "active_7d": active_7d,
        "total_entries": total_entries,
        "platform_breakdown": {r["platform"]: r["cnt"] for r in breakdown},
    }
