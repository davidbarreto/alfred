from datetime import date, datetime, time
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.features.organizer.routines.schemas import (
    RoutineCreate,
    RoutineStepCreate,
    RoutineStepUpdate,
    RoutineUpdate,
)
from app.features.organizer.routines.service import (
    RoutineConflictError,
    RoutineService,
    RoutineValidationError,
)

_NOW = datetime(2026, 10, 1, 9, 0)


def _step(id=1, routine_id=1, position=0, **overrides):
    defaults = dict(
        id=id, routine_id=routine_id, position=position, title="Step", duration_minutes=10, anchor="start",
        offset_minutes=-30, window_start=None, window_end=None, context=None, location=None,
        checklist_note_id=None, created_at=_NOW, updated_at=_NOW,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _routine(id=1, steps=None, **overrides):
    defaults = dict(
        id=id, name="Dinner", description=None, active=True, recurrence_rule=None, starts_on=None,
        steps=steps if steps is not None else [], created_at=_NOW, updated_at=_NOW,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _scheduled(steps=None, **overrides):
    return _routine(steps=steps, recurrence_rule="FREQ=DAILY", starts_on=date(2026, 10, 1), **overrides)


@pytest.fixture
def service():
    svc = RoutineService(session=AsyncMock())
    svc._repo = AsyncMock()
    svc._repo.get_event_ids_by_routine.return_value = {}
    svc._repo.get_notes.return_value = {}
    svc._repo.note_exists.return_value = True
    svc._repo.position_taken.return_value = False
    svc._repo.next_position.return_value = 0
    return svc


class TestCreateRoutine:
    async def test_creates_event_based_routine(self, service):
        service._repo.create_routine.return_value = _routine()
        result = await service.create_routine(RoutineCreate(name="Dinner"))
        assert result.name == "Dinner"
        assert result.event_ids == []

    async def test_rejects_invalid_rrule(self, service):
        with pytest.raises(RoutineValidationError, match="recurrence_rule"):
            await service.create_routine(
                RoutineCreate(name="x", recurrence_rule="FREQ=SOMETIMES", starts_on=date(2026, 10, 1))
            )
        service._repo.create_routine.assert_not_called()


class TestGetRoutine:
    async def test_returns_checklist_note_content_for_steps(self, service):
        service._repo.get_routine.return_value = _routine(steps=[_step(checklist_note_id=26)])
        service._repo.get_notes.return_value = {26: SimpleNamespace(id=26, title="Dinner checklist", content="- cook\n- plate")}

        detail = await service.get_routine(1)

        note = detail.steps[0].checklist_note
        assert (note.id, note.title, note.content) == (26, "Dinner checklist", "- cook\n- plate")

    async def test_step_without_note_has_no_checklist(self, service):
        service._repo.get_routine.return_value = _routine(steps=[_step()])
        assert (await service.get_routine(1)).steps[0].checklist_note is None

    async def test_includes_attached_event_ids(self, service):
        service._repo.get_routine.return_value = _routine()
        service._repo.get_event_ids_by_routine.return_value = {1: [7, 9]}
        assert (await service.get_routine(1)).event_ids == [7, 9]

    async def test_unknown_routine_is_none(self, service):
        service._repo.get_routine.return_value = None
        assert await service.get_routine(5) is None

    async def test_list_attaches_event_ids_per_routine(self, service):
        service._repo.get_routines.return_value = [_routine(1), _routine(2)]
        service._repo.get_event_ids_by_routine.return_value = {2: [4]}
        result = await service.get_routines()
        assert [r.event_ids for r in result] == [[], [4]]


class TestUpdateRoutine:
    async def test_rename(self, service):
        service._repo.get_routine.return_value = _routine()
        service._repo.update_routine.return_value = _routine(name="Evening")
        result = await service.update_routine(1, RoutineUpdate(name="Evening"))
        assert result.name == "Evening"

    async def test_unknown_routine_is_none(self, service):
        service._repo.get_routine.return_value = None
        assert await service.update_routine(9, RoutineUpdate(name="x")) is None

    async def test_rule_without_start_date_is_rejected(self, service):
        service._repo.get_routine.return_value = _routine()
        with pytest.raises(RoutineValidationError, match="together"):
            await service.update_routine(1, RoutineUpdate(recurrence_rule="FREQ=DAILY"))

    async def test_cannot_become_scheduled_while_attached_to_events(self, service):
        service._repo.get_routine.return_value = _routine()
        service._repo.get_event_ids_by_routine.return_value = {1: [7]}
        with pytest.raises(RoutineValidationError, match="detach"):
            await service.update_routine(1, RoutineUpdate(recurrence_rule="FREQ=DAILY", starts_on=date(2026, 10, 1)))

    async def test_cannot_become_scheduled_with_relative_steps(self, service):
        service._repo.get_routine.return_value = _routine(steps=[_step(id=3)])
        with pytest.raises(RoutineValidationError, match=r"\[3\].*window_start"):
            await service.update_routine(1, RoutineUpdate(recurrence_rule="FREQ=DAILY", starts_on=date(2026, 10, 1)))

    async def test_scheduled_with_window_steps_can_become_event_based(self, service):
        service._repo.get_routine.return_value = _scheduled(
            steps=[_step(anchor=None, offset_minutes=None, window_start=time(7), window_end=time(8))]
        )
        with pytest.raises(RoutineValidationError, match="anchor"):
            await service.update_routine(1, RoutineUpdate(recurrence_rule=None, starts_on=None))

    async def test_empty_scheduled_routine_can_become_event_based(self, service):
        service._repo.get_routine.return_value = _scheduled()
        service._repo.update_routine.return_value = _routine()
        result = await service.update_routine(1, RoutineUpdate(recurrence_rule=None, starts_on=None))
        assert result.recurrence_rule is None


class TestDeleteRoutine:
    async def test_delete(self, service):
        service._repo.get_routine.return_value = _routine()
        assert await service.delete_routine(1) is True
        service._repo.delete_routine.assert_awaited_once_with(1)

    async def test_unknown(self, service):
        service._repo.get_routine.return_value = None
        assert await service.delete_routine(1) is False
        service._repo.delete_routine.assert_not_called()


class TestAddStep:
    async def test_appends_at_next_position_by_default(self, service):
        service._repo.get_routine.return_value = _routine()
        service._repo.next_position.return_value = 3
        service._repo.create_step.return_value = _step(position=3)

        await service.add_step(1, RoutineStepCreate(title="Leave", anchor="start", offset_minutes=-50))

        assert service._repo.create_step.call_args.args[:2] == (1, 3)

    async def test_explicit_position_used_when_free(self, service):
        service._repo.get_routine.return_value = _routine()
        service._repo.create_step.return_value = _step(position=5)
        await service.add_step(1, RoutineStepCreate(title="x", anchor="end", offset_minutes=0, position=5))
        assert service._repo.create_step.call_args.args[:2] == (1, 5)

    async def test_taken_position_is_a_conflict(self, service):
        service._repo.get_routine.return_value = _routine()
        service._repo.position_taken.return_value = True
        with pytest.raises(RoutineConflictError):
            await service.add_step(1, RoutineStepCreate(title="x", anchor="end", offset_minutes=0, position=0))

    async def test_unknown_routine_is_none(self, service):
        service._repo.get_routine.return_value = None
        assert await service.add_step(1, RoutineStepCreate(title="x", anchor="end", offset_minutes=0)) is None

    async def test_window_step_rejected_for_event_based_routine(self, service):
        service._repo.get_routine.return_value = _routine()
        with pytest.raises(RoutineValidationError, match="anchor"):
            await service.add_step(1, RoutineStepCreate(title="x", window_start="07:00", window_end="08:00"))

    async def test_relative_step_rejected_for_scheduled_routine(self, service):
        service._repo.get_routine.return_value = _scheduled()
        with pytest.raises(RoutineValidationError, match="window_start"):
            await service.add_step(1, RoutineStepCreate(title="x", anchor="start", offset_minutes=0))

    async def test_window_step_accepted_for_scheduled_routine(self, service):
        service._repo.get_routine.return_value = _scheduled()
        service._repo.create_step.return_value = _step(anchor=None, offset_minutes=None, window_start=time(7), window_end=time(8))
        result = await service.add_step(1, RoutineStepCreate(title="Shower", window_start="07:00", window_end="08:00"))
        assert result.window_start == time(7)

    async def test_missing_checklist_note_is_rejected(self, service):
        service._repo.get_routine.return_value = _routine()
        service._repo.note_exists.return_value = False
        with pytest.raises(RoutineValidationError, match="note 99"):
            await service.add_step(
                1, RoutineStepCreate(title="x", anchor="start", offset_minutes=0, checklist_note_id=99)
            )


class TestUpdateStep:
    async def test_changes_only_given_fields(self, service):
        service._repo.get_step.return_value = _step()
        service._repo.get_routine.return_value = _routine()
        service._repo.update_step.return_value = _step(duration_minutes=45)

        await service.update_step(1, RoutineStepUpdate(duration_minutes=45))

        validated = service._repo.update_step.call_args.args[2]
        assert validated.duration_minutes == 45
        assert (validated.anchor, validated.offset_minutes) == ("start", -30)

    async def test_setting_a_window_clears_the_relative_form(self, service):
        service._repo.get_step.return_value = _step(anchor=None, offset_minutes=None, window_start=time(7), window_end=time(8))
        service._repo.get_routine.return_value = _scheduled()
        service._repo.update_step.return_value = _step()

        await service.update_step(1, RoutineStepUpdate(window_end=time(9)))

        validated = service._repo.update_step.call_args.args[2]
        assert (validated.window_start, validated.window_end, validated.anchor) == (time(7), time(9), None)

    async def test_switching_to_relative_timing_clears_the_window(self, service):
        service._repo.get_step.return_value = _step(anchor=None, offset_minutes=None, window_start=time(7), window_end=time(8))
        service._repo.get_routine.return_value = _routine()
        service._repo.update_step.return_value = _step()

        await service.update_step(1, RoutineStepUpdate(anchor="end", offset_minutes=15))

        validated = service._repo.update_step.call_args.args[2]
        assert (validated.anchor, validated.offset_minutes, validated.window_start) == ("end", 15, None)

    async def test_switching_form_in_wrong_kind_of_routine_is_rejected(self, service):
        service._repo.get_step.return_value = _step()
        service._repo.get_routine.return_value = _routine()
        with pytest.raises(RoutineValidationError, match="anchor"):
            await service.update_step(1, RoutineStepUpdate(window_start=time(7), window_end=time(8)))

    async def test_moving_to_a_taken_position_conflicts(self, service):
        service._repo.get_step.return_value = _step(position=0)
        service._repo.get_routine.return_value = _routine()
        service._repo.position_taken.return_value = True
        with pytest.raises(RoutineConflictError):
            await service.update_step(1, RoutineStepUpdate(position=2))

    async def test_unknown_step_is_none(self, service):
        service._repo.get_step.return_value = None
        assert await service.update_step(1, RoutineStepUpdate(title="x")) is None

    async def test_cannot_null_the_title(self, service):
        service._repo.get_step.return_value = _step()
        service._repo.get_routine.return_value = _routine()
        with pytest.raises(RoutineValidationError, match="title"):
            await service.update_step(1, RoutineStepUpdate(title=None))


class TestDeleteStep:
    async def test_delete(self, service):
        service._repo.get_step.return_value = _step()
        assert await service.delete_step(1) is True

    async def test_unknown(self, service):
        service._repo.get_step.return_value = None
        assert await service.delete_step(1) is False


class TestAttach:
    async def test_attaches_event_based_routine(self, service):
        service._repo.get_routine.return_value = _routine()
        service._repo.event_exists.return_value = True
        service._repo.get_event_ids_by_routine.return_value = {1: [7]}

        result = await service.attach(1, 7)

        service._repo.set_event_routine.assert_awaited_once_with(7, 1)
        assert result.event_ids == [7]

    async def test_scheduled_routine_cannot_be_attached(self, service):
        service._repo.get_routine.return_value = _scheduled()
        with pytest.raises(RoutineValidationError, match="scheduled"):
            await service.attach(1, 7)
        service._repo.set_event_routine.assert_not_called()

    async def test_unknown_event_is_rejected(self, service):
        service._repo.get_routine.return_value = _routine()
        service._repo.event_exists.return_value = False
        with pytest.raises(RoutineValidationError, match="Event 7"):
            await service.attach(1, 7)

    async def test_unknown_routine_is_none(self, service):
        service._repo.get_routine.return_value = None
        assert await service.attach(1, 7) is None

    async def test_detach(self, service):
        service._repo.event_exists.return_value = True
        assert await service.detach(7) is True
        service._repo.set_event_routine.assert_awaited_once_with(7, None)

    async def test_detach_unknown_event(self, service):
        service._repo.event_exists.return_value = False
        assert await service.detach(7) is False
