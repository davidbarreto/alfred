from typing import Annotated

from fastapi import Query
from pydantic import BaseModel

from app.features.metrics.series.schemas import SeriesKind

# A group with fewer samples than this is returned but flagged, and never ranked as "best".
MIN_SAMPLES = 5
TREND_DAYS = 30


class GroupStat(BaseModel):
    """Aggregates of one group. Percentiles are null for count series (there is nothing to measure)."""

    key: str
    label: str
    n: int
    median: float | None = None
    p90: float | None = None
    mean: float | None = None
    min: float | None = None
    max: float | None = None
    low_confidence: bool = False


class MetricTrend(BaseModel):
    days: int
    recent: GroupStat
    previous: GroupStat


class MetricStats(BaseModel):
    series: str
    kind: SeriesKind
    unit: str | None
    sample_threshold: int
    # Closed duration entries longer than the stale cap: kept in the database, left out of every number here.
    excluded_over_cap: int
    overall: GroupStat
    by_tag: list[GroupStat]
    by_hour: list[GroupStat]
    by_weekday: list[GroupStat]
    by_weather: list[GroupStat]
    trend: MetricTrend
    best_tag: GroupStat | None = None
    best_hour: GroupStat | None = None


class MetricStatsFilters:
    def __init__(
        self,
        tag: Annotated[str | None, Query()] = None,
        days: Annotated[int | None, Query(ge=1, le=3650)] = None,
    ):
        self.tag = tag
        self.days = days
