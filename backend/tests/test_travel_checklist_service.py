from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest
from freezegun import freeze_time

from app.features.travel.checklist.service import ChecklistService
from app.features.travel.checklist.template import DEFAULT_ITEMS
from app.features.travel.errors import TravelConflictError, TravelNotFoundError


@pytest.fixture
def service():
    svc = ChecklistService(AsyncMock(), AsyncMock())
    svc._settings = AsyncMock()
    svc._trips = AsyncMock()
    svc._settings.get_value.return_value = "1"
    svc._settings.list_values.return_value = {}
    return svc


class TestSeeding:
    async def test_defaults_are_written_once_with_a_marker(self, service):
        service._settings.get_value.return_value = None

        await service.get_template()

        written = {c.args[0]: c.args[1] for c in service._settings.set_value.await_args_list}
        assert written["travel.checklist.start.passport-validity"] == "-60"
        assert written["travel.checklist.end.unpack-and-laundry"] == "1"
        assert written["travel.checklist_seeded"] == "1"
        assert len(written) == len(DEFAULT_ITEMS) + 1

    async def test_an_emptied_list_is_not_reseeded(self, service):
        assert await service.get_template() == []
        service._settings.set_value.assert_not_awaited()


class TestPutAndDelete:
    async def test_put_stores_the_signed_offset_under_the_anchored_key(self, service):
        item = await service.put_item("end", "send-photos", 3)

        service._settings.set_value.assert_awaited_once_with("travel.checklist.end.send-photos", "3")
        assert item.title == "send photos"

    async def test_same_name_under_the_other_anchor_is_a_conflict(self, service):
        service._settings.list_values.return_value = {"travel.checklist.start.currency": "-14"}
        with pytest.raises(TravelConflictError):
            await service.put_item("end", "currency", 1)

    @pytest.mark.parametrize("anchor,name", [("middle", "x"), ("start", "Has Space")])
    async def test_invalid_anchor_or_name_is_rejected(self, service, anchor, name):
        with pytest.raises(ValueError):
            await service.put_item(anchor, name, 1)

    async def test_delete_reports_missing(self, service):
        service._settings.delete_value.return_value = False
        assert await service.delete_item("start", "nope") is False


class TestGenerate:
    @freeze_time("2026-11-12 10:00:00")
    async def test_creates_a_task_per_item_due_at_its_offset(self, service):
        service._settings.list_values.return_value = {
            "travel.checklist.start.plug-adapter": "-7", "travel.checklist.end.send-photos": "3",
        }
        service._trips.get_trip.return_value = MagicMock(
            start_date=date(2026, 12, 17), end_date=date(2026, 12, 29)
        )
        service._trips.get_trip.return_value.name = "Christmas 2026"
        service._tasks.get_tasks.return_value = []

        result = await service.generate(1)

        assert result.created == ["plug adapter (Christmas 2026)", "send photos (Christmas 2026)"]
        deadlines = [c.args[0].deadline.date() for c in service._tasks.create_task.await_args_list]
        assert deadlines == [date(2026, 12, 10), date(2027, 1, 1)]

    @freeze_time("2026-11-12 10:00:00")
    async def test_skips_an_item_whose_task_exists(self, service):
        service._settings.list_values.return_value = {"travel.checklist.start.currency": "-14"}
        service._trips.get_trip.return_value = MagicMock(start_date=date(2026, 12, 17), end_date=date(2026, 12, 29))
        service._trips.get_trip.return_value.name = "Christmas 2026"
        existing = MagicMock()
        existing.title = "Currency (Christmas 2026)"
        service._tasks.get_tasks.return_value = [existing]

        result = await service.generate(1)

        assert result.skipped == ["currency (Christmas 2026)"]
        service._tasks.create_task.assert_not_awaited()

    async def test_unknown_trip_is_not_found(self, service):
        service._trips.get_trip.return_value = None
        with pytest.raises(TravelNotFoundError):
            await service.generate(9)
