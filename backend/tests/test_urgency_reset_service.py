from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.features.core.urgency_reset.schemas import UrgencyResetRead
from app.features.core.urgency_reset.service import UrgencyResetService
from app.features.organizer.tasks.schemas import TaskFilters, TaskUpdate

NOW = datetime(2026, 9, 20, 10, 0)


def _task(
    id=1, deadline=None, urgency="URGENT", priority="LOW", created_at=None, recurrence_rule=None,
):
    task = MagicMock()
    task.id = id
    task.deadline = deadline
    task.urgency = urgency
    task.priority = priority
    task.created_at = created_at or NOW
    task.recurrence_rule = recurrence_rule
    return task


@pytest.fixture
def service():
    svc = UrgencyResetService.__new__(UrgencyResetService)
    svc._task_service = AsyncMock()
    svc._task_service.get_tasks.return_value = []
    svc._working_memory_service = AsyncMock()
    return svc


@pytest.fixture(autouse=True)
def _frozen_now():
    settings = MagicMock(urgency_reset_days=7, undated_task_escalation_days=30)
    with (
        patch("app.features.core.urgency_reset.service.local_now", return_value=NOW),
        patch("app.features.core.urgency_reset.service.get_settings", return_value=settings),
    ):
        yield


class TestReset:
    async def test_fetches_all_active_tasks(self, service):
        await service.reset()

        (filters,), _ = service._task_service.get_tasks.call_args
        assert filters.status == "ACTIVE"
        assert isinstance(filters, TaskFilters)

    async def test_returns_zero_counts_when_nothing_to_reset(self, service):
        result = await service.reset()

        assert result == UrgencyResetRead(
            days=7, tasks_urgency_reset=0, tasks_deadline_moved=0, tasks_snoozed=0
        )

    async def test_overdue_one_off_deadline_moves_forward_keeping_time_of_day(self, service):
        task = _task(id=1, deadline=datetime(2026, 9, 1, 14, 30), urgency="URGENT")
        service._task_service.get_tasks.return_value = [task]

        result = await service.reset(days=5)

        service._task_service.update_task.assert_awaited_once_with(
            1, TaskUpdate(deadline=datetime(2026, 9, 25, 14, 30), urgency="NORMAL")
        )
        assert result.tasks_deadline_moved == 1
        assert result.tasks_urgency_reset == 1

    async def test_overdue_normal_task_is_moved_but_not_counted_as_urgency_reset(self, service):
        # It would otherwise be escalated by the very next reminder run.
        task = _task(id=1, deadline=datetime(2026, 9, 1, 9, 0), urgency="NORMAL")
        service._task_service.get_tasks.return_value = [task]

        result = await service.reset()

        service._task_service.update_task.assert_awaited_once_with(
            1, TaskUpdate(deadline=datetime(2026, 9, 27, 9, 0), urgency="NORMAL")
        )
        assert result.tasks_deadline_moved == 1
        assert result.tasks_urgency_reset == 0

    async def test_urgent_task_with_future_deadline_only_resets_urgency(self, service):
        deadline = datetime(2026, 9, 22, 9, 0)
        task = _task(id=1, deadline=deadline, urgency="URGENT")
        service._task_service.get_tasks.return_value = [task]

        result = await service.reset()

        service._task_service.update_task.assert_awaited_once_with(1, TaskUpdate(urgency="NORMAL"))
        assert result.tasks_urgency_reset == 1
        assert result.tasks_deadline_moved == 0

    async def test_normal_task_with_future_deadline_is_untouched(self, service):
        task = _task(id=1, deadline=datetime(2026, 9, 22, 9, 0), urgency="NORMAL")
        service._task_service.get_tasks.return_value = [task]

        await service.reset()

        service._task_service.update_task.assert_not_awaited()

    async def test_urgent_undated_task_is_snoozed_and_urgency_cleared(self, service):
        task = _task(id=4, deadline=None, urgency="URGENT", created_at=NOW - timedelta(days=45))
        service._task_service.get_tasks.return_value = [task]

        with patch(
            "app.features.core.urgency_reset.service.snooze_undated_escalation", new_callable=AsyncMock
        ) as snooze:
            result = await service.reset(days=3)

        snooze.assert_awaited_once_with(
            service._working_memory_service, 4, 3,
            task_service=service._task_service, current_urgency="URGENT",
        )
        assert result.tasks_snoozed == 1
        assert result.tasks_urgency_reset == 1
        assert result.tasks_deadline_moved == 0

    async def test_stale_normal_undated_task_is_snoozed_before_it_escalates(self, service):
        task = _task(id=4, deadline=None, urgency="NORMAL", priority="LOW", created_at=NOW - timedelta(days=45))
        service._task_service.get_tasks.return_value = [task]

        with patch(
            "app.features.core.urgency_reset.service.snooze_undated_escalation", new_callable=AsyncMock
        ) as snooze:
            result = await service.reset()

        snooze.assert_awaited_once()
        assert result.tasks_snoozed == 1
        assert result.tasks_urgency_reset == 0

    async def test_fresh_normal_undated_task_is_untouched(self, service):
        task = _task(id=4, deadline=None, urgency="NORMAL", created_at=NOW - timedelta(days=3))
        service._task_service.get_tasks.return_value = [task]

        with patch(
            "app.features.core.urgency_reset.service.snooze_undated_escalation", new_callable=AsyncMock
        ) as snooze:
            await service.reset()

        snooze.assert_not_awaited()
        service._task_service.update_task.assert_not_awaited()

    async def test_stale_high_priority_normal_undated_task_is_untouched(self, service):
        # Age escalation never applies to HIGH priority, so there is nothing to defer.
        task = _task(id=4, deadline=None, urgency="NORMAL", priority="HIGH", created_at=NOW - timedelta(days=45))
        service._task_service.get_tasks.return_value = [task]

        with patch(
            "app.features.core.urgency_reset.service.snooze_undated_escalation", new_callable=AsyncMock
        ) as snooze:
            await service.reset()

        snooze.assert_not_awaited()

    async def test_urgent_high_priority_undated_task_is_snoozed_like_any_other(self, service):
        task = _task(id=4, deadline=None, urgency="URGENT", priority="HIGH")
        service._task_service.get_tasks.return_value = [task]

        with patch(
            "app.features.core.urgency_reset.service.snooze_undated_escalation", new_callable=AsyncMock
        ) as snooze:
            await service.reset()

        snooze.assert_awaited_once()

    async def test_urgent_recurring_task_only_resets_urgency(self, service):
        task = _task(
            id=6, deadline=datetime(2026, 8, 1, 9, 0), urgency="URGENT", recurrence_rule="FREQ=WEEKLY;BYDAY=MO",
        )
        service._task_service.get_tasks.return_value = [task]

        result = await service.reset()

        service._task_service.update_task.assert_awaited_once_with(6, TaskUpdate(urgency="NORMAL"))
        assert result.tasks_urgency_reset == 1
        assert result.tasks_deadline_moved == 0

    async def test_normal_recurring_task_is_untouched(self, service):
        task = _task(id=6, urgency="NORMAL", recurrence_rule="FREQ=WEEKLY;BYDAY=MO", created_at=NOW - timedelta(days=90))
        service._task_service.get_tasks.return_value = [task]

        await service.reset()

        service._task_service.update_task.assert_not_awaited()

    async def test_priority_is_never_changed(self, service):
        task = _task(id=1, deadline=datetime(2026, 9, 1, 9, 0), urgency="URGENT", priority="HIGH")
        service._task_service.get_tasks.return_value = [task]

        await service.reset()

        (_, update), _ = service._task_service.update_task.call_args
        assert "priority" not in update.model_dump(exclude_unset=True)

    async def test_defaults_days_from_settings(self, service):
        result = await service.reset()

        assert result.days == 7

    async def test_counts_aggregate_across_tasks(self, service):
        service._task_service.get_tasks.return_value = [
            _task(id=1, deadline=datetime(2026, 9, 1, 9, 0), urgency="URGENT"),
            _task(id=2, deadline=datetime(2026, 9, 2, 9, 0), urgency="NORMAL"),
            _task(id=3, deadline=None, urgency="URGENT"),
            _task(id=4, urgency="URGENT", recurrence_rule="FREQ=WEEKLY;BYDAY=MO"),
        ]

        with patch("app.features.core.urgency_reset.service.snooze_undated_escalation", new_callable=AsyncMock):
            result = await service.reset()

        assert result.tasks_urgency_reset == 3
        assert result.tasks_deadline_moved == 2
        assert result.tasks_snoozed == 1
