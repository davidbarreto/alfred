from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from app.features.core.catchup.schemas import CatchupApply
from app.features.core.catchup.service import CatchupService
from app.features.core.reminders.schemas import ReminderSettingsRead
from app.features.organizer.tasks.schemas import TaskFilters, TaskUpdate

NOW = datetime(2026, 10, 23, 10, 0)


def _settings(**overrides) -> ReminderSettingsRead:
    values = {
        "overload_overdue_threshold": 5, "overload_urgent_threshold": 4, "overload_max_listed": 5,
        "overload_urgent_interval_hours": 4, "overdue_grace_hours_high": 0,
        "overdue_grace_hours_medium": 48, "overdue_grace_hours_low": 168,
        "undated_escalation_days_high": 7, "undated_escalation_days_medium": 21,
        "undated_escalation_days_low": 45, "urgency_reset_days": 7,
        "catchup_tasks_per_day": 3, "catchup_stale_days": 30, "catchup_missed_habit_threshold": 3,
    }
    return ReminderSettingsRead(**{**values, **overrides})


def _task(id, priority="MEDIUM", urgency="NORMAL", deadline=None, recurrence_rule=None, missed_count=None):
    return SimpleNamespace(
        id=id, title=f"Task {id}", priority=priority, urgency=urgency, deadline=deadline,
        created_at=datetime(2026, 1, 1), recurrence_rule=recurrence_rule, is_done_in_cycle=False,
        missed_count=missed_count,
    )


@pytest.fixture
def service():
    svc = CatchupService.__new__(CatchupService)
    svc._task_service = AsyncMock()
    svc._task_service.get_tasks.return_value = []
    svc._settings = AsyncMock()
    svc._settings.get.return_value = _settings()
    return svc


@pytest.fixture(autouse=True)
def _frozen_now():
    with patch("app.features.core.catchup.service.local_now", return_value=NOW):
        yield


def _backlog():
    """3 top picks (HIGH), 4 mid-overdue (spreadable), 2 stale (droppable), 1 missed habit."""
    top = [_task(i, priority="HIGH", deadline=NOW - timedelta(days=i)) for i in (1, 2, 3)]
    spreadable = [_task(10 + i, deadline=NOW - timedelta(days=3 + i)) for i in range(4)]
    stale = [_task(20 + i, priority="LOW", deadline=NOW - timedelta(days=40 + i)) for i in range(2)]
    habit = [_task(30, recurrence_rule="FREQ=WEEKLY;BYDAY=MO,TU,WE,TH", missed_count=4)]
    return top + spreadable + stale + habit


class TestGetSuggestions:
    async def test_fetches_all_active_tasks(self, service):
        await service.get_suggestions()

        (filters,), _ = service._task_service.get_tasks.call_args
        assert isinstance(filters, TaskFilters)
        assert filters.status == "ACTIVE"

    async def test_empty_backlog_has_no_suggestions(self, service):
        result = await service.get_suggestions()

        assert result.today_top == []
        assert result.suggestions == []

    async def test_returns_top_three_and_one_suggestion_of_each_kind(self, service):
        service._task_service.get_tasks.return_value = _backlog()

        result = await service.get_suggestions()

        assert [t.id for t in result.today_top] == [3, 2, 1]
        assert [s.kind for s in result.suggestions] == ["spread", "drop", "habits"]

    async def test_spread_leaves_top_picks_and_stale_tasks_alone(self, service):
        service._task_service.get_tasks.return_value = _backlog()

        spread = (await service.get_suggestions()).suggestions[0]

        assert sorted(m.task_id for m in spread.moves) == [10, 11, 12, 13]
        assert spread.command == "/catchupapply spread"
        assert spread.applicable is True

    async def test_spread_needs_at_least_two_tasks(self, service):
        service._task_service.get_tasks.return_value = [
            _task(1, priority="HIGH", deadline=NOW - timedelta(days=1)),
            _task(2, priority="HIGH", deadline=NOW - timedelta(days=1)),
            _task(3, priority="HIGH", deadline=NOW - timedelta(days=1)),
            _task(4, deadline=NOW - timedelta(days=5)),
        ]

        result = await service.get_suggestions()

        assert result.suggestions == []

    async def test_drop_lists_ids_in_its_command(self, service):
        service._task_service.get_tasks.return_value = _backlog()

        drop = (await service.get_suggestions()).suggestions[1]

        assert [t.id for t in drop.tasks] == [21, 20]  # oldest first
        assert drop.command == "/catchupapply drop 21,20"
        assert drop.tasks[0].days_overdue == 41

    async def test_habits_are_informational_only(self, service):
        service._task_service.get_tasks.return_value = _backlog()

        habits = (await service.get_suggestions()).suggestions[2]

        assert habits.applicable is False
        assert habits.command is None
        assert [t.id for t in habits.tasks] == [30]

    async def test_settings_drive_the_rules(self, service):
        service._task_service.get_tasks.return_value = _backlog()
        service._settings.get.return_value = _settings(catchup_stale_days=45, catchup_missed_habit_threshold=5)

        result = await service.get_suggestions()

        # 40-41 day old tasks are no longer stale (so they get spread instead) and the habit misses 4 < 5.
        assert [s.kind for s in result.suggestions] == ["spread"]
        assert sorted(m.task_id for m in result.suggestions[0].moves) == [10, 11, 12, 13, 20, 21]

    async def test_per_day_cap_comes_from_settings(self, service):
        service._task_service.get_tasks.return_value = _backlog()
        service._settings.get.return_value = _settings(catchup_tasks_per_day=1)

        spread = (await service.get_suggestions()).suggestions[0]

        assert len({m.new_deadline.date() for m in spread.moves}) == 4

    async def test_nothing_is_written(self, service):
        service._task_service.get_tasks.return_value = _backlog()

        await service.get_suggestions()

        service._task_service.update_task.assert_not_awaited()


class TestApplySpread:
    async def test_moves_every_planned_task_through_the_task_service(self, service):
        service._task_service.get_tasks.return_value = _backlog()

        result = await service.apply(CatchupApply(kind="spread"))

        assert (result.kind, result.applied, result.skipped) == ("spread", 4, 0)
        updated = {call.args[0]: call.args[1] for call in service._task_service.update_task.await_args_list}
        assert sorted(updated) == [10, 11, 12, 13]
        assert all(isinstance(u, TaskUpdate) and u.deadline > NOW for u in updated.values())
        assert all(set(u.model_dump(exclude_unset=True)) == {"deadline"} for u in updated.values())

    async def test_404_when_there_is_nothing_to_spread(self, service):
        with pytest.raises(HTTPException) as exc:
            await service.apply(CatchupApply(kind="spread"))

        assert exc.value.status_code == 404
        service._task_service.update_task.assert_not_awaited()


class TestApplyDrop:
    async def test_cancels_the_requested_stale_tasks(self, service):
        service._task_service.get_tasks.return_value = _backlog()

        result = await service.apply(CatchupApply(kind="drop", task_ids=[20]))

        assert (result.applied, result.skipped) == (1, 0)
        service._task_service.update_task.assert_awaited_once_with(20, TaskUpdate(status="CANCELLED"))

    async def test_without_ids_drops_every_suggested_task(self, service):
        service._task_service.get_tasks.return_value = _backlog()

        result = await service.apply(CatchupApply(kind="drop"))

        assert result.applied == 2
        assert {c.args[0] for c in service._task_service.update_task.await_args_list} == {20, 21}

    async def test_ids_that_no_longer_qualify_are_skipped_not_dropped(self, service):
        service._task_service.get_tasks.return_value = _backlog()

        result = await service.apply(CatchupApply(kind="drop", task_ids=[20, 1, 999]))

        assert (result.applied, result.skipped) == (1, 2)
        service._task_service.update_task.assert_awaited_once_with(20, TaskUpdate(status="CANCELLED"))

    async def test_404_when_nothing_is_stale(self, service):
        with pytest.raises(HTTPException) as exc:
            await service.apply(CatchupApply(kind="drop"))

        assert exc.value.status_code == 404

    def test_empty_id_list_is_rejected(self):
        with pytest.raises(ValueError):
            CatchupApply(kind="drop", task_ids=[])
