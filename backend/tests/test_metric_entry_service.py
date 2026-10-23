from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest

from app.features.metrics.entries import service as svc
from app.features.metrics.entries.schemas import (
    MetricEntryCreate,
    MetricEntryFilters,
    MetricEntryUpdate,
    MetricLog,
    MetricStart,
    MetricStop,
)
from app.features.metrics.entries.service import (
    MetricAmbiguousStopError,
    MetricEntryService,
    MetricInvalidEntryError,
    MetricKindMismatchError,
    MetricNothingRunningError,
    MetricSeriesArchivedError,
    MetricSeriesNotFoundError,
    MetricStaleEntryError,
)
from app.features.metrics.entries.tables import MetricEntry
from app.features.metrics.series.tables import MetricSeries
from app.features.metrics.tags.tables import MetricTag
from app.shared.weather import WeatherSnapshot

NOW = datetime(2026, 10, 21, 9, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _frozen_now(monkeypatch):
    monkeypatch.setattr(svc, "_now", lambda: NOW)


def _series(name="commute-work", kind="duration", id=1, archived=False, unit=None) -> MetricSeries:
    return MetricSeries(id=id, name=name, kind=kind, unit=unit, is_archived=archived, created_at=NOW, updated_at=NOW)


def _entry(series=None, id=10, started=NOW - timedelta(minutes=30), ended=None, status="open", value=None, tags=(), **kw):
    series = series or _series()
    return MetricEntry(
        id=id,
        series_id=series.id,
        series=series,
        started_at=started,
        ended_at=ended,
        value=value,
        status=status,
        source="telegram",
        tags=[MetricTag(id=i, name=t) for i, t in enumerate(tags)],
        context=kw.get("context"),
        created_at=NOW,
        updated_at=NOW,
    )


@pytest.fixture
def make_service():
    def _make(conditions=None):
        service = MetricEntryService(AsyncMock(), conditions)
        service._repo = AsyncMock()
        service._series = AsyncMock()
        return service

    return _make


class TestStart:
    async def test_creates_series_on_first_use(self, make_service):
        service = make_service()
        service._series.get_series_by_name.return_value = None
        service._series.create_series.return_value = _series()
        service._repo.get_open_entries.return_value = []
        service._repo.create_entry.return_value = _entry(tags=["bus"])

        result = await service.start(MetricStart(series="Commute Work", tags=["bus"]), "telegram")

        service._series.create_series.assert_awaited_once_with("commute-work", "duration")
        assert result.series_created is True
        assert "new series" in result.message and "[bus]" in result.message
        fields, tags = service._repo.create_entry.await_args.args
        assert fields["status"] == "open" and fields["started_at"] == NOW and tags == ["bus"]

    async def test_discards_unfinished_previous_entry(self, make_service):
        service = make_service()
        service._series.get_series_by_name.return_value = _series()
        service._repo.get_open_entries.return_value = [_entry(id=7)]
        service._repo.create_entry.return_value = _entry(id=8)

        result = await service.start(MetricStart(series="commute-work"), "shortcut")

        service._repo.update_entry.assert_awaited_once_with(7, {"status": "discarded"})
        assert result.discarded_entry_id == 7 and "#7" in result.message

    async def test_rejects_non_duration_series(self, make_service):
        service = make_service()
        service._series.get_series_by_name.return_value = _series("sleep", "value")
        with pytest.raises(MetricKindMismatchError):
            await service.start(MetricStart(series="sleep"), "telegram")

    async def test_rejects_archived_series(self, make_service):
        service = make_service()
        service._series.get_series_by_name.return_value = _series(archived=True)
        with pytest.raises(MetricSeriesArchivedError):
            await service.start(MetricStart(series="commute-work"), "telegram")

    async def test_stores_weather_with_location_source(self, make_service):
        conditions = AsyncMock()
        conditions.get_current_conditions.return_value = WeatherSnapshot(
            temp_c=14.5, precipitation_mm=0.2, wind_kmh=12, weather_code=61
        )
        service = make_service(conditions)
        service._series.get_series_by_name.return_value = _series()
        service._repo.get_open_entries.return_value = []
        service._repo.create_entry.return_value = _entry()

        await service.start(MetricStart(series="commute-work", lat=41.2, lon=-8.6, accuracy_m=20), "shortcut")

        fields, _ = service._repo.create_entry.await_args.args
        assert fields["context"]["start"]["location_source"] == "device"
        assert fields["context"]["start"]["weather_code"] == 61
        assert (fields["start_lat"], fields["start_lon"], fields["start_accuracy_m"]) == (41.2, -8.6, 20)

    async def test_weather_failure_never_blocks_start(self, make_service):
        conditions = AsyncMock()
        conditions.get_current_conditions.side_effect = RuntimeError("open-meteo down")
        service = make_service(conditions)
        service._series.get_series_by_name.return_value = _series()
        service._repo.get_open_entries.return_value = []
        service._repo.create_entry.return_value = _entry()

        await service.start(MetricStart(series="commute-work"), "telegram")

        fields, _ = service._repo.create_entry.await_args.args
        assert fields["context"] is None

    async def test_default_location_is_marked(self, make_service):
        conditions = AsyncMock()
        conditions.get_current_conditions.return_value = WeatherSnapshot(
            temp_c=10, precipitation_mm=0, wind_kmh=5, weather_code=0
        )
        service = make_service(conditions)
        service._series.get_series_by_name.return_value = _series()
        service._repo.get_open_entries.return_value = []
        service._repo.create_entry.return_value = _entry()

        await service.start(MetricStart(series="commute-work"), "telegram")

        fields, _ = service._repo.create_entry.await_args.args
        assert fields["context"]["start"]["location_source"] == "default"


class TestStop:
    async def test_closes_the_only_running_timer(self, make_service):
        service = make_service()
        running = _entry(started=NOW - timedelta(minutes=34))
        service._repo.get_open_entries.return_value = [running]
        service._repo.update_entry.return_value = _entry(started=running.started_at, ended=NOW, status="closed")

        result = await service.stop(MetricStop(), "telegram")

        fields = service._repo.update_entry.await_args.args[1]
        assert fields["ended_at"] == NOW and fields["status"] == "closed"
        assert result.message == "Stopped commute-work: 34 min"

    async def test_ago_backdates_the_stop(self, make_service):
        service = make_service()
        service._repo.get_open_entries.return_value = [_entry()]
        service._repo.update_entry.return_value = _entry(ended=NOW, status="closed")

        await service.stop(MetricStop(ago_s=300), "telegram")

        assert service._repo.update_entry.await_args.args[1]["ended_at"] == NOW - timedelta(seconds=300)

    async def test_nothing_running(self, make_service):
        service = make_service()
        service._repo.get_open_entries.return_value = []
        with pytest.raises(MetricNothingRunningError):
            await service.stop(MetricStop(), "telegram")

    async def test_unknown_series_means_nothing_running(self, make_service):
        service = make_service()
        service._series.get_series_by_name.return_value = None
        with pytest.raises(MetricNothingRunningError):
            await service.stop(MetricStop(series="ghost"), "telegram")

    async def test_several_timers_need_a_series_name(self, make_service):
        service = make_service()
        service._repo.get_open_entries.return_value = [_entry(id=1), _entry(_series("gym", id=2), id=2)]
        with pytest.raises(MetricAmbiguousStopError) as exc:
            await service.stop(MetricStop(), "telegram")
        assert "commute-work" in str(exc.value) and "gym" in str(exc.value)

    async def test_naming_the_series_resolves_ambiguity(self, make_service):
        service = make_service()
        service._series.get_series_by_name.return_value = _series("gym", id=2)
        service._repo.get_open_entries.return_value = [_entry(_series("gym", id=2), id=2)]
        service._repo.update_entry.return_value = _entry(_series("gym", id=2), id=2, ended=NOW, status="closed")

        result = await service.stop(MetricStop(series="gym"), "telegram")

        assert result.entry.series_name == "gym"
        service._repo.get_open_entries.assert_awaited_once_with(2)

    async def test_forgotten_timer_is_not_silently_closed(self, make_service):
        service = make_service()
        service._repo.get_open_entries.return_value = [_entry(started=NOW - timedelta(hours=14))]
        with pytest.raises(MetricStaleEntryError):
            await service.stop(MetricStop(), "telegram")
        service._repo.update_entry.assert_not_awaited()

    async def test_forgotten_timer_can_be_backdated(self, make_service):
        service = make_service()
        started = NOW - timedelta(hours=14)
        service._repo.get_open_entries.return_value = [_entry(started=started)]
        service._repo.update_entry.return_value = _entry(started=started, ended=NOW - timedelta(hours=13), status="closed")

        await service.stop(MetricStop(ago_s=13 * 3600), "telegram")

        service._repo.update_entry.assert_awaited_once()

    async def test_ago_before_the_start_is_invalid(self, make_service):
        service = make_service()
        service._repo.get_open_entries.return_value = [_entry(started=NOW - timedelta(minutes=5))]
        with pytest.raises(MetricInvalidEntryError):
            await service.stop(MetricStop(ago_s=600), "telegram")

    async def test_end_weather_is_kept_next_to_the_start_weather(self, make_service):
        conditions = AsyncMock()
        conditions.get_current_conditions.return_value = WeatherSnapshot(
            temp_c=9, precipitation_mm=1.2, wind_kmh=20, weather_code=63
        )
        service = make_service(conditions)
        start_ctx = {"start": {"temp_c": 12, "location_source": "default"}}
        service._repo.get_open_entries.return_value = [_entry(context=start_ctx)]
        service._repo.update_entry.return_value = _entry(ended=NOW, status="closed")

        await service.stop(MetricStop(lat=41.1, lon=-8.6), "shortcut")

        context = service._repo.update_entry.await_args.args[1]["context"]
        assert context["start"] == start_ctx["start"]
        assert context["end"]["weather_code"] == 63 and context["end"]["location_source"] == "device"


class TestLog:
    async def test_value_creates_a_value_series(self, make_service):
        service = make_service()
        service._series.get_series_by_name.return_value = None
        service._series.create_series.return_value = _series("sleep", "value", unit="h")
        service._repo.create_entry.return_value = _entry(_series("sleep", "value", unit="h"), status="closed", value=7.5)

        result = await service.log(MetricLog(series="sleep", value=7.5), "telegram")

        service._series.create_series.assert_awaited_once_with("sleep", "value")
        fields, _ = service._repo.create_entry.await_args.args
        assert fields["value"] == 7.5 and fields["status"] == "closed"
        assert result.message.startswith("Logged sleep: 7.5")

    async def test_no_value_counts_one_event(self, make_service):
        service = make_service()
        service._series.get_series_by_name.return_value = _series("coffee", "count")
        service._repo.create_entry.return_value = _entry(_series("coffee", "count"), status="closed", value=1)

        await service.log(MetricLog(series="coffee"), "telegram")

        fields, _ = service._repo.create_entry.await_args.args
        assert fields["value"] == 1

    async def test_value_for_a_count_series_is_rejected(self, make_service):
        service = make_service()
        service._series.get_series_by_name.return_value = _series("coffee", "count")
        with pytest.raises(MetricKindMismatchError):
            await service.log(MetricLog(series="coffee", value=2), "telegram")

    async def test_missing_value_for_a_value_series_is_rejected(self, make_service):
        service = make_service()
        service._series.get_series_by_name.return_value = _series("sleep", "value")
        with pytest.raises(MetricKindMismatchError):
            await service.log(MetricLog(series="sleep"), "telegram")

    def test_nan_value_is_rejected_at_the_schema(self):
        with pytest.raises(ValueError):
            MetricLog(series="sleep", value=float("nan"))

    async def test_unit_flag_sets_the_unit_on_a_series_without_one(self, make_service):
        service = make_service()
        weight = _series("weight", "value")
        service._series.get_series_by_name.return_value = weight
        service._series.update_series.return_value = _series("weight", "value", unit="kg")
        service._repo.create_entry.return_value = _entry(weight, status="closed", value=80)

        result = await service.log(MetricLog(series="weight", value=80, unit=" kg "), "telegram")

        service._series.update_series.assert_awaited_once_with(weight.id, {"unit": "kg"})
        assert result.message.startswith("Logged weight: 80 kg")

    async def test_unit_flag_changes_a_different_unit(self, make_service):
        service = make_service()
        service._series.get_series_by_name.return_value = _series("weight", "value", unit="lb")
        service._series.update_series.return_value = _series("weight", "value", unit="kg")
        service._repo.create_entry.return_value = _entry(_series("weight", "value"), status="closed", value=80)

        await service.log(MetricLog(series="weight", value=80, unit="kg"), "telegram")

        service._series.update_series.assert_awaited_once()

    async def test_same_unit_is_not_rewritten(self, make_service):
        service = make_service()
        service._series.get_series_by_name.return_value = _series("weight", "value", unit="kg")
        service._repo.create_entry.return_value = _entry(_series("weight", "value"), status="closed", value=80)

        await service.log(MetricLog(series="weight", value=80, unit="kg"), "telegram")

        service._series.update_series.assert_not_awaited()

    def test_blank_unit_is_treated_as_missing(self):
        assert MetricLog(series="weight", value=80, unit="  ").unit is None


class TestManualEntries:
    async def test_create_duration_needs_an_end(self, make_service):
        service = make_service()
        service._series.get_series_by_name.return_value = _series()
        with pytest.raises(MetricInvalidEntryError):
            await service.create_entry(MetricEntryCreate(series="commute-work", started_at=NOW))

    async def test_create_rejects_end_before_start(self, make_service):
        service = make_service()
        service._series.get_series_by_name.return_value = _series()
        with pytest.raises(MetricInvalidEntryError):
            await service.create_entry(
                MetricEntryCreate(series="commute-work", started_at=NOW, ended_at=NOW - timedelta(minutes=1))
            )

    async def test_create_unknown_series(self, make_service):
        service = make_service()
        service._series.get_series_by_name.return_value = None
        with pytest.raises(MetricSeriesNotFoundError):
            await service.create_entry(MetricEntryCreate(series="ghost", started_at=NOW))

    async def test_create_closed_duration(self, make_service):
        service = make_service()
        service._series.get_series_by_name.return_value = _series()
        service._repo.create_entry.return_value = _entry(ended=NOW, status="closed")

        await service.create_entry(
            MetricEntryCreate(series="commute-work", started_at=NOW - timedelta(minutes=30), ended_at=NOW, tags=["Bus"])
        )

        fields, tags = service._repo.create_entry.await_args.args
        assert fields["status"] == "closed" and fields["source"] == "portal" and tags == ["Bus"]

    async def test_value_series_needs_a_value(self, make_service):
        service = make_service()
        service._series.get_series_by_name.return_value = _series("sleep", "value")
        with pytest.raises(MetricInvalidEntryError):
            await service.create_entry(MetricEntryCreate(series="sleep", started_at=NOW))

    async def test_update_closing_an_open_entry_sets_closed(self, make_service):
        service = make_service()
        service._repo.get_entry.return_value = _entry()
        service._repo.update_entry.return_value = _entry(ended=NOW, status="closed")

        await service.update_entry(10, MetricEntryUpdate(ended_at=NOW))

        fields = service._repo.update_entry.await_args.args[1]
        assert fields["status"] == "closed" and fields["ended_at"] == NOW

    async def test_update_cannot_move_end_before_start(self, make_service):
        service = make_service()
        service._repo.get_entry.return_value = _entry(ended=NOW, status="closed")
        with pytest.raises(MetricInvalidEntryError):
            await service.update_entry(10, MetricEntryUpdate(ended_at=NOW - timedelta(hours=2)))

    async def test_update_keeps_discarded_status(self, make_service):
        service = make_service()
        service._repo.get_entry.return_value = _entry(ended=NOW, status="discarded")
        service._repo.update_entry.return_value = _entry(ended=NOW, status="discarded")

        await service.update_entry(10, MetricEntryUpdate(note="x"))

        assert service._repo.update_entry.await_args.args[1]["status"] == "discarded"

    async def test_update_unknown_entry(self, make_service):
        service = make_service()
        service._repo.get_entry.return_value = None
        assert await service.update_entry(99, MetricEntryUpdate(note="x")) is None

    async def test_discard_sets_status(self, make_service):
        service = make_service()
        service._repo.get_entry.return_value = _entry()
        service._repo.update_entry.return_value = _entry(status="discarded")

        result = await service.discard_entry(10)

        service._repo.update_entry.assert_awaited_once_with(10, {"status": "discarded"})
        assert result.status == "discarded"

    async def test_discard_is_idempotent(self, make_service):
        service = make_service()
        service._repo.get_entry.return_value = _entry(status="discarded")
        await service.discard_entry(10)
        service._repo.update_entry.assert_not_awaited()


class TestStaleFlag:
    async def test_open_entry_older_than_six_hours_is_stale(self, make_service):
        service = make_service()
        service._repo.get_open_entries.return_value = [
            _entry(id=1, started=NOW - timedelta(hours=7)),
            _entry(id=2, started=NOW - timedelta(hours=1)),
        ]
        entries = await service.get_open_entries()
        assert [e.is_stale for e in entries] == [True, False]

    async def test_closed_entry_is_never_stale(self, make_service):
        service = make_service()
        service._repo.get_entry.return_value = _entry(started=NOW - timedelta(hours=9), ended=NOW, status="closed")
        assert (await service.get_entry(10)).is_stale is False


class TestListing:
    async def test_unknown_series_filter_returns_nothing(self, make_service):
        service = make_service()
        service._series.get_series_by_name.return_value = None
        assert await service.get_entries(MetricEntryFilters(series="ghost")) == []
        service._repo.get_entries.assert_not_awaited()

    async def test_read_exposes_duration_tags_and_series(self, make_service):
        service = make_service()
        service._repo.get_entries.return_value = [
            _entry(started=NOW - timedelta(minutes=34), ended=NOW, status="closed", tags=["bus"])
        ]
        (entry,) = await service.get_entries(MetricEntryFilters())
        assert entry.duration_s == 34 * 60 and entry.tags == ["bus"] and entry.series_name == "commute-work"
