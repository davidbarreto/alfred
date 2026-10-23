import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.features.metrics.entries.service import STALE_AFTER
from app.features.metrics.series.repository import MetricSeriesRepository
from app.features.metrics.stats.repository import GroupBy, MetricStatsRepository, StatRow
from app.features.metrics.stats.schemas import MIN_SAMPLES, TREND_DAYS, GroupStat, MetricStats, MetricTrend

logger = logging.getLogger(__name__)

_WEEKDAYS = {"1": "Mon", "2": "Tue", "3": "Wed", "4": "Thu", "5": "Fri", "6": "Sat", "7": "Sun"}
_WEATHER_ORDER = {"dry": 0, "rain": 1, "unknown": 2}
_MAX_DURATION_S = int(STALE_AFTER.total_seconds())


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _label(group_by: GroupBy | None, key: str | None) -> str:
    if key is None:
        return "All"
    if group_by == "hour":
        return f"{int(key):02d}:00"
    if group_by == "weekday":
        return _WEEKDAYS.get(key, key)
    if group_by == "weather":
        return key.capitalize()
    return key


def _group_stat(row: StatRow, group_by: GroupBy | None, measured: bool) -> GroupStat:
    """Build a GroupStat; count series have no measure, so only `n` is meaningful there."""
    return GroupStat(
        key=row.key if row.key is not None else "all",
        label=_label(group_by, row.key),
        n=row.n,
        median=row.median if measured else None,
        p90=row.p90 if measured else None,
        mean=row.mean if measured else None,
        min=row.min if measured else None,
        max=row.max if measured else None,
        low_confidence=row.n < MIN_SAMPLES,
    )


def _best(groups: list[GroupStat]) -> GroupStat | None:
    """The fastest/lowest group among those with enough samples; needs at least two to be a comparison."""
    eligible = [g for g in groups if not g.low_confidence and g.median is not None]
    if len(eligible) < 2:
        return None
    return min(eligible, key=lambda g: g.median)  # type: ignore[arg-type, return-value]


class MetricStatsService:
    def __init__(self, session: AsyncSession):
        self._repo = MetricStatsRepository(session)
        self._series = MetricSeriesRepository(session)

    async def get_stats(self, name: str, tag: str | None = None, days: int | None = None) -> MetricStats | None:
        series = await self._series.get_series_by_name(name)
        if series is None:
            logger.debug("Metric stats: series=%r not found", name)
            return None
        kind = series.kind
        measured = kind != "count"
        tz = get_settings().timezone
        now = _now()
        since = now - timedelta(days=days) if days else None

        async def grouped(group_by: GroupBy) -> list[GroupStat]:
            rows = await self._repo.get_stats(
                series.id, kind, tz, _MAX_DURATION_S, group_by=group_by, since=since, tag=tag
            )
            return [_group_stat(row, group_by, measured) for row in rows]

        async def overall(window_since: datetime | None, window_until: datetime | None = None) -> GroupStat:
            rows = await self._repo.get_stats(
                series.id, kind, tz, _MAX_DURATION_S, since=window_since, until=window_until, tag=tag
            )
            return _group_stat(rows[0], None, measured)

        by_tag = sorted(await grouped("tag"), key=lambda g: (-g.n, g.label))
        by_hour = sorted(await grouped("hour"), key=lambda g: int(g.key))
        by_weekday = sorted(await grouped("weekday"), key=lambda g: int(g.key))
        by_weather = sorted(await grouped("weather"), key=lambda g: _WEATHER_ORDER.get(g.key, 9))
        trend_start = now - timedelta(days=TREND_DAYS)
        trend = MetricTrend(
            days=TREND_DAYS,
            recent=await overall(trend_start),
            previous=await overall(now - timedelta(days=2 * TREND_DAYS), trend_start),
        )
        excluded = await self._repo.count_over_cap(series.id, _MAX_DURATION_S, since) if kind == "duration" else 0
        logger.debug("Metric stats: series=%r kind=%s tag=%r days=%s", series.name, kind, tag, days)
        return MetricStats(
            series=series.name,
            kind=kind,
            unit=series.unit,
            sample_threshold=MIN_SAMPLES,
            excluded_over_cap=excluded,
            overall=await overall(since),
            by_tag=by_tag,
            by_hour=by_hour,
            by_weekday=by_weekday,
            by_weather=by_weather,
            trend=trend,
            best_tag=_best(by_tag) if kind == "duration" else None,
            best_hour=_best(by_hour) if kind == "duration" else None,
        )
