import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.metrics.entries.durations import format_duration
from app.features.metrics.entries.repository import MetricEntryRepository
from app.features.metrics.entries.schemas import (
    MetricActionResult,
    MetricEntryCreate,
    MetricEntryFilters,
    MetricEntryRead,
    MetricEntryUpdate,
    MetricLog,
    MetricStart,
    MetricStop,
)
from app.features.metrics.entries.tables import MetricEntry
from app.features.metrics.series.repository import MetricSeriesRepository
from app.features.metrics.series.tables import MetricSeries
from app.shared.weather import ConditionsProvider

logger = logging.getLogger(__name__)

# One global cap: an open entry older than this is "stale" and a closed one longer than this is
# not trusted by the stats (a forgotten stop must never become a 14-hour commute).
STALE_AFTER = timedelta(hours=6)
_WEATHER_TIMEOUT_S = 4.0


class MetricKindMismatchError(Exception):
    def __init__(self, series: str, actual: str, expected: str):
        super().__init__(f"Series {series!r} is a {actual} series; this action needs a {expected} series")


class MetricSeriesNotFoundError(Exception):
    """No series with that name."""


class MetricSeriesArchivedError(Exception):
    """The series is archived; unarchive it before recording new entries."""


class MetricNothingRunningError(Exception):
    def __init__(self, series: str | None):
        super().__init__(f"Nothing running for {series}" if series else "Nothing running")


class MetricAmbiguousStopError(Exception):
    def __init__(self, series_names: list[str]):
        super().__init__(f"Several timers are running ({', '.join(series_names)}); say which series to stop")


class MetricStaleEntryError(Exception):
    def __init__(self, entry_id: int):
        super().__init__(
            f"Entry {entry_id} would last over {STALE_AFTER // timedelta(hours=1)} h; "
            "backdate the stop with --ago or discard it"
        )


class MetricInvalidEntryError(Exception):
    """The entry's fields don't fit its series kind or are inconsistent."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _tag_suffix(tags: list[str]) -> str:
    return f" [{', '.join(tags)}]" if tags else ""


class MetricEntryService:
    def __init__(self, session: AsyncSession, conditions: ConditionsProvider | None = None):
        self._repo = MetricEntryRepository(session)
        self._series = MetricSeriesRepository(session)
        self._conditions = conditions

    # --- reads -------------------------------------------------------------------------------

    async def get_entry(self, entry_id: int) -> MetricEntryRead | None:
        entry = await self._repo.get_entry(entry_id)
        return self._to_read(entry, _now()) if entry else None

    async def get_entries(self, filters: MetricEntryFilters) -> list[MetricEntryRead]:
        series_id = None
        if filters.series is not None:
            series = await self._series.get_series_by_name(filters.series.strip().lower())
            if series is None:
                return []
            series_id = series.id
        entries = await self._repo.get_entries(
            series_id=series_id,
            tag=filters.tag,
            status=filters.status,
            since=filters.since,
            until=filters.until,
            limit=filters.limit,
            offset=filters.offset,
        )
        now = _now()
        return [self._to_read(e, now) for e in entries]

    async def get_open_entries(self) -> list[MetricEntryRead]:
        now = _now()
        return [self._to_read(e, now) for e in await self._repo.get_open_entries()]

    # --- recording ---------------------------------------------------------------------------

    async def start(self, data: MetricStart, source: str) -> MetricActionResult:
        series, created = await self._resolve_series(data.series, "duration")
        discarded_ids: list[int] = []
        for open_entry in await self._repo.get_open_entries(series.id):
            await self._repo.update_entry(open_entry.id, {"status": "discarded"})
            discarded_ids.append(open_entry.id)

        snapshot = await self._snapshot(data.lat, data.lon)
        entry = await self._repo.create_entry(
            {
                "series_id": series.id,
                "started_at": _now(),
                "status": "open",
                "source": source,
                "start_lat": data.lat,
                "start_lon": data.lon,
                "start_accuracy_m": data.accuracy_m,
                "context": {"start": snapshot} if snapshot else None,
                "note": data.note,
            },
            data.tags,
        )
        logger.info("Metric started: entry_id=%d series=%r discarded=%s", entry.id, series.name, discarded_ids)
        message = f"Started {series.name}{_tag_suffix(data.tags)}"
        if created:
            message += f" (new series '{series.name}' created)"
        if discarded_ids:
            message += f"; discarded the previous unfinished entry #{discarded_ids[0]}"
        return MetricActionResult(
            message=message,
            entry=self._to_read(entry, _now()),
            series_created=created,
            discarded_entry_id=discarded_ids[0] if discarded_ids else None,
        )

    async def stop(self, data: MetricStop, source: str) -> MetricActionResult:
        if data.series is not None:
            series = await self._series.get_series_by_name(data.series)
            if series is None:
                raise MetricNothingRunningError(data.series)
            open_entries = await self._repo.get_open_entries(series.id)
        else:
            open_entries = await self._repo.get_open_entries()
        if not open_entries:
            raise MetricNothingRunningError(data.series)
        if data.series is None and len(open_entries) > 1:
            raise MetricAmbiguousStopError([e.series_name for e in open_entries])

        entry = open_entries[0]
        ended_at = _now() - timedelta(seconds=data.ago_s or 0)
        if ended_at < entry.started_at:
            raise MetricInvalidEntryError("The stop time would be before the start; use a smaller --ago")
        if ended_at - entry.started_at > STALE_AFTER:
            raise MetricStaleEntryError(entry.id)

        snapshot = await self._snapshot(data.lat, data.lon)
        context = {**(entry.context or {}), "end": snapshot} if snapshot else entry.context
        entry_id, series_name = entry.id, entry.series_name
        updated = await self._repo.update_entry(
            entry_id,
            {
                "ended_at": ended_at,
                "status": "closed",
                "end_lat": data.lat,
                "end_lon": data.lon,
                "end_accuracy_m": data.accuracy_m,
                "context": context,
            },
        )
        assert updated is not None
        read = self._to_read(updated, _now())
        logger.info("Metric stopped: entry_id=%d series=%r source=%s", entry_id, series_name, source)
        assert read.duration_s is not None
        return MetricActionResult(
            message=f"Stopped {series_name}: {format_duration(read.duration_s)}{_tag_suffix(read.tags)}",
            entry=read,
        )

    async def log(self, data: MetricLog, source: str) -> MetricActionResult:
        kind = "value" if data.value is not None else "count"
        series, created = await self._resolve_series(data.series, kind)
        if data.unit and data.unit != series.unit:
            series = await self._series.update_series(series.id, {"unit": data.unit}) or series
            logger.info("Metric series unit set: id=%d name=%r", series.id, series.name)
        snapshot = await self._snapshot(data.lat, data.lon)
        entry = await self._repo.create_entry(
            {
                "series_id": series.id,
                "started_at": _now(),
                "value": data.value if kind == "value" else 1,
                "status": "closed",
                "source": source,
                "start_lat": data.lat,
                "start_lon": data.lon,
                "start_accuracy_m": data.accuracy_m,
                "context": {"start": snapshot} if snapshot else None,
                "note": data.note,
            },
            data.tags,
        )
        logger.info("Metric logged: entry_id=%d series=%r kind=%s", entry.id, series.name, kind)
        message = f"Logged {series.name}"
        if kind == "value":
            message += f": {data.value:g}{' ' + series.unit if series.unit else ''}"
        message += _tag_suffix(data.tags)
        if created:
            message += f" (new series '{series.name}' created)"
        return MetricActionResult(message=message, entry=self._to_read(entry, _now()), series_created=created)

    # --- manual maintenance ------------------------------------------------------------------

    async def create_entry(self, data: MetricEntryCreate, source: str = "portal") -> MetricEntryRead:
        series = await self._series.get_series_by_name(data.series)
        if series is None:
            raise MetricSeriesNotFoundError(data.series)
        fields = self._validated_fields(series.kind, data.started_at, data.ended_at, data.value)
        entry = await self._repo.create_entry(
            {**fields, "series_id": series.id, "source": source, "note": data.note}, data.tags
        )
        logger.info("Metric entry created: entry_id=%d series=%r source=%s", entry.id, series.name, source)
        return self._to_read(entry, _now())

    async def update_entry(self, entry_id: int, data: MetricEntryUpdate) -> MetricEntryRead | None:
        entry = await self._repo.get_entry(entry_id)
        if entry is None:
            logger.debug("Metric entry update: id=%d not found", entry_id)
            return None
        changes = {k: v for k, v in data.model_dump(exclude_unset=True).items() if v is not None}
        tags = changes.pop("tags", None)
        merged = self._validated_fields(
            entry.series_kind,
            changes.get("started_at", entry.started_at),
            changes.get("ended_at", entry.ended_at),
            changes.get("value", entry.value),
            status=entry.status,
        )
        fields = {k: merged[k] for k in ("started_at", "ended_at", "value", "status") if k in changes or k == "status"}
        if "note" in changes:
            fields["note"] = changes["note"]
        updated = await self._repo.update_entry(entry_id, fields, tags)
        assert updated is not None
        logger.info("Metric entry updated: entry_id=%d fields=%s", entry_id, list(changes))
        return self._to_read(updated, _now())

    async def discard_entry(self, entry_id: int) -> MetricEntryRead | None:
        entry = await self._repo.get_entry(entry_id)
        if entry is None:
            logger.debug("Metric entry discard: id=%d not found", entry_id)
            return None
        if entry.status != "discarded":
            entry = await self._repo.update_entry(entry_id, {"status": "discarded"})
            assert entry is not None
            logger.info("Metric entry discarded: entry_id=%d", entry_id)
        return self._to_read(entry, _now())

    # --- helpers -----------------------------------------------------------------------------

    async def _resolve_series(self, name: str, kind: str) -> tuple[MetricSeries, bool]:
        series = await self._series.get_series_by_name(name)
        if series is None:
            series = await self._series.create_series(name, kind)
            logger.info("Metric series auto-created: id=%d name=%r kind=%s", series.id, series.name, kind)
            return series, True
        if series.is_archived:
            raise MetricSeriesArchivedError(f"Series {name!r} is archived; unarchive it first")
        if series.kind != kind:
            raise MetricKindMismatchError(name, series.kind, kind)
        return series, False

    async def _snapshot(self, lat: float | None, lon: float | None) -> dict[str, Any] | None:
        """Best-effort weather at this moment; a failure or timeout must never block a start/stop."""
        if self._conditions is None:
            return None
        try:
            snapshot = await asyncio.wait_for(
                self._conditions.get_current_conditions(lat, lon), timeout=_WEATHER_TIMEOUT_S
            )
        except Exception as exc:
            logger.warning("Metric weather snapshot failed: %s", exc)
            return None
        if snapshot is None:
            return None
        return {**snapshot.model_dump(), "location_source": "default" if lat is None else "device"}

    @staticmethod
    def _validated_fields(
        kind: str, started_at: datetime, ended_at: datetime | None, value: float | None, status: str | None = None
    ) -> dict[str, Any]:
        """Check the fields fit the series kind and return the columns to write."""
        if kind == "duration":
            if value is not None:
                raise MetricInvalidEntryError("A duration entry has no value")
            if ended_at is None and status is None:
                raise MetricInvalidEntryError("A duration entry needs an end time")
        else:
            if ended_at is not None:
                raise MetricInvalidEntryError(f"A {kind} entry has no end time")
            if kind == "value" and value is None:
                raise MetricInvalidEntryError("A value entry needs a value")
            value = 1 if kind == "count" and value is None else value
        if ended_at is not None and ended_at < started_at:
            raise MetricInvalidEntryError("The end time is before the start time")
        if status == "discarded":
            new_status = "discarded"
        elif kind == "duration" and ended_at is None:
            new_status = "open"
        else:
            new_status = "closed"
        return {"started_at": started_at, "ended_at": ended_at, "value": value, "status": new_status}

    @staticmethod
    def _to_read(entry: MetricEntry, now: datetime) -> MetricEntryRead:
        read = MetricEntryRead.model_validate(entry)
        read.is_stale = entry.status == "open" and now - entry.started_at > STALE_AFTER
        return read
