import logging
from datetime import datetime, timezone

from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.influxdb_client_async import InfluxDBClientAsync

from feelinq.config import settings

log = logging.getLogger(__name__)

_client: InfluxDBClientAsync | None = None


async def init() -> None:
    global _client
    _client = InfluxDBClientAsync(
        url=settings.influx_url,
        token=settings.influx_token,
        org=settings.influx_org,
    )
    log.info("InfluxDB async client initialised")


async def close() -> None:
    if _client:
        await _client.close()


def _get_client() -> InfluxDBClientAsync:
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
    write_api = client.write_api()
    await write_api.write(bucket=settings.influx_bucket, record=point)
    log.debug("Wrote mood entry for user %s", user_id)


async def query_mood_entries(
    user_id: str,
    range_days: int = 30,
) -> list[dict]:
    client = _get_client()
    query = f'''
    from(bucket: "{settings.influx_bucket}")
      |> range(start: -{range_days}d)
      |> filter(fn: (r) => r._measurement == "mood_entry")
      |> filter(fn: (r) => r.user_id == "{user_id}")
      |> pivot(rowKey: ["_time"], columnKey: ["_field"], valueColumn: "_value")
      |> sort(columns: ["_time"])
    '''
    query_api = client.query_api()
    tables = await query_api.query(query)
    results = []
    for table in tables:
        for record in table.records:
            results.append({
                "time": record.get_time(),
                "mean_valence": record.values.get("mean_valence"),
                "mean_arousal": record.values.get("mean_arousal"),
                "emotions": record.values.get("emotions", ""),
            })
    return results


async def count_entries(user_id: str) -> int:
    client = _get_client()
    query = f'''
    from(bucket: "{settings.influx_bucket}")
      |> range(start: -365d)
      |> filter(fn: (r) => r._measurement == "mood_entry")
      |> filter(fn: (r) => r.user_id == "{user_id}")
      |> filter(fn: (r) => r._field == "mean_valence")
      |> count()
      |> yield(name: "count")
    '''
    query_api = client.query_api()
    tables = await query_api.query(query)
    for table in tables:
        for record in table.records:
            return int(record.get_value())
    return 0


async def count_all_entries() -> int:
    client = _get_client()
    query = f'''
    from(bucket: "{settings.influx_bucket}")
      |> range(start: -365d)
      |> filter(fn: (r) => r._measurement == "mood_entry")
      |> filter(fn: (r) => r._field == "mean_valence")
      |> count()
      |> sum()
    '''
    query_api = client.query_api()
    tables = await query_api.query(query)
    for table in tables:
        for record in table.records:
            return int(record.get_value())
    return 0
