from datetime import datetime
from typing import Literal, NamedTuple

from sqlalchemy import Float, case, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import ColumnElement

from app.features.metrics.entries.tables import MetricEntry
from app.features.metrics.tags.tables import MetricTag, metric_entry_tag_links

GroupBy = Literal["hour", "weekday", "weather", "tag"]

# Rain starts at this much precipitation (mm) in the weather snapshot taken at the start of an entry.
_RAIN_MM = 0.1


class StatRow(NamedTuple):
    key: str | None
    n: int
    median: float | None
    p90: float | None
    mean: float | None
    min: float | None
    max: float | None


def _float(value: object) -> float | None:
    return None if value is None else float(value)  # type: ignore[arg-type]


class MetricStatsRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    @staticmethod
    def _measure(kind: str) -> ColumnElement:
        """What is aggregated: seconds for a duration series, the stored number otherwise."""
        if kind == "duration":
            return cast(func.extract("epoch", MetricEntry.ended_at - MetricEntry.started_at), Float)
        return cast(MetricEntry.value, Float)

    @staticmethod
    def _group_expression(group_by: GroupBy, timezone: str) -> ColumnElement:
        local_start = func.timezone(timezone, MetricEntry.started_at)
        if group_by == "hour":
            return func.extract("hour", local_start)
        if group_by == "weekday":
            return func.extract("isodow", local_start)
        if group_by == "tag":
            return func.lower(MetricTag.name)
        precipitation = MetricEntry.context["start"]["precipitation_mm"].astext.cast(Float)
        return case((precipitation.is_(None), "unknown"), (precipitation < _RAIN_MM, "dry"), else_="rain")

    def _filters(
        self,
        series_id: int,
        kind: str,
        max_duration_s: int,
        since: datetime | None,
        until: datetime | None,
        tag: str | None,
    ) -> list[ColumnElement]:
        conditions: list[ColumnElement] = [MetricEntry.series_id == series_id, MetricEntry.status == "closed"]
        if kind == "duration":
            conditions.append(self._measure(kind) <= max_duration_s)
        if since is not None:
            conditions.append(MetricEntry.started_at >= since)
        if until is not None:
            conditions.append(MetricEntry.started_at < until)
        if tag is not None:
            tagged = (
                select(metric_entry_tag_links.c.entry_id)
                .join(MetricTag, MetricTag.id == metric_entry_tag_links.c.tag_id)
                .where(func.lower(MetricTag.name) == tag.lower())
            )
            conditions.append(MetricEntry.id.in_(tagged))
        return conditions

    async def get_stats(
        self,
        series_id: int,
        kind: str,
        timezone: str,
        max_duration_s: int,
        group_by: GroupBy | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        tag: str | None = None,
    ) -> list[StatRow]:
        """Aggregates over closed entries, optionally grouped. Without `group_by` the result is one row."""
        measure = self._measure(kind)
        key = self._group_expression(group_by, timezone) if group_by else None
        columns = [
            func.count().label("n"),
            func.percentile_cont(0.5).within_group(measure),
            func.percentile_cont(0.9).within_group(measure),
            func.avg(measure),
            func.min(measure),
            func.max(measure),
        ]
        stmt = select(*([key] if key is not None else []), *columns).select_from(MetricEntry)
        if group_by == "tag":
            stmt = stmt.join(metric_entry_tag_links, metric_entry_tag_links.c.entry_id == MetricEntry.id).join(
                MetricTag, MetricTag.id == metric_entry_tag_links.c.tag_id
            )
        stmt = stmt.where(*self._filters(series_id, kind, max_duration_s, since, until, tag))
        if key is not None:
            stmt = stmt.group_by(key)
        rows = (await self._session.execute(stmt)).all()
        result = []
        for row in rows:
            raw_key, values = (row[0], row[1:]) if key is not None else (None, row)
            n, median, p90, mean, low, high = values
            result.append(
                StatRow(
                    key=None if raw_key is None else str(int(raw_key)) if group_by in ("hour", "weekday") else str(raw_key),
                    n=int(n),
                    median=_float(median),
                    p90=_float(p90),
                    mean=_float(mean),
                    min=_float(low),
                    max=_float(high),
                )
            )
        return result

    async def count_over_cap(self, series_id: int, max_duration_s: int, since: datetime | None = None) -> int:
        """Closed duration entries that are longer than the cap, and so excluded from `get_stats`."""
        stmt = select(func.count()).select_from(MetricEntry).where(
            MetricEntry.series_id == series_id,
            MetricEntry.status == "closed",
            self._measure("duration") > max_duration_s,
        )
        if since is not None:
            stmt = stmt.where(MetricEntry.started_at >= since)
        return int(await self._session.scalar(stmt) or 0)
