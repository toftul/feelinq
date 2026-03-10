import logging
from datetime import datetime, timezone

from feelinq.core.emotions import mean_valence_arousal
from feelinq.core import scheduler
from feelinq.db import influx, postgres

log = logging.getLogger(__name__)


async def save_entry(
    user_id: str,
    platform: str,
    platform_id: str,
    emotion_keys: list[str],
) -> tuple[float, float]:
    mean_v, mean_a = mean_valence_arousal(emotion_keys)
    now = datetime.now(timezone.utc)

    await influx.write_mood_entry(
        user_id=user_id,
        platform=platform,
        platform_id=platform_id,
        mean_valence=mean_v,
        mean_arousal=mean_a,
        emotions=emotion_keys,
        timestamp=now,
    )

    user = await postgres.get_user(user_id)
    assert user is not None
    next_fire = scheduler.compute_fire_time(user["due_min_h"], user["due_max_h"])
    await postgres.update_after_entry(user_id, last_entry_at=now, next_reminder_at=next_fire)
    scheduler.reschedule(user_id, platform, next_fire)

    log.info("Saved entry for user %s: v=%.2f a=%.2f emotions=%s", user_id, mean_v, mean_a, emotion_keys)
    return mean_v, mean_a
