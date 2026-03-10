import asyncio
import logging
from datetime import datetime, timezone

from influxdb_client_3 import InfluxDBClient3, Point, WritePrecision

from feelinq.config import settings

log = logging.getLogger(__name__)

_client: InfluxDBClient3 | None = None


def init() -> None:
    global _client
    _client = InfluxDBClient3(
        host=settings.influx_host,
        port=settings.influx_port,
        token=settings.influx_token or None,
        database=settings.influx_database,
    )
    log.info("InfluxDB 3 client initialised")


def close() -> None:
    if _client:
        _client.close()


def _get_client() -> InfluxDBClient3:
    assert _client is not None, "InfluxDB client not initialised"
    return _client


async def write_mood_entry(
    user_id: str,
    platform: str,
    platform_id: str,
    mean_valence: float,
    mean_arousal: float,
    emotions: list[str],
    timestamp: datetime | None = None,
) -> None:
    client = _get_client()
    ts = timestamp or datetime.now(timezone.utc)
    point = (
        Point("mood_entry")
        .tag("user_id", user_id)
        .tag("platform", platform)
        .tag("platform_id", platform_id)
        .field("mean_valence", mean_valence)
        .field("mean_arousal", mean_arousal)
        .field("emotions", ",".join(emotions))
        .time(ts, WritePrecision.NS)
    )
    await asyncio.to_thread(client.write, record=point)
    log.debug("Wrote mood entry for user %s", user_id)


async def query_mood_entries(
    user_id: str,
    range_days: int = 30,
) -> list[dict]:
    client = _get_client()
    query = (
        "SELECT time, mean_valence, mean_arousal, emotions "
        "FROM mood_entry "
        f"WHERE user_id = '{user_id}' "
        f"AND time >= now() - interval '{range_days} days' "
        "ORDER BY time"
    )
    table = await asyncio.to_thread(client.query, query=query, language="sql")
    results = []
    for batch in table.to_batches():
        for row in zip(*[batch.column(name) for name in batch.schema.names]):
            d = dict(zip(batch.schema.names, [v.as_py() for v in row]))
            results.append(d)
    return results


async def count_entries(user_id: str) -> int:
    client = _get_client()
    query = (
        "SELECT COUNT(*) AS cnt FROM mood_entry "
        f"WHERE user_id = '{user_id}'"
    )
    table = await asyncio.to_thread(client.query, query=query, language="sql")
    df = table.to_pandas()
    if df.empty:
        return 0
    return int(df.iloc[0]["cnt"])


async def count_all_entries() -> int:
    client = _get_client()
    query = "SELECT COUNT(*) AS cnt FROM mood_entry"
    table = await asyncio.to_thread(client.query, query=query, language="sql")
    df = table.to_pandas()
    if df.empty:
        return 0
    return int(df.iloc[0]["cnt"])
