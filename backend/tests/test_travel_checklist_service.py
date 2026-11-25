from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest
from freezegun import freeze_time
from pydantic import ValidationError

from app.features.travel.checklist.schemas import ChecklistItemWrite, ChecklistTemplateUpdate
from app.features.travel.checklist.service import ChecklistService
from app.features.travel.checklist.template import DEFAULT_ITEMS
from app.features.travel.errors import TravelNotFoundError


@pytest.fixture
def service():
    svc = ChecklistService(AsyncMock(), AsyncMock())
    svc._settings = AsyncMock()
    svc._trips = AsyncMock()
    svc._task_repo = AsyncMock()
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
        assert (await service.get_template()).items == []
        service._settings.set_value.assert_not_awaited()


class TestReplace:
    async def test_writes_new_and_changed_items_and_deletes_missing_ones(self, service):
        service._settings.list_values.side_effect = [
            {"travel.checklist.start.currency": "-14", "travel.checklist.start.plug-adapter": "-7"},
            {"travel.checklist.start.currency": "-10", "travel.checklist.end.send-photos": "3"},
        ]

        result = await service.replace_template([
            ChecklistItemWrite(anchor="start", name="currency", offset_days=-10),
            ChecklistItemWrite(anchor="end", name="send-photos", offset_days=3),
        ])

        service._settings.delete_value.assert_awaited_once_with("travel.checklist.start.plug-adapter")
        written = [c.args for c in service._settings.set_value.await_args_list]
        assert written == [("travel.checklist.start.currency", "-10"), ("travel.checklist.end.send-photos", "3")]
        assert [(i.name, i.title, i.offset_days) for i in result.items] == [
            ("currency", "currency", -10), ("send-photos", "send photos", 3),
        ]

    async def test_moving_an_item_to_the_other_anchor_replaces_its_key(self, service):
        service._settings.list_values.return_value = {"travel.checklist.start.currency": "-14"}

        await service.replace_template([ChecklistItemWrite(anchor="end", name="currency", offset_days=1)])

        service._settings.delete_value.assert_awaited_once_with("travel.checklist.start.currency")
        service._settings.set_value.assert_awaited_once_with("travel.checklist.end.currency", "1")

    async def test_unchanged_items_are_not_rewritten(self, service):
        service._settings.list_values.return_value = {"travel.checklist.start.currency": "-14"}

        await service.replace_template([ChecklistItemWrite(anchor="start", name="currency", offset_days=-14)])

        service._settings.set_value.assert_not_awaited()
        service._settings.delete_value.assert_not_awaited()

    async def test_an_unseeded_template_is_seeded_before_it_is_replaced(self, service):
        service._settings.get_value.return_value = None

        await service.replace_template([])

        assert ("travel.checklist_seeded", "1") in [c.args for c in service._settings.set_value.await_args_list]
        assert service._settings.delete_value.await_count == 0  # list_values is mocked empty


class TestTemplateSchema:
    def test_names_are_unique_across_both_anchors(self):
        with pytest.raises(ValidationError, match="unique"):
            ChecklistTemplateUpdate(items=[
                {"anchor": "start", "name": "currency", "offset_days": -14},
                {"anchor": "end", "name": "currency", "offset_days": 1},
            ])

    @pytest.mark.parametrize("item", [
        {"anchor": "middle", "name": "x", "offset_days": 1},
        {"anchor": "start", "name": "Has Space", "offset_days": 1},
        {"anchor": "start", "name": "x", "offset_days": 5000},
    ])
    def test_invalid_anchor_name_or_offset_is_rejected(self, item):
        with pytest.raises(ValidationError):
            ChecklistTemplateUpdate(items=[item])

    def test_items_are_required(self):
        with pytest.raises(ValidationError):
            ChecklistTemplateUpdate()


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

        assert result.created == ["Plug adapter (Christmas 2026)", "Send photos (Christmas 2026)"]
        deadlines = [c.args[0].deadline.date() for c in service._tasks.create_task.await_args_list]
        assert deadlines == [date(2026, 12, 10), date(2027, 1, 1)]
        assert {c.args[0].priority for c in service._tasks.create_task.await_args_list} == {"MEDIUM"}

    @freeze_time("2026-11-12 10:00:00")
    async def test_skips_an_item_whose_task_exists(self, service):
        service._settings.list_values.return_value = {"travel.checklist.start.currency": "-14"}
        service._trips.get_trip.return_value = MagicMock(start_date=date(2026, 12, 17), end_date=date(2026, 12, 29))
        service._trips.get_trip.return_value.name = "Christmas 2026"
        existing = MagicMock()
        existing.title = "Currency (Christmas 2026)"
        service._tasks.get_tasks.return_value = [existing]

        result = await service.generate(1)

        assert result.skipped == ["Currency (Christmas 2026)"]
        service._tasks.create_task.assert_not_awaited()

    async def test_unknown_trip_is_not_found(self, service):
        service._trips.get_trip.return_value = None
        with pytest.raises(TravelNotFoundError):
            await service.generate(9)


class TestIsPending:
    async def test_pending_when_the_template_has_items_and_no_task_exists(self, service):
        service._settings.list_values.return_value = {"travel.checklist.start.currency": "-14"}
        service._task_repo.get_tasks.return_value = []
        assert await service.is_pending("Christmas 2026") is True

    async def test_not_pending_once_a_task_for_the_trip_exists(self, service):
        service._settings.list_values.return_value = {"travel.checklist.start.currency": "-14"}
        existing = MagicMock()
        existing.title = "Currency (Christmas 2026)"
        service._task_repo.get_tasks.return_value = [existing]
        assert await service.is_pending("Christmas 2026") is False

    async def test_not_pending_with_an_empty_template(self, service):
        assert await service.is_pending("Christmas 2026") is False
        service._task_repo.get_tasks.assert_not_awaited()
