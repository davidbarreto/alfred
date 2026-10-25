from datetime import date, datetime, time
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.assistant.commands.handlers.routine import handle_routine
from app.assistant.commands.registry import COMMAND_DEFINITIONS
from app.features.organizer.routines.schemas import RoutineStepCreate, RoutineUpdate
from app.features.organizer.routines.service import RoutineConflictError, RoutineValidationError
from app.features.organizer.tasks.schemas import TASK_CONTEXTS


@pytest.fixture
def service():
    svc = AsyncMock()
    dumped = MagicMock()
    dumped.model_dump.return_value = {"id": 1}
    for name in ("create_routine", "get_routine", "update_routine", "add_step", "update_step", "attach"):
        getattr(svc, name).return_value = dumped
    svc.get_routines.return_value = [dumped]
    svc.delete_routine.return_value = True
    svc.delete_step.return_value = True
    svc.detach.return_value = True
    return svc


class TestRoutineCommands:
    async def test_add_builds_a_scheduled_routine(self, service):
        await handle_routine(
            "add",
            {"name": "Morning", "recurrence_rule": "FREQ=DAILY", "starts_on": "2026-10-01", "description": "Wake up"},
            service,
        )
        payload = service.create_routine.call_args.args[0]
        assert (payload.name, payload.recurrence_rule, payload.starts_on) == ("Morning", "FREQ=DAILY", date(2026, 10, 1))

    async def test_add_event_based_routine_needs_no_rule(self, service):
        await handle_routine("add", {"name": "Dinner"}, service)
        assert service.create_routine.call_args.args[0].recurrence_rule is None

    async def test_add_rule_without_start_is_400(self, service):
        with pytest.raises(HTTPException) as exc:
            await handle_routine("add", {"name": "x", "recurrence_rule": "FREQ=DAILY"}, service)
        assert exc.value.status_code == 400

    async def test_list_filters_by_active(self, service):
        await handle_routine("list", {"active": "true"}, service)
        service.get_routines.assert_awaited_once_with(True)

    async def test_list_without_filter(self, service):
        await handle_routine("list", {}, service)
        service.get_routines.assert_awaited_once_with(None)

    async def test_get_unknown_is_404(self, service):
        service.get_routine.return_value = None
        with pytest.raises(HTTPException) as exc:
            await handle_routine("get", {"id": "9"}, service)
        assert exc.value.status_code == 404

    async def test_get_requires_numeric_id(self, service):
        with pytest.raises(HTTPException) as exc:
            await handle_routine("get", {"id": "abc"}, service)
        assert exc.value.status_code == 400

    async def test_update_clears_the_rule_with_empty_values(self, service):
        await handle_routine("update", {"id": "1", "recurrence_rule": "", "starts_on": ""}, service)
        assert service.update_routine.call_args.args[1] == RoutineUpdate(recurrence_rule=None, starts_on=None)

    async def test_update_active_flag(self, service):
        await handle_routine("update", {"id": "1", "active": "false"}, service)
        assert service.update_routine.call_args.args[1] == RoutineUpdate(active=False)

    async def test_invalid_active_value_is_400(self, service):
        with pytest.raises(HTTPException) as exc:
            await handle_routine("update", {"id": "1", "active": "maybe"}, service)
        assert exc.value.status_code == 400

    async def test_delete(self, service):
        assert await handle_routine("delete", {"id": "1"}, service) == {"deleted": True, "id": 1}

    async def test_delete_unknown_is_404(self, service):
        service.delete_routine.return_value = False
        with pytest.raises(HTTPException) as exc:
            await handle_routine("delete", {"id": "1"}, service)
        assert exc.value.status_code == 404


class TestStepCommands:
    async def test_add_relative_step(self, service):
        await handle_routine(
            "add_step",
            {"routine_id": "1", "title": "Prepare dinner", "anchor": "Start", "offset_minutes": "-120",
             "duration_minutes": "40", "context": "Home", "note": "26", "checklist_note_id": "26"},
            service,
        )
        routine_id, payload = service.add_step.call_args.args
        assert routine_id == 1
        assert payload == RoutineStepCreate(
            title="Prepare dinner", anchor="start", offset_minutes=-120, duration_minutes=40,
            context="home", checklist_note_id=26,
        )

    async def test_add_window_step(self, service):
        await handle_routine(
            "add_step",
            {"routine_id": "2", "title": "Shower", "window_start": "07:30", "window_end": "09:00", "duration_minutes": "15"},
            service,
        )
        payload = service.add_step.call_args.args[1]
        assert (payload.window_start, payload.window_end) == (time(7, 30), time(9, 0))

    async def test_add_step_without_timing_is_400(self, service):
        with pytest.raises(HTTPException) as exc:
            await handle_routine("add_step", {"routine_id": "1", "title": "x"}, service)
        assert exc.value.status_code == 400

    async def test_add_step_to_unknown_routine_is_404(self, service):
        service.add_step.return_value = None
        with pytest.raises(HTTPException) as exc:
            await handle_routine("add_step", {"routine_id": "1", "title": "x", "anchor": "end", "offset_minutes": "0"}, service)
        assert exc.value.status_code == 404

    async def test_update_step_sends_only_given_fields(self, service):
        await handle_routine("update_step", {"id": "4", "duration_minutes": "30"}, service)
        assert service.update_step.call_args.args == (4, service.update_step.call_args.args[1])
        assert service.update_step.call_args.args[1].model_dump(exclude_unset=True) == {"duration_minutes": 30}

    async def test_update_step_can_clear_location(self, service):
        await handle_routine("update_step", {"id": "4", "location": ""}, service)
        assert service.update_step.call_args.args[1].model_dump(exclude_unset=True) == {"location": None}

    async def test_delete_step(self, service):
        assert await handle_routine("delete_step", {"id": "4"}, service) == {"deleted": True, "id": 4}

    async def test_non_numeric_offset_is_400(self, service):
        with pytest.raises(HTTPException) as exc:
            await handle_routine("add_step", {"routine_id": "1", "title": "x", "anchor": "end", "offset_minutes": "soon"}, service)
        assert exc.value.status_code == 400


class TestAttachCommands:
    async def test_attach(self, service):
        await handle_routine("attach", {"id": "1", "event_id": "7"}, service)
        service.attach.assert_awaited_once_with(1, 7)

    async def test_attach_validation_error_is_422(self, service):
        service.attach.side_effect = RoutineValidationError("nope")
        with pytest.raises(HTTPException) as exc:
            await handle_routine("attach", {"id": "1", "event_id": "7"}, service)
        assert exc.value.status_code == 422

    async def test_conflict_is_409(self, service):
        service.add_step.side_effect = RoutineConflictError("taken")
        with pytest.raises(HTTPException) as exc:
            await handle_routine("add_step", {"routine_id": "1", "title": "x", "anchor": "end", "offset_minutes": "0"}, service)
        assert exc.value.status_code == 409

    async def test_detach(self, service):
        assert await handle_routine("detach", {"event_id": "7"}, service) == {"detached": True, "event_id": 7}

    async def test_detach_unknown_event_is_404(self, service):
        service.detach.return_value = False
        with pytest.raises(HTTPException) as exc:
            await handle_routine("detach", {"event_id": "7"}, service)
        assert exc.value.status_code == 404

    async def test_unknown_command_is_400(self, service):
        with pytest.raises(HTTPException) as exc:
            await handle_routine("explode", {}, service)
        assert exc.value.status_code == 400


class TestRoutineRegistry:
    def test_every_action_is_defined(self):
        assert set(COMMAND_DEFINITIONS["routine"]) == {
            "add", "list", "get", "update", "delete", "add_step", "update_step", "delete_step", "attach", "detach",
        }

    def test_overview_states_the_rules(self):
        details = COMMAND_DEFINITIONS["routine"]["add"]["details"]
        for phrase in ("not tasks", "never notify", "travel", "recurrence_rule", "starts_on", "event-based", "scheduled"):
            assert phrase in details

    def test_step_details_explain_timing_forms_units_and_contexts(self):
        for action in ("add_step", "update_step"):
            details = COMMAND_DEFINITIONS["routine"][action]["details"]
            for phrase in ("anchor", "offset_minutes", "negative", "window_start", "window_end", "fixed", "minutes", "HH:MM"):
                assert phrase in details
            for context in TASK_CONTEXTS:
                assert context in details

    def test_step_flags_cover_every_step_field(self):
        keys = set(COMMAND_DEFINITIONS["routine"]["add_step"]["flags"].values())
        assert {"title", "duration_minutes", "anchor", "offset_minutes", "window_start", "window_end", "context",
                "location", "checklist_note_id", "position"} <= keys

    def test_routine_flags_cover_every_routine_field(self):
        keys = set(COMMAND_DEFINITIONS["routine"]["update"]["flags"].values())
        assert {"name", "description", "active", "recurrence_rule", "starts_on"} <= keys

    def test_no_action_uses_the_reserved_name(self):
        for config in COMMAND_DEFINITIONS["routine"].values():
            assert "action" not in config["flags"].values()
            assert "action" not in config.get("arg_keys", [])
