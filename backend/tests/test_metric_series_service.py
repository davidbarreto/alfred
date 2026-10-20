from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.exc import IntegrityError

from app.features.metrics.series.schemas import (
    MetricSeriesCreate,
    MetricSeriesMerge,
    MetricSeriesUpdate,
    normalize_series_name,
)
from app.features.metrics.series.service import (
    MetricSeriesMergeError,
    MetricSeriesNameTakenError,
    MetricSeriesNotEmptyError,
    MetricSeriesService,
)
from app.features.metrics.series.tables import MetricSeries

NOW = datetime(2026, 10, 21, tzinfo=timezone.utc)


def _series(name="commute-work", kind="duration", id=1) -> MetricSeries:
    return MetricSeries(id=id, name=name, kind=kind, unit=None, description=None, is_archived=False, created_at=NOW, updated_at=NOW)


@pytest.fixture
def service():
    svc = MetricSeriesService(AsyncMock())
    svc._repo = AsyncMock()
    return svc


class TestNameNormalisation:
    @pytest.mark.parametrize(
        "raw,clean",
        [("Commute Work", "commute-work"), ("  sleep ", "sleep"), ("gym_time", "gym_time"), ("A  B", "a-b")],
    )
    def test_slugifies(self, raw, clean):
        assert normalize_series_name(raw) == clean

    @pytest.mark.parametrize("raw", ["", "-lead", "has/slash", "ünï", "x" * 65])
    def test_rejects_invalid(self, raw):
        with pytest.raises(ValueError):
            normalize_series_name(raw)


class TestCreate:
    async def test_duplicate_name_is_rejected(self, service):
        service._repo.get_series_by_name.return_value = _series()
        with pytest.raises(MetricSeriesNameTakenError):
            await service.create_series(MetricSeriesCreate(name="commute-work", kind="duration"))

    async def test_race_on_unique_index_is_reported_as_name_taken(self, service):
        service._repo.get_series_by_name.return_value = None
        service._repo.create_series.side_effect = IntegrityError("x", {}, Exception())
        with pytest.raises(MetricSeriesNameTakenError):
            await service.create_series(MetricSeriesCreate(name="sleep", kind="value"))

    async def test_creates(self, service):
        service._repo.get_series_by_name.return_value = None
        service._repo.create_series.return_value = _series("sleep", "value")
        result = await service.create_series(MetricSeriesCreate(name="Sleep", kind="value", unit="h"))
        service._repo.create_series.assert_awaited_once_with("sleep", "value", "h", None)
        assert result.name == "sleep"


class TestUpdate:
    async def test_rename_to_existing_name_is_rejected(self, service):
        service._repo.get_series_by_name.side_effect = [_series(), _series("other", id=2)]
        with pytest.raises(MetricSeriesNameTakenError):
            await service.update_series("commute-work", MetricSeriesUpdate(name="other"))

    async def test_archive(self, service):
        service._repo.get_series_by_name.return_value = _series()
        service._repo.update_series.return_value = _series()
        await service.update_series("commute-work", MetricSeriesUpdate(is_archived=True))
        service._repo.update_series.assert_awaited_once_with(1, {"is_archived": True})

    async def test_unknown_series(self, service):
        service._repo.get_series_by_name.return_value = None
        assert await service.update_series("ghost", MetricSeriesUpdate(unit="x")) is None


class TestDelete:
    async def test_series_with_entries_is_never_deleted(self, service):
        service._repo.get_series_by_name.return_value = _series()
        service._repo.count_entries.return_value = 42
        with pytest.raises(MetricSeriesNotEmptyError) as exc:
            await service.delete_series("commute-work")
        assert exc.value.entry_count == 42
        service._repo.delete_series.assert_not_awaited()

    async def test_empty_series_is_deleted(self, service):
        service._repo.get_series_by_name.return_value = _series()
        service._repo.count_entries.return_value = 0
        service._repo.delete_series.return_value = True
        assert await service.delete_series("commute-work") is True

    async def test_unknown_series(self, service):
        service._repo.get_series_by_name.return_value = None
        assert await service.delete_series("ghost") is False


class TestMerge:
    async def test_moves_entries_then_removes_source(self, service):
        service._repo.get_series_by_name.side_effect = [_series("comute-work", id=1), _series("commute-work", id=2)]
        service._repo.move_entries.return_value = 3

        result = await service.merge_series("comute-work", MetricSeriesMerge(into="commute-work"))

        service._repo.move_entries.assert_awaited_once_with(1, 2)
        service._repo.delete_series.assert_awaited_once_with(1)
        assert result.name == "commute-work"

    async def test_different_kinds_are_not_merged(self, service):
        service._repo.get_series_by_name.side_effect = [_series("a", "value", id=1), _series("b", "duration", id=2)]
        with pytest.raises(MetricSeriesMergeError):
            await service.merge_series("a", MetricSeriesMerge(into="b"))
        service._repo.move_entries.assert_not_awaited()

    async def test_merging_into_itself_is_rejected(self, service):
        same = _series()
        service._repo.get_series_by_name.side_effect = [same, same]
        with pytest.raises(MetricSeriesMergeError):
            await service.merge_series("commute-work", MetricSeriesMerge(into="commute-work"))

    async def test_unknown_series(self, service):
        service._repo.get_series_by_name.side_effect = [None, _series()]
        assert await service.merge_series("ghost", MetricSeriesMerge(into="commute-work")) is None
