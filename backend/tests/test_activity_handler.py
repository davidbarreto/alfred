from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.assistant.commands.handlers.activity import handle_activity
from app.assistant.commands.registry import COMMAND_DEFINITIONS
from app.features.organizer.activities.schemas import ActivityCreate, ActivityLogCreate, ActivityUpdate
from app.features.organizer.activities.service import ActivityStateError, ActivityValidationError
from app.features.organizer.tasks.schemas import TASK_CONTEXTS


@pytest.fixture
def service():
    svc = AsyncMock()
    dumped = MagicMock()
    dumped.model_dump.return_value = {"id": 1}
    for name in ("create_activity", "update_activity", "archive", "unarchive", "log"):
        getattr(svc, name).return_value = dumped
    svc.get_activities.return_value = [dumped]
    svc.get_history.return_value = [dumped]
    return svc


class TestAddAndList:
    async def test_add_with_every_field(self, service):
        await handle_activity(
            "add",
            {"title": "Gym", "min_minutes": "60", "max_minutes": "90", "context": "Out", "target_per_week": "3", "tags": "health, sport"},
            service,
        )
        assert service.create_activity.call_args.args[0] == ActivityCreate(
            title="Gym", min_minutes=60, max_minutes=90, context="out", target_per_week=3, tags=["health", "sport"],
        )

    async def test_add_only_needs_a_title(self, service):
        await handle_activity("add", {"title": "Read"}, service)
        assert service.create_activity.call_args.args[0] == ActivityCreate(title="Read")

    @pytest.mark.parametrize("args", [{"title": ""}, {"title": "x", "context": "office"}, {"title": "x", "min_minutes": "0"},
                                      {"title": "x", "min_minutes": "90", "max_minutes": "30"}, {"title": "x", "max_minutes": "long"}])
    async def test_invalid_add_is_400(self, service, args):
        with pytest.raises(HTTPException) as exc:
            await handle_activity("add", args, service)
        assert exc.value.status_code == 400

    async def test_list_defaults(self, service):
        await handle_activity("list", {}, service)
        filters = service.get_activities.call_args.args[0]
        assert (filters.include_archived, filters.tag, filters.q, filters.limit) == (False, None, None, 200)

    async def test_list_filters(self, service):
        await handle_activity("list", {"tag": "health", "search": "gy", "archived": "true", "limit": "5"}, service)
        filters = service.get_activities.call_args.args[0]
        assert (filters.include_archived, filters.tag, filters.q, filters.limit) == (True, "health", "gy", 5)

    async def test_invalid_archived_flag_is_400(self, service):
        with pytest.raises(HTTPException) as exc:
            await handle_activity("list", {"archived": "maybe"}, service)
        assert exc.value.status_code == 400


class TestUpdate:
    async def test_only_given_fields_are_sent(self, service):
        await handle_activity("update", {"id": "4", "target_per_week": "2"}, service)
        assert service.update_activity.call_args.args == (4, ActivityUpdate(target_per_week=2))

    async def test_empty_value_clears_an_optional_field(self, service):
        await handle_activity("update", {"id": "4", "target_per_week": "", "context": "", "max_minutes": ""}, service)
        assert service.update_activity.call_args.args[1].model_dump(exclude_unset=True) == {
            "target_per_week": None, "context": None, "max_minutes": None,
        }

    async def test_tags_replace_the_set(self, service):
        await handle_activity("update", {"id": "4", "tags": "a,b"}, service)
        assert service.update_activity.call_args.args[1].tags == ["a", "b"]

    async def test_blank_title_is_400(self, service):
        with pytest.raises(HTTPException) as exc:
            await handle_activity("update", {"id": "4", "title": " "}, service)
        assert exc.value.status_code == 400

    async def test_unknown_activity_is_404(self, service):
        service.update_activity.return_value = None
        with pytest.raises(HTTPException) as exc:
            await handle_activity("update", {"id": "4", "title": "x"}, service)
        assert exc.value.status_code == 404

    async def test_range_error_is_422(self, service):
        service.update_activity.side_effect = ActivityValidationError("max below min")
        with pytest.raises(HTTPException) as exc:
            await handle_activity("update", {"id": "4", "max_minutes": "5"}, service)
        assert exc.value.status_code == 422

    async def test_id_is_required_and_numeric(self, service):
        for args in ({}, {"id": "abc"}):
            with pytest.raises(HTTPException) as exc:
                await handle_activity("update", args, service)
            assert exc.value.status_code == 400


class TestArchiveAndLog:
    async def test_archive_and_unarchive(self, service):
        await handle_activity("archive", {"id": "2"}, service)
        service.archive.assert_awaited_once_with(2)
        await handle_activity("unarchive", {"id": "2"}, service)
        service.unarchive.assert_awaited_once_with(2)

    async def test_archive_unknown_is_404(self, service):
        service.archive.return_value = None
        with pytest.raises(HTTPException) as exc:
            await handle_activity("archive", {"id": "2"}, service)
        assert exc.value.status_code == 404

    async def test_log_with_minutes_note_and_catch_up_time(self, service):
        await handle_activity(
            "log", {"id": "2", "minutes": "45", "note": "Legs", "done_at": "2026-10-19T19:00:00"}, service
        )
        activity_id, payload = service.log.call_args.args
        assert activity_id == 2
        assert payload == ActivityLogCreate(done_at=datetime(2026, 10, 19, 19, 0), minutes=45, note="Legs")

    async def test_bare_log_means_done_now(self, service):
        await handle_activity("log", {"id": "2"}, service)
        assert service.log.call_args.args[1] == ActivityLogCreate()

    @pytest.mark.parametrize("args", [{"minutes": "0"}, {"minutes": "lots"}, {"done_at": "yesterday"}])
    async def test_invalid_log_is_400(self, service, args):
        with pytest.raises(HTTPException) as exc:
            await handle_activity("log", {"id": "2", **args}, service)
        assert exc.value.status_code == 400

    async def test_log_of_unknown_activity_is_404(self, service):
        service.log.return_value = None
        with pytest.raises(HTTPException) as exc:
            await handle_activity("log", {"id": "2"}, service)
        assert exc.value.status_code == 404

    async def test_log_of_archived_activity_is_409(self, service):
        service.log.side_effect = ActivityStateError("archived")
        with pytest.raises(HTTPException) as exc:
            await handle_activity("log", {"id": "2"}, service)
        assert exc.value.status_code == 409

    async def test_future_log_is_422(self, service):
        service.log.side_effect = ActivityValidationError("future")
        with pytest.raises(HTTPException) as exc:
            await handle_activity("log", {"id": "2", "done_at": "2030-01-01T10:00:00"}, service)
        assert exc.value.status_code == 422

    async def test_history_paging(self, service):
        await handle_activity("history", {"id": "2", "limit": "10", "offset": "20"}, service)
        service.get_history.assert_awaited_once_with(2, 10, 20)

    async def test_history_defaults_and_404(self, service):
        await handle_activity("history", {"id": "2"}, service)
        service.get_history.assert_awaited_once_with(2, 50, 0)
        service.get_history.return_value = None
        with pytest.raises(HTTPException) as exc:
            await handle_activity("history", {"id": "2"}, service)
        assert exc.value.status_code == 404

    async def test_unknown_command_is_400(self, service):
        with pytest.raises(HTTPException) as exc:
            await handle_activity("explode", {}, service)
        assert exc.value.status_code == 400


class TestRegistry:
    def test_actions(self):
        assert set(COMMAND_DEFINITIONS["activity"]) == {"add", "list", "update", "log", "history", "archive", "unarchive"}

    @pytest.mark.parametrize("action", ["add", "update"])
    def test_details_explain_the_concept_units_and_contexts(self, action):
        details = COMMAND_DEFINITIONS["activity"][action]["details"]
        for phrase in ("not tasks", "minutes", "target_per_week", "never enforced", "tags", "recurring task"):
            assert phrase in details
        for context in TASK_CONTEXTS:
            assert context in details

    def test_log_details_define_what_counts_as_done(self):
        details = COMMAND_DEFINITIONS["activity"]["log"]["details"]
        for phrase in ("counts as done", "minutes", "done_at", "not in the future"):
            assert phrase in details

    def test_field_flags_cover_every_activity_field(self):
        keys = set(COMMAND_DEFINITIONS["activity"]["add"]["flags"].values())
        assert {"title", "min_minutes", "max_minutes", "context", "target_per_week", "tags"} <= keys
