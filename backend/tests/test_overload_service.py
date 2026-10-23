from datetime import date, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.features.core.overload.schemas import OverloadSnapshot
from app.features.core.overload.service import OverloadService, classify_level
from app.features.core.overload.tables import OverloadLog
from app.features.core.reminders.schemas import ReminderSettingsRead

NOW = datetime(2026, 10, 23, 10, 0)
TODAY = NOW.date()


def _settings(**overrides) -> ReminderSettingsRead:
    values = {
        "overload_overdue_threshold": 5, "overload_urgent_threshold": 4, "overload_max_listed": 5,
        "overload_urgent_interval_hours": 4, "overdue_grace_hours_high": 0,
        "overdue_grace_hours_medium": 48, "overdue_grace_hours_low": 168,
        "undated_escalation_days_high": 7, "undated_escalation_days_medium": 21,
        "undated_escalation_days_low": 45, "urgency_reset_days": 7, "catchup_tasks_per_day": 3, "catchup_stale_days": 30,
        "catchup_missed_habit_threshold": 3,
    }
    return ReminderSettingsRead(**{**values, **overrides})


def _task(deadline=None, urgency="NORMAL", recurrence_rule=None, is_done_in_cycle=False):
    task = MagicMock()
    task.deadline = deadline
    task.urgency = urgency
    task.recurrence_rule = recurrence_rule
    task.is_done_in_cycle = is_done_in_cycle
    return task


def _log_row(day: date, level="ok", last_level=None) -> OverloadLog:
    return OverloadLog(
        date=day, level=level, last_level=last_level or level, peak_overdue=0, peak_urgent=0,
        peak_active=0, reminder_runs=0, tasks_listed=0, tasks_omitted=0,
    )


def _snapshot(level="ok", overdue=0, urgent=0, active=0) -> OverloadSnapshot:
    return OverloadSnapshot(
        level=level, overdue=overdue, urgent=urgent, active=active,
        overdue_threshold=5, urgent_threshold=4,
    )


@pytest.fixture
def service():
    svc = OverloadService.__new__(OverloadService)
    svc._task_service = AsyncMock()
    svc._task_service.get_tasks.return_value = []
    svc._settings = AsyncMock()
    svc._settings.get.return_value = _settings()
    svc._repo = AsyncMock()
    svc._repo.get_day.return_value = None
    svc._repo.get_days.return_value = []
    svc._repo.get_latest.return_value = None
    svc._repo.save.side_effect = lambda row: row
    return svc


@pytest.fixture(autouse=True)
def _frozen_now():
    with patch("app.features.core.overload.service.local_now", return_value=NOW):
        yield


class TestClassifyLevel:
    def test_ok_below_half_the_thresholds(self):
        assert classify_level(overdue=2, urgent=1, settings=_settings()) == "ok"

    def test_elevated_from_half_the_overdue_threshold(self):
        assert classify_level(overdue=3, urgent=0, settings=_settings()) == "elevated"

    def test_elevated_from_half_the_urgent_threshold(self):
        assert classify_level(overdue=0, urgent=2, settings=_settings()) == "elevated"

    def test_overloaded_at_the_overdue_threshold(self):
        assert classify_level(overdue=5, urgent=0, settings=_settings()) == "overloaded"

    def test_overloaded_at_the_urgent_threshold(self):
        assert classify_level(overdue=0, urgent=4, settings=_settings()) == "overloaded"

    def test_thresholds_come_from_settings(self):
        assert classify_level(overdue=5, urgent=0, settings=_settings(overload_overdue_threshold=10)) == "elevated"


class TestSnapshot:
    async def test_counts_overdue_urgent_and_active(self, service):
        service._task_service.get_tasks.return_value = [
            _task(deadline=NOW - timedelta(days=1), urgency="URGENT"),
            _task(deadline=NOW - timedelta(hours=1)),
            _task(deadline=NOW + timedelta(days=1)),
            _task(deadline=None, urgency="URGENT"),
            _task(deadline=None),
        ]

        snapshot = await service.snapshot()

        assert (snapshot.overdue, snapshot.urgent, snapshot.active) == (2, 2, 5)

    async def test_reports_thresholds_and_level(self, service):
        service._task_service.get_tasks.return_value = [_task(deadline=NOW - timedelta(days=1))] * 5

        snapshot = await service.snapshot()

        assert snapshot.level == "overloaded"
        assert (snapshot.overdue_threshold, snapshot.urgent_threshold) == (5, 4)

    async def test_recurring_task_not_due_today_is_ignored(self, service):
        service._task_service.get_tasks.return_value = [
            _task(deadline=NOW - timedelta(days=1), urgency="URGENT", recurrence_rule="FREQ=WEEKLY;BYDAY=MO"),
        ]

        with patch("app.features.organizer.tasks.recurrence.is_due_today", return_value=False):
            snapshot = await service.snapshot()

        assert (snapshot.overdue, snapshot.urgent, snapshot.active) == (0, 0, 0)

    async def test_recurring_task_done_in_cycle_is_ignored(self, service):
        service._task_service.get_tasks.return_value = [
            _task(urgency="URGENT", recurrence_rule="FREQ=WEEKLY;BYDAY=FR", is_done_in_cycle=True),
        ]

        with patch("app.features.organizer.tasks.recurrence.is_due_today", return_value=True):
            snapshot = await service.snapshot()

        assert snapshot.urgent == 0

    async def test_pending_recurring_task_due_today_counts(self, service):
        service._task_service.get_tasks.return_value = [
            _task(urgency="URGENT", recurrence_rule="FREQ=WEEKLY;BYDAY=FR"),
        ]

        with patch("app.features.organizer.tasks.recurrence.is_due_today", return_value=True):
            snapshot = await service.snapshot()

        assert (snapshot.urgent, snapshot.active) == (1, 1)


class TestRecordRun:
    async def test_creates_the_days_row(self, service):
        await service.record_run(_snapshot("elevated", overdue=3, urgent=2, active=12), listed=4, omitted=0)

        row = service._repo.save.call_args.args[0]
        assert row.date == TODAY
        assert (row.level, row.last_level) == ("elevated", "elevated")
        assert (row.peak_overdue, row.peak_urgent, row.peak_active) == (3, 2, 12)
        assert (row.reminder_runs, row.tasks_listed, row.tasks_omitted) == (1, 4, 0)
        assert row.first_overloaded_at is None

    async def test_accumulates_counts_and_keeps_peaks(self, service):
        existing = _log_row(TODAY, level="overloaded")
        existing.peak_overdue, existing.peak_urgent, existing.peak_active = 9, 6, 30
        existing.reminder_runs, existing.tasks_listed, existing.tasks_omitted = 3, 15, 8
        service._repo.get_day.return_value = existing

        await service.record_run(_snapshot("elevated", overdue=3, urgent=2, active=12), listed=5, omitted=2)

        assert (existing.peak_overdue, existing.peak_urgent, existing.peak_active) == (9, 6, 30)
        assert (existing.reminder_runs, existing.tasks_listed, existing.tasks_omitted) == (4, 20, 10)

    async def test_level_keeps_the_worst_of_the_day_while_last_level_follows_the_latest_run(self, service):
        existing = _log_row(TODAY, level="overloaded")
        service._repo.get_day.return_value = existing

        await service.record_run(_snapshot("ok"), listed=0, omitted=0)

        assert existing.level == "overloaded"
        assert existing.last_level == "ok"

    async def test_level_escalates_within_the_day(self, service):
        existing = _log_row(TODAY, level="elevated")
        service._repo.get_day.return_value = existing

        await service.record_run(_snapshot("overloaded", overdue=6), listed=5, omitted=1)

        assert existing.level == "overloaded"
        assert existing.first_overloaded_at is not None

    async def test_first_overloaded_at_is_set_once(self, service):
        existing = _log_row(TODAY, level="overloaded")
        first = datetime(2026, 10, 23, 8, 5)
        existing.first_overloaded_at = first
        service._repo.get_day.return_value = existing

        await service.record_run(_snapshot("overloaded", overdue=6), listed=5, omitted=1)

        assert existing.first_overloaded_at == first


class TestPreviousLevel:
    async def test_none_before_the_first_run(self, service):
        assert await service.previous_level() is None

    async def test_returns_the_latest_runs_level(self, service):
        service._repo.get_latest.return_value = _log_row(TODAY - timedelta(days=1), level="overloaded", last_level="ok")

        assert await service.previous_level() == "ok"


class TestStatus:
    async def test_streak_is_zero_when_not_overloaded(self, service):
        status = await service.status()

        assert status.level == "ok"
        assert status.streak_days == 0

    async def test_streak_counts_today_when_there_is_no_history(self, service):
        service._task_service.get_tasks.return_value = [_task(deadline=NOW - timedelta(days=1))] * 5

        assert (await service.status()).streak_days == 1

    async def test_streak_counts_consecutive_overloaded_days(self, service):
        service._task_service.get_tasks.return_value = [_task(deadline=NOW - timedelta(days=1))] * 5
        service._repo.get_days.return_value = [
            _log_row(TODAY, level="overloaded"),
            _log_row(TODAY - timedelta(days=1), level="overloaded"),
            _log_row(TODAY - timedelta(days=2), level="overloaded"),
            _log_row(TODAY - timedelta(days=3), level="elevated"),
            _log_row(TODAY - timedelta(days=4), level="overloaded"),
        ]

        assert (await service.status()).streak_days == 3

    async def test_a_missing_day_breaks_the_streak(self, service):
        service._task_service.get_tasks.return_value = [_task(deadline=NOW - timedelta(days=1))] * 5
        service._repo.get_days.return_value = [_log_row(TODAY - timedelta(days=2), level="overloaded")]

        assert (await service.status()).streak_days == 1


class TestHistory:
    async def test_returns_oldest_first_for_the_window(self, service):
        service._repo.get_days.return_value = [
            _log_row(TODAY, level="elevated"),
            _log_row(TODAY - timedelta(days=1), level="ok"),
        ]

        history = await service.history(7)

        service._repo.get_days.assert_awaited_once_with(TODAY - timedelta(days=6))
        assert [day.date for day in history] == [TODAY - timedelta(days=1), TODAY]
