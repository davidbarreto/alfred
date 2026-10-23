from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.features.core.overload.schemas import OverloadSnapshot
from app.features.core.reminders import escalation
from app.features.core.reminders.schemas import ReminderSettingsRead
from app.features.core.reminders.service import ReminderService
from app.features.organizer.tasks.schemas import TaskUpdate


def _make_task(
    id=1, title="Pay rent", deadline=None, urgency="NORMAL", priority="LOW", created_at=None,
    recurrence_rule=None, is_done_today=False,
):
    task = MagicMock()
    task.id = id
    task.title = title
    task.deadline = deadline
    task.urgency = urgency
    task.priority = priority
    task.created_at = created_at or NOW
    task.recurrence_rule = recurrence_rule
    task.is_done_today = is_done_today
    task.is_done_in_cycle = is_done_today
    return task


def _make_event(id=1, title="Team sync", start_datetime=None, all_day=False):
    event = MagicMock()
    event.id = id
    event.title = title
    event.start_datetime = start_datetime or datetime(2026, 7, 11, 14, 30)
    event.all_day = all_day
    return event


NOW = datetime(2026, 7, 11, 10, 0)


@pytest.fixture
def mock_session():
    return AsyncMock()


@pytest.fixture
def mock_task_service():
    service = AsyncMock()
    service.get_tasks.return_value = []
    return service


@pytest.fixture(autouse=True)
def mock_study_plan_service():
    # Autoused so every existing test (none of which cares about study plans) doesn't
    # have to patch this collaborator individually; study-plan-specific tests override
    # get_active_plans' return value via this fixture.
    with patch("app.features.core.reminders.service.StudyPlanService") as MockService:
        MockService.return_value.get_active_plans = AsyncMock(return_value=[])
        yield MockService


def default_reminder_settings(**overrides):
    values = {
        "overload_overdue_threshold": 5, "overload_urgent_threshold": 4, "overload_max_listed": 5,
        "overload_urgent_interval_hours": 4, "overdue_grace_hours_high": 0,
        "overdue_grace_hours_medium": 48, "overdue_grace_hours_low": 168,
        "undated_escalation_days_high": 7, "undated_escalation_days_medium": 21,
        "undated_escalation_days_low": 45, "urgency_reset_days": 7,
    }
    return ReminderSettingsRead(**{**values, **overrides})


def ok_snapshot(**overrides):
    values = {
        "level": "ok", "overdue": 0, "urgent": 0, "active": 0,
        "overdue_threshold": 5, "urgent_threshold": 4,
    }
    return OverloadSnapshot(**{**values, **overrides})


@pytest.fixture(autouse=True)
def mock_reminder_settings():
    with patch("app.features.core.reminders.service.ReminderSettingsService") as MockSettings:
        MockSettings.return_value.get = AsyncMock(return_value=default_reminder_settings())
        yield MockSettings.return_value


@pytest.fixture(autouse=True)
def mock_overload_service():
    with patch("app.features.core.reminders.service.OverloadService") as MockOverload:
        MockOverload.return_value.previous_level = AsyncMock(return_value=None)
        MockOverload.return_value.snapshot = AsyncMock(return_value=ok_snapshot())
        MockOverload.return_value.record_run = AsyncMock()
        yield MockOverload.return_value


def _service(session, task_service):
    return ReminderService(session=session, task_service=task_service)


class TestBuildDueDigestTasks:
    async def test_overdue_normal_task_is_escalated_and_included(self, mock_session, mock_task_service):
        task = _make_task(id=1, deadline=NOW - timedelta(hours=2), urgency="NORMAL", priority="HIGH")
        mock_task_service.get_tasks.return_value = [task]

        with (
            patch("app.features.core.reminders.service.CalendarEventService") as MockEventService,
            patch("app.features.core.reminders.service.ShoppingRepository") as MockShoppingRepo,
            patch("app.features.core.reminders.service.WorkingMemoryRepository") as MockWMRepo,
            patch("app.features.core.reminders.service.local_now", return_value=NOW),
        ):
            MockEventService.return_value.get_events = AsyncMock(return_value=[])
            MockShoppingRepo.return_value.list = AsyncMock(return_value=[])
            MockWMRepo.return_value.list = AsyncMock(return_value=[])
            MockWMRepo.return_value.upsert = AsyncMock()

            digest = await _service(mock_session, mock_task_service).build_due_digest()

        mock_task_service.update_task.assert_awaited_once_with(1, TaskUpdate(urgency="URGENT"))
        assert digest.has_content is True
        assert "Urgent tasks:" in digest.text
        assert "- Pay rent (HIGH, overdue)" in digest.text

    async def test_due_today_normal_task_is_not_escalated(self, mock_session, mock_task_service):
        task = _make_task(
            id=13, title="Water plants", deadline=NOW + timedelta(hours=3),
            urgency="NORMAL", priority="LOW",
        )
        mock_task_service.get_tasks.return_value = [task]

        with (
            patch("app.features.core.reminders.service.CalendarEventService") as MockEventService,
            patch("app.features.core.reminders.service.ShoppingRepository") as MockShoppingRepo,
            patch("app.features.core.reminders.service.WorkingMemoryRepository") as MockWMRepo,
            patch("app.features.core.reminders.service.local_now", return_value=NOW),
        ):
            MockEventService.return_value.get_events = AsyncMock(return_value=[])
            MockShoppingRepo.return_value.list = AsyncMock(return_value=[])
            MockWMRepo.return_value.list = AsyncMock(return_value=[])
            MockWMRepo.return_value.upsert = AsyncMock()

            digest = await _service(mock_session, mock_task_service).build_due_digest()

        mock_task_service.update_task.assert_not_awaited()
        assert "Normal tasks:" in digest.text
        assert "- Water plants (LOW, due 13:00)" in digest.text

    async def test_already_urgent_task_is_not_updated_again(self, mock_session, mock_task_service):
        task = _make_task(id=2, deadline=NOW - timedelta(hours=1), urgency="URGENT")
        mock_task_service.get_tasks.return_value = [task]

        with (
            patch("app.features.core.reminders.service.CalendarEventService") as MockEventService,
            patch("app.features.core.reminders.service.ShoppingRepository") as MockShoppingRepo,
            patch("app.features.core.reminders.service.WorkingMemoryRepository") as MockWMRepo,
            patch("app.features.core.reminders.service.local_now", return_value=NOW),
        ):
            MockEventService.return_value.get_events = AsyncMock(return_value=[])
            MockShoppingRepo.return_value.list = AsyncMock(return_value=[])
            MockWMRepo.return_value.list = AsyncMock(return_value=[])
            MockWMRepo.return_value.upsert = AsyncMock()

            await _service(mock_session, mock_task_service).build_due_digest()

        mock_task_service.update_task.assert_not_awaited()

    async def test_task_already_reminded_today_is_skipped(self, mock_session, mock_task_service):
        task = _make_task(id=3, deadline=NOW - timedelta(hours=1), urgency="URGENT")
        mock_task_service.get_tasks.return_value = [task]

        with (
            patch("app.features.core.reminders.service.CalendarEventService") as MockEventService,
            patch("app.features.core.reminders.service.ShoppingRepository") as MockShoppingRepo,
            patch("app.features.core.reminders.service.WorkingMemoryRepository") as MockWMRepo,
            patch("app.features.core.reminders.service.local_now", return_value=NOW),
        ):
            MockEventService.return_value.get_events = AsyncMock(return_value=[])
            MockShoppingRepo.return_value.list = AsyncMock(return_value=[])
            MockWMRepo.return_value.list = AsyncMock(return_value=[MagicMock()])
            MockWMRepo.return_value.upsert = AsyncMock()

            digest = await _service(mock_session, mock_task_service).build_due_digest()

        MockWMRepo.return_value.upsert.assert_not_awaited()
        assert digest.has_content is False

    async def test_mark_reminded_upserts_marker_with_urgent_ttl_under_an_hour(
        self, mock_session, mock_task_service
    ):
        task = _make_task(id=7, deadline=NOW - timedelta(hours=1), urgency="URGENT", priority="HIGH")
        mock_task_service.get_tasks.return_value = [task]

        with (
            patch("app.features.core.reminders.service.CalendarEventService") as MockEventService,
            patch("app.features.core.reminders.service.ShoppingRepository") as MockShoppingRepo,
            patch("app.features.core.reminders.service.WorkingMemoryRepository") as MockWMRepo,
            patch("app.features.core.reminders.service.local_now", return_value=NOW),
        ):
            MockEventService.return_value.get_events = AsyncMock(return_value=[])
            MockShoppingRepo.return_value.list = AsyncMock(return_value=[])
            MockWMRepo.return_value.list = AsyncMock(return_value=[])
            MockWMRepo.return_value.upsert = AsyncMock()
            before = datetime.now(timezone.utc)

            digest = await _service(mock_session, mock_task_service).build_due_digest()

        assert "- Pay rent (HIGH, overdue)" in digest.text
        MockWMRepo.return_value.upsert.assert_awaited_once()
        marker = MockWMRepo.return_value.upsert.call_args.args[0]
        assert marker.key == f"reminder:task:7:{NOW.date().isoformat()}"
        # The dedup TTL for urgent tasks must be strictly shorter than the hourly cron
        # cadence, otherwise a marker written seconds after the hour suppresses the next run.
        assert marker.expires_at - before < timedelta(hours=1)

    async def test_recurring_task_done_today_is_not_reminded(self, mock_session, mock_task_service):
        task = _make_task(
            id=10, deadline=NOW - timedelta(hours=2), urgency="URGENT", priority="HIGH",
            recurrence_rule="daily", is_done_today=True,
        )
        mock_task_service.get_tasks.return_value = [task]

        with (
            patch("app.features.core.reminders.service.CalendarEventService") as MockEventService,
            patch("app.features.core.reminders.service.ShoppingRepository") as MockShoppingRepo,
            patch("app.features.core.reminders.service.WorkingMemoryRepository") as MockWMRepo,
            patch("app.features.core.reminders.service.local_now", return_value=NOW),
        ):
            MockEventService.return_value.get_events = AsyncMock(return_value=[])
            MockShoppingRepo.return_value.list = AsyncMock(return_value=[])
            MockWMRepo.return_value.list = AsyncMock(return_value=[])
            MockWMRepo.return_value.upsert = AsyncMock()

            digest = await _service(mock_session, mock_task_service).build_due_digest()

        assert digest.has_content is False
        MockWMRepo.return_value.upsert.assert_not_awaited()

    async def test_recurring_task_not_done_today_is_reminded(self, mock_session, mock_task_service):
        task = _make_task(
            id=11, title="Take meds", deadline=NOW - timedelta(hours=2), urgency="URGENT",
            priority="HIGH", recurrence_rule="daily", is_done_today=False,
        )
        mock_task_service.get_tasks.return_value = [task]

        with (
            patch("app.features.core.reminders.service.CalendarEventService") as MockEventService,
            patch("app.features.core.reminders.service.ShoppingRepository") as MockShoppingRepo,
            patch("app.features.core.reminders.service.WorkingMemoryRepository") as MockWMRepo,
            patch("app.features.core.reminders.service.local_now", return_value=NOW),
        ):
            MockEventService.return_value.get_events = AsyncMock(return_value=[])
            MockShoppingRepo.return_value.list = AsyncMock(return_value=[])
            MockWMRepo.return_value.list = AsyncMock(return_value=[])
            MockWMRepo.return_value.upsert = AsyncMock()

            digest = await _service(mock_session, mock_task_service).build_due_digest()

        assert "- Take meds (HIGH, overdue)" in digest.text

    async def test_recurring_task_not_due_today_is_not_reminded(self, mock_session, mock_task_service):
        # NOW (2026-07-11) is a Saturday; a Sunday-only weekly task must not be
        # reminded on any other day, even though it wasn't completed today either.
        task = _make_task(
            id=15, title="Refill pill organizer", deadline=NOW - timedelta(hours=2),
            urgency="URGENT", priority="HIGH", recurrence_rule="FREQ=WEEKLY;BYDAY=SU",
            is_done_today=False,
        )
        mock_task_service.get_tasks.return_value = [task]

        with (
            patch("app.features.core.reminders.service.CalendarEventService") as MockEventService,
            patch("app.features.core.reminders.service.ShoppingRepository") as MockShoppingRepo,
            patch("app.features.core.reminders.service.WorkingMemoryRepository") as MockWMRepo,
            patch("app.features.core.reminders.service.local_now", return_value=NOW),
        ):
            MockEventService.return_value.get_events = AsyncMock(return_value=[])
            MockShoppingRepo.return_value.list = AsyncMock(return_value=[])
            MockWMRepo.return_value.list = AsyncMock(return_value=[])
            MockWMRepo.return_value.upsert = AsyncMock()

            digest = await _service(mock_session, mock_task_service).build_due_digest()

        assert "Refill pill organizer" not in digest.text
        assert digest.has_content is False

    async def test_recurring_task_due_today_is_reminded_when_not_done(self, mock_session, mock_task_service):
        # NOW (2026-07-11) is a Saturday.
        task = _make_task(
            id=16, title="Water the garden", deadline=NOW - timedelta(hours=2),
            urgency="URGENT", priority="HIGH", recurrence_rule="FREQ=WEEKLY;BYDAY=SA",
            is_done_today=False,
        )
        mock_task_service.get_tasks.return_value = [task]

        with (
            patch("app.features.core.reminders.service.CalendarEventService") as MockEventService,
            patch("app.features.core.reminders.service.ShoppingRepository") as MockShoppingRepo,
            patch("app.features.core.reminders.service.WorkingMemoryRepository") as MockWMRepo,
            patch("app.features.core.reminders.service.local_now", return_value=NOW),
        ):
            MockEventService.return_value.get_events = AsyncMock(return_value=[])
            MockShoppingRepo.return_value.list = AsyncMock(return_value=[])
            MockWMRepo.return_value.list = AsyncMock(return_value=[])
            MockWMRepo.return_value.upsert = AsyncMock()

            digest = await _service(mock_session, mock_task_service).build_due_digest()

        assert "Water the garden" in digest.text

    async def test_undated_recurring_task_not_due_today_is_not_reminded(
        self, mock_session, mock_task_service
    ):
        # NOW (2026-07-11) is a Saturday; a Sunday-only weekly undated habit must not
        # be reminded on any other day.
        task = _make_task(
            id=17, title="Refill pill organizer", deadline=None,
            urgency="NORMAL", priority="HIGH", recurrence_rule="FREQ=WEEKLY;BYDAY=SU",
            is_done_today=False,
        )
        mock_task_service.get_tasks.return_value = [task]

        with (
            patch("app.features.core.reminders.service.CalendarEventService") as MockEventService,
            patch("app.features.core.reminders.service.ShoppingRepository") as MockShoppingRepo,
            patch("app.features.core.reminders.service.WorkingMemoryRepository") as MockWMRepo,
            patch("app.features.core.reminders.service.local_now", return_value=NOW),
        ):
            MockEventService.return_value.get_events = AsyncMock(return_value=[])
            MockShoppingRepo.return_value.list = AsyncMock(return_value=[])
            MockWMRepo.return_value.list = AsyncMock(return_value=[])
            MockWMRepo.return_value.upsert = AsyncMock()

            digest = await _service(mock_session, mock_task_service).build_due_digest()

        assert "Refill pill organizer" not in digest.text
        assert "without a due date" not in digest.text
        assert digest.has_content is False

    async def test_undated_recurring_task_done_today_is_excluded_entirely(
        self, mock_session, mock_task_service
    ):
        task = _make_task(
            id=12, title="Journal", deadline=None, urgency="NORMAL", priority="HIGH",
            recurrence_rule="daily", is_done_today=True,
        )
        mock_task_service.get_tasks.return_value = [task]

        with (
            patch("app.features.core.reminders.service.CalendarEventService") as MockEventService,
            patch("app.features.core.reminders.service.ShoppingRepository") as MockShoppingRepo,
            patch("app.features.core.reminders.service.WorkingMemoryRepository") as MockWMRepo,
            patch("app.features.core.reminders.service.local_now", return_value=NOW),
        ):
            MockEventService.return_value.get_events = AsyncMock(return_value=[])
            MockShoppingRepo.return_value.list = AsyncMock(return_value=[])
            MockWMRepo.return_value.list = AsyncMock(return_value=[])
            MockWMRepo.return_value.upsert = AsyncMock()

            digest = await _service(mock_session, mock_task_service).build_due_digest()

        assert "Journal" not in digest.text
        assert "without a due date" not in digest.text
        assert digest.has_content is False

    async def test_far_future_task_is_excluded(self, mock_session, mock_task_service):
        task = _make_task(id=4, deadline=NOW + timedelta(days=3), urgency="NORMAL")
        mock_task_service.get_tasks.return_value = [task]

        with (
            patch("app.features.core.reminders.service.CalendarEventService") as MockEventService,
            patch("app.features.core.reminders.service.ShoppingRepository") as MockShoppingRepo,
            patch("app.features.core.reminders.service.WorkingMemoryRepository") as MockWMRepo,
            patch("app.features.core.reminders.service.local_now", return_value=NOW),
        ):
            MockEventService.return_value.get_events = AsyncMock(return_value=[])
            MockShoppingRepo.return_value.list = AsyncMock(return_value=[])
            MockWMRepo.return_value.list = AsyncMock(return_value=[])
            MockWMRepo.return_value.upsert = AsyncMock()

            digest = await _service(mock_session, mock_task_service).build_due_digest()

        mock_task_service.update_task.assert_not_awaited()
        assert digest.has_content is False

    async def test_undated_normal_task_is_counted_not_listed(self, mock_session, mock_task_service):
        task = _make_task(id=5, title="Read that book", deadline=None, urgency="NORMAL", priority="LOW")
        mock_task_service.get_tasks.return_value = [task]

        with (
            patch("app.features.core.reminders.service.CalendarEventService") as MockEventService,
            patch("app.features.core.reminders.service.ShoppingRepository") as MockShoppingRepo,
            patch("app.features.core.reminders.service.WorkingMemoryRepository") as MockWMRepo,
            patch("app.features.core.reminders.service.local_now", return_value=NOW),
        ):
            MockEventService.return_value.get_events = AsyncMock(return_value=[])
            MockShoppingRepo.return_value.list = AsyncMock(return_value=[])
            MockWMRepo.return_value.list = AsyncMock(return_value=[])
            MockWMRepo.return_value.upsert = AsyncMock()

            digest = await _service(mock_session, mock_task_service).build_due_digest()

        mock_task_service.update_task.assert_not_awaited()
        assert "Read that book" not in digest.text
        assert "1 other task(s) without a due date" in digest.text

    async def test_undated_summary_already_reminded_today_is_skipped(self, mock_session, mock_task_service):
        task = _make_task(id=6, title="Read that book", deadline=None, urgency="NORMAL", priority="LOW")
        mock_task_service.get_tasks.return_value = [task]

        with (
            patch("app.features.core.reminders.service.CalendarEventService") as MockEventService,
            patch("app.features.core.reminders.service.ShoppingRepository") as MockShoppingRepo,
            patch("app.features.core.reminders.service.WorkingMemoryRepository") as MockWMRepo,
            patch("app.features.core.reminders.service.local_now", return_value=NOW),
        ):
            MockEventService.return_value.get_events = AsyncMock(return_value=[])
            MockShoppingRepo.return_value.list = AsyncMock(return_value=[])
            MockWMRepo.return_value.list = AsyncMock(return_value=[MagicMock()])
            MockWMRepo.return_value.upsert = AsyncMock()

            digest = await _service(mock_session, mock_task_service).build_due_digest()

        MockWMRepo.return_value.upsert.assert_not_awaited()
        assert digest.has_content is False

    async def test_undated_high_priority_task_is_listed_individually(self, mock_session, mock_task_service):
        task = _make_task(id=7, title="Renew passport", deadline=None, urgency="NORMAL", priority="HIGH")
        mock_task_service.get_tasks.return_value = [task]

        with (
            patch("app.features.core.reminders.service.CalendarEventService") as MockEventService,
            patch("app.features.core.reminders.service.ShoppingRepository") as MockShoppingRepo,
            patch("app.features.core.reminders.service.WorkingMemoryRepository") as MockWMRepo,
            patch("app.features.core.reminders.service.local_now", return_value=NOW),
        ):
            MockEventService.return_value.get_events = AsyncMock(return_value=[])
            MockShoppingRepo.return_value.list = AsyncMock(return_value=[])
            MockWMRepo.return_value.list = AsyncMock(return_value=[])
            MockWMRepo.return_value.upsert = AsyncMock()

            digest = await _service(mock_session, mock_task_service).build_due_digest()

        mock_task_service.update_task.assert_not_awaited()
        assert "Normal tasks:" in digest.text
        assert "- Renew passport (HIGH)" in digest.text

    async def test_undated_low_task_past_its_priority_age_is_escalated_and_listed(self, mock_session, mock_task_service):
        stale_created_at = NOW - timedelta(days=46)
        task = _make_task(
            id=8, title="Learn guitar", deadline=None, urgency="NORMAL", priority="LOW",
            created_at=stale_created_at,
        )
        updated_task = _make_task(
            id=8, title="Learn guitar", deadline=None, urgency="URGENT", priority="LOW",
            created_at=stale_created_at,
        )
        mock_task_service.get_tasks.return_value = [task]
        mock_task_service.update_task.return_value = updated_task

        with (
            patch("app.features.core.reminders.service.CalendarEventService") as MockEventService,
            patch("app.features.core.reminders.service.ShoppingRepository") as MockShoppingRepo,
            patch("app.features.core.reminders.service.WorkingMemoryRepository") as MockWMRepo,
            patch("app.features.core.reminders.service.local_now", return_value=NOW),
        ):
            MockEventService.return_value.get_events = AsyncMock(return_value=[])
            MockShoppingRepo.return_value.list = AsyncMock(return_value=[])
            MockWMRepo.return_value.list = AsyncMock(return_value=[])
            MockWMRepo.return_value.upsert = AsyncMock()

            digest = await _service(mock_session, mock_task_service).build_due_digest()

        mock_task_service.update_task.assert_awaited_once_with(8, TaskUpdate(urgency="URGENT"))
        assert "Urgent tasks:" in digest.text
        assert "- Learn guitar (LOW)" in digest.text

    async def test_recurring_undated_task_is_not_age_escalated(self, mock_session, mock_task_service):
        # Every cycle of a habit starts fresh, so created_at age says nothing about it.
        task = _make_task(
            id=10, title="Take medicine", deadline=None, urgency="NORMAL", priority="LOW",
            created_at=NOW - timedelta(days=90), recurrence_rule="FREQ=WEEKLY;BYDAY=SA",
        )
        mock_task_service.get_tasks.return_value = [task]

        with (
            patch("app.features.core.reminders.service.CalendarEventService") as MockEventService,
            patch("app.features.core.reminders.service.ShoppingRepository") as MockShoppingRepo,
            patch("app.features.core.reminders.service.WorkingMemoryRepository") as MockWMRepo,
            patch("app.features.core.reminders.service.local_now", return_value=NOW),
        ):
            MockEventService.return_value.get_events = AsyncMock(return_value=[])
            MockShoppingRepo.return_value.list = AsyncMock(return_value=[])
            MockWMRepo.return_value.list = AsyncMock(return_value=[])
            MockWMRepo.return_value.upsert = AsyncMock()

            digest = await _service(mock_session, mock_task_service).build_due_digest()

        mock_task_service.update_task.assert_not_awaited()
        assert "Urgent tasks:" not in digest.text

    async def test_undated_task_under_a_month_old_is_not_escalated(self, mock_session, mock_task_service):
        task = _make_task(
            id=9, title="Learn guitar", deadline=None, urgency="NORMAL", priority="LOW",
            created_at=NOW - timedelta(days=10),
        )
        mock_task_service.get_tasks.return_value = [task]

        with (
            patch("app.features.core.reminders.service.CalendarEventService") as MockEventService,
            patch("app.features.core.reminders.service.ShoppingRepository") as MockShoppingRepo,
            patch("app.features.core.reminders.service.WorkingMemoryRepository") as MockWMRepo,
            patch("app.features.core.reminders.service.local_now", return_value=NOW),
        ):
            MockEventService.return_value.get_events = AsyncMock(return_value=[])
            MockShoppingRepo.return_value.list = AsyncMock(return_value=[])
            MockWMRepo.return_value.list = AsyncMock(return_value=[])
            MockWMRepo.return_value.upsert = AsyncMock()

            digest = await _service(mock_session, mock_task_service).build_due_digest()

        mock_task_service.update_task.assert_not_awaited()
        assert "1 other task(s) without a due date" in digest.text


class TestDigestGrouping:
    async def test_groups_by_urgency_and_sorts_by_priority_then_deadline(
        self, mock_session, mock_task_service
    ):
        tasks = [
            _make_task(id=31, title="Call bank", deadline=NOW + timedelta(hours=6),
                       urgency="NORMAL", priority="LOW"),
            _make_task(id=32, title="Send invoice", deadline=NOW + timedelta(hours=1),
                       urgency="NORMAL", priority="MEDIUM"),
            _make_task(id=33, title="Take Medicine: Night routine", deadline=None,
                       urgency="NORMAL", priority="HIGH"),
            _make_task(id=34, title="Pay rent", deadline=NOW - timedelta(hours=2),
                       urgency="URGENT", priority="LOW"),
        ]
        mock_task_service.get_tasks.return_value = tasks

        with (
            patch("app.features.core.reminders.service.CalendarEventService") as MockEventService,
            patch("app.features.core.reminders.service.ShoppingRepository") as MockShoppingRepo,
            patch("app.features.core.reminders.service.WorkingMemoryRepository") as MockWMRepo,
            patch("app.features.core.reminders.service.local_now", return_value=NOW),
        ):
            MockEventService.return_value.get_events = AsyncMock(return_value=[])
            MockShoppingRepo.return_value.list = AsyncMock(return_value=[])
            MockWMRepo.return_value.list = AsyncMock(return_value=[])
            MockWMRepo.return_value.upsert = AsyncMock()

            digest = await _service(mock_session, mock_task_service).build_due_digest()

        assert digest.text == (
            "⏰ Reminders\n"
            "Urgent tasks:\n"
            "- Pay rent (LOW, overdue)\n"
            "\n"
            "Normal tasks:\n"
            "- Take Medicine: Night routine (HIGH)\n"
            "- Send invoice (MEDIUM, due 11:00)\n"
            "- Call bank (LOW, due 16:00)"
        )

    async def test_overdue_sorts_before_dated_within_same_priority(
        self, mock_session, mock_task_service
    ):
        tasks = [
            _make_task(id=35, title="Later today", deadline=NOW + timedelta(hours=2),
                       urgency="URGENT", priority="LOW"),
            _make_task(id=36, title="Already late", deadline=NOW - timedelta(hours=1),
                       urgency="URGENT", priority="LOW"),
        ]
        mock_task_service.get_tasks.return_value = tasks

        with (
            patch("app.features.core.reminders.service.CalendarEventService") as MockEventService,
            patch("app.features.core.reminders.service.ShoppingRepository") as MockShoppingRepo,
            patch("app.features.core.reminders.service.WorkingMemoryRepository") as MockWMRepo,
            patch("app.features.core.reminders.service.local_now", return_value=NOW),
        ):
            MockEventService.return_value.get_events = AsyncMock(return_value=[])
            MockShoppingRepo.return_value.list = AsyncMock(return_value=[])
            MockWMRepo.return_value.list = AsyncMock(return_value=[])
            MockWMRepo.return_value.upsert = AsyncMock()

            digest = await _service(mock_session, mock_task_service).build_due_digest()

        assert digest.text.index("Already late") < digest.text.index("Later today")

    async def test_deadline_tomorrow_is_labelled(self, mock_session, mock_task_service):
        task = _make_task(
            id=37, title="Early flight", deadline=NOW + timedelta(hours=20),
            urgency="NORMAL", priority="MEDIUM",
        )
        mock_task_service.get_tasks.return_value = [task]

        with (
            patch("app.features.core.reminders.service.CalendarEventService") as MockEventService,
            patch("app.features.core.reminders.service.ShoppingRepository") as MockShoppingRepo,
            patch("app.features.core.reminders.service.WorkingMemoryRepository") as MockWMRepo,
            patch("app.features.core.reminders.service.local_now", return_value=NOW),
        ):
            MockEventService.return_value.get_events = AsyncMock(return_value=[])
            MockShoppingRepo.return_value.list = AsyncMock(return_value=[])
            MockWMRepo.return_value.list = AsyncMock(return_value=[])
            MockWMRepo.return_value.upsert = AsyncMock()

            digest = await _service(mock_session, mock_task_service).build_due_digest()

        assert "- Early flight (MEDIUM, due tomorrow 06:00)" in digest.text


class TestReminderFrequency:
    """The dedup TTL sets how often the hourly cron (08:00-22:00) re-reminds a task."""

    def test_urgent_high_reminds_every_hourly_run(self):
        assert escalation.task_dedup_ttl("URGENT", "HIGH", False, default_reminder_settings()) < timedelta(hours=1)

    def test_urgent_cadence_slows_down_with_priority(self):
        settings = default_reminder_settings()
        high = escalation.task_dedup_ttl("URGENT", "HIGH", False, settings)
        medium = escalation.task_dedup_ttl("URGENT", "MEDIUM", False, settings)
        low = escalation.task_dedup_ttl("URGENT", "LOW", False, settings)
        assert high < medium < low
        assert timedelta(hours=1) < medium < timedelta(hours=2)
        assert timedelta(hours=3) < low < timedelta(hours=4)

    def test_high_priority_reminds_four_times_a_day(self):
        ttl = escalation.task_dedup_ttl("NORMAL", "HIGH", False, default_reminder_settings())
        assert timedelta(hours=3) < ttl < timedelta(hours=4)

    def test_medium_priority_reminds_twice_a_day(self):
        ttl = escalation.task_dedup_ttl("NORMAL", "MEDIUM", False, default_reminder_settings())
        assert timedelta(hours=7) < ttl < timedelta(hours=8)

    def test_low_priority_reminds_once_a_day(self):
        assert escalation.task_dedup_ttl("NORMAL", "LOW", False, default_reminder_settings()) >= timedelta(hours=24)

    def test_overload_slows_urgent_reminders_to_the_configured_interval(self):
        ttl = escalation.task_dedup_ttl("URGENT", "HIGH", True, default_reminder_settings())
        assert timedelta(hours=3) < ttl < timedelta(hours=4)

    def test_overload_never_speeds_a_task_up(self):
        settings = default_reminder_settings(overload_urgent_interval_hours=1)
        assert escalation.task_dedup_ttl("URGENT", "LOW", True, settings) == escalation.task_dedup_ttl(
            "URGENT", "LOW", False, settings
        )

    def test_overload_leaves_normal_tasks_alone(self):
        settings = default_reminder_settings()
        assert escalation.task_dedup_ttl("NORMAL", "HIGH", True, settings) == escalation.task_dedup_ttl(
            "NORMAL", "HIGH", False, settings
        )

    async def test_due_today_medium_task_marker_uses_twice_a_day_ttl(self, mock_session, mock_task_service):
        task = _make_task(
            id=14, title="Send invoice", deadline=NOW + timedelta(hours=5),
            urgency="NORMAL", priority="MEDIUM",
        )
        mock_task_service.get_tasks.return_value = [task]

        with (
            patch("app.features.core.reminders.service.CalendarEventService") as MockEventService,
            patch("app.features.core.reminders.service.ShoppingRepository") as MockShoppingRepo,
            patch("app.features.core.reminders.service.WorkingMemoryRepository") as MockWMRepo,
            patch("app.features.core.reminders.service.local_now", return_value=NOW),
        ):
            MockEventService.return_value.get_events = AsyncMock(return_value=[])
            MockShoppingRepo.return_value.list = AsyncMock(return_value=[])
            MockWMRepo.return_value.list = AsyncMock(return_value=[])
            MockWMRepo.return_value.upsert = AsyncMock()
            before = datetime.now(timezone.utc)

            digest = await _service(mock_session, mock_task_service).build_due_digest()

        assert "- Send invoice (MEDIUM, due 15:00)" in digest.text
        marker = MockWMRepo.return_value.upsert.call_args.args[0]
        assert marker.key == f"reminder:task:14:{NOW.date().isoformat()}"
        assert timedelta(hours=7) < marker.expires_at - before < timedelta(hours=8)


def _snooze_list_side_effect(snoozed_task_id: int):
    from app.features.core.reminders.service import undated_escalation_snooze_key

    def _side_effect(filters):
        if filters.key == undated_escalation_snooze_key(snoozed_task_id):
            return [MagicMock()]
        return []

    return _side_effect


class TestSnoozeUndatedEscalation:
    async def test_upserts_marker_with_default_days(self):
        from app.features.core.reminders.service import snooze_undated_escalation, undated_escalation_snooze_key

        wm_service = AsyncMock()

        expires_at = await snooze_undated_escalation(wm_service, task_id=5)

        wm_service.upsert.assert_awaited_once()
        created = wm_service.upsert.call_args.args[0]
        assert created.key == undated_escalation_snooze_key(5)
        assert created.expires_at == expires_at

    async def test_respects_explicit_days(self):
        from app.features.core.reminders.service import snooze_undated_escalation

        wm_service = AsyncMock()
        before = datetime.now(timezone.utc)

        await snooze_undated_escalation(wm_service, task_id=5, days=3)

        created = wm_service.upsert.call_args.args[0]
        assert 2 <= (created.expires_at - before).days <= 3

    async def test_resets_urgency_when_currently_urgent(self):
        from app.features.core.reminders.service import snooze_undated_escalation
        from app.features.organizer.tasks.schemas import TaskUpdate

        wm_service = AsyncMock()
        task_service = AsyncMock()

        await snooze_undated_escalation(
            wm_service, task_id=5, task_service=task_service, current_urgency="URGENT"
        )

        task_service.update_task.assert_awaited_once_with(5, TaskUpdate(urgency="NORMAL"))

    async def test_does_not_reset_when_already_normal(self):
        from app.features.core.reminders.service import snooze_undated_escalation

        wm_service = AsyncMock()
        task_service = AsyncMock()

        await snooze_undated_escalation(
            wm_service, task_id=5, task_service=task_service, current_urgency="NORMAL"
        )

        task_service.update_task.assert_not_called()

    async def test_no_task_service_is_a_no_op_for_urgency(self):
        from app.features.core.reminders.service import snooze_undated_escalation

        wm_service = AsyncMock()

        # Should not raise even though current_urgency is URGENT and no task_service given.
        await snooze_undated_escalation(wm_service, task_id=5, current_urgency="URGENT")


class TestUndatedTaskEscalationConfigAndSnooze:
    async def test_escalation_age_respects_setting(self, mock_session, mock_task_service, mock_reminder_settings):
        task = _make_task(
            id=20, title="Organize garage", deadline=None, urgency="NORMAL", priority="LOW",
            created_at=NOW - timedelta(days=8),
        )
        mock_task_service.get_tasks.return_value = [task]
        mock_task_service.update_task.return_value = _make_task(
            id=20, title="Organize garage", deadline=None, urgency="URGENT", priority="LOW",
            created_at=NOW - timedelta(days=8),
        )
        mock_reminder_settings.get.return_value = default_reminder_settings(undated_escalation_days_low=7)

        with (
            patch("app.features.core.reminders.service.CalendarEventService") as MockEventService,
            patch("app.features.core.reminders.service.ShoppingRepository") as MockShoppingRepo,
            patch("app.features.core.reminders.service.WorkingMemoryRepository") as MockWMRepo,
            patch("app.features.core.reminders.service.local_now", return_value=NOW),
        ):
            MockEventService.return_value.get_events = AsyncMock(return_value=[])
            MockShoppingRepo.return_value.list = AsyncMock(return_value=[])
            MockWMRepo.return_value.list = AsyncMock(return_value=[])
            MockWMRepo.return_value.upsert = AsyncMock()

            digest = await _service(mock_session, mock_task_service).build_due_digest()

        mock_task_service.update_task.assert_awaited_once_with(20, TaskUpdate(urgency="URGENT"))
        assert "Urgent tasks:" in digest.text
        assert "- Organize garage (LOW)" in digest.text

    async def test_snoozed_stale_task_is_not_escalated_or_listed(self, mock_session, mock_task_service):
        task = _make_task(
            id=21, title="Learn guitar", deadline=None, urgency="NORMAL", priority="LOW",
            created_at=NOW - timedelta(days=40),
        )
        mock_task_service.get_tasks.return_value = [task]

        with (
            patch("app.features.core.reminders.service.CalendarEventService") as MockEventService,
            patch("app.features.core.reminders.service.ShoppingRepository") as MockShoppingRepo,
            patch("app.features.core.reminders.service.WorkingMemoryRepository") as MockWMRepo,
            patch("app.features.core.reminders.service.local_now", return_value=NOW),
        ):
            MockEventService.return_value.get_events = AsyncMock(return_value=[])
            MockShoppingRepo.return_value.list = AsyncMock(return_value=[])
            MockWMRepo.return_value.list = AsyncMock(side_effect=_snooze_list_side_effect(21))
            MockWMRepo.return_value.upsert = AsyncMock()

            digest = await _service(mock_session, mock_task_service).build_due_digest()

        mock_task_service.update_task.assert_not_awaited()
        assert "Learn guitar" not in digest.text
        assert "1 other task(s) without a due date" in digest.text

    async def test_snoozed_already_urgent_task_is_not_listed(self, mock_session, mock_task_service):
        task = _make_task(id=22, title="Call plumber", deadline=None, urgency="URGENT", priority="LOW")
        mock_task_service.get_tasks.return_value = [task]

        with (
            patch("app.features.core.reminders.service.CalendarEventService") as MockEventService,
            patch("app.features.core.reminders.service.ShoppingRepository") as MockShoppingRepo,
            patch("app.features.core.reminders.service.WorkingMemoryRepository") as MockWMRepo,
            patch("app.features.core.reminders.service.local_now", return_value=NOW),
        ):
            MockEventService.return_value.get_events = AsyncMock(return_value=[])
            MockShoppingRepo.return_value.list = AsyncMock(return_value=[])
            MockWMRepo.return_value.list = AsyncMock(side_effect=_snooze_list_side_effect(22))
            MockWMRepo.return_value.upsert = AsyncMock()

            digest = await _service(mock_session, mock_task_service).build_due_digest()

        assert "Call plumber" not in digest.text
        assert "1 other task(s) without a due date" in digest.text


class TestBuildDueDigestEventsAndShopping:
    async def test_imminent_event_is_included(self, mock_session, mock_task_service):
        event = _make_event(id=5, start_datetime=NOW + timedelta(hours=1))

        with (
            patch("app.features.core.reminders.service.CalendarEventService") as MockEventService,
            patch("app.features.core.reminders.service.ShoppingRepository") as MockShoppingRepo,
            patch("app.features.core.reminders.service.WorkingMemoryRepository") as MockWMRepo,
            patch("app.features.core.reminders.service.local_now", return_value=NOW),
        ):
            MockEventService.return_value.get_events = AsyncMock(return_value=[event])
            MockShoppingRepo.return_value.list = AsyncMock(return_value=[])
            MockWMRepo.return_value.list = AsyncMock(return_value=[])
            MockWMRepo.return_value.upsert = AsyncMock()

            digest = await _service(mock_session, mock_task_service).build_due_digest()

        assert "Starting soon (11:00): Team sync" in digest.text

    async def test_all_day_event_shows_all_day_not_midnight(self, mock_session, mock_task_service):
        event = _make_event(id=6, title="Schedule tax dates", start_datetime=NOW, all_day=True)

        with (
            patch("app.features.core.reminders.service.CalendarEventService") as MockEventService,
            patch("app.features.core.reminders.service.ShoppingRepository") as MockShoppingRepo,
            patch("app.features.core.reminders.service.WorkingMemoryRepository") as MockWMRepo,
            patch("app.features.core.reminders.service.local_now", return_value=NOW),
        ):
            MockEventService.return_value.get_events = AsyncMock(return_value=[event])
            MockShoppingRepo.return_value.list = AsyncMock(return_value=[])
            MockWMRepo.return_value.list = AsyncMock(return_value=[])
            MockWMRepo.return_value.upsert = AsyncMock()

            digest = await _service(mock_session, mock_task_service).build_due_digest()

        assert "Starting soon (All day): Schedule tax dates" in digest.text
        assert "00:00" not in digest.text

    async def test_event_lines_use_recurrence_expanding_service_not_raw_repository(
        self, mock_session, mock_task_service
    ):
        # ReminderService must call CalendarEventService.get_events (which expands RRULEs
        # into real next-occurrence spans) rather than querying CalendarEventRepository
        # directly, otherwise a recurring event's stale original start_datetime is reused
        # for every reminder regardless of when the next occurrence actually falls.
        event = _make_event(id=7, start_datetime=NOW + timedelta(hours=1))

        with (
            patch("app.features.core.reminders.service.CalendarEventService") as MockEventService,
            patch("app.features.core.reminders.service.ShoppingRepository") as MockShoppingRepo,
            patch("app.features.core.reminders.service.WorkingMemoryRepository") as MockWMRepo,
            patch("app.features.core.reminders.service.local_now", return_value=NOW),
        ):
            MockEventService.return_value.get_events = AsyncMock(return_value=[event])
            MockShoppingRepo.return_value.list = AsyncMock(return_value=[])
            MockWMRepo.return_value.list = AsyncMock(return_value=[])
            MockWMRepo.return_value.upsert = AsyncMock()

            await _service(mock_session, mock_task_service).build_due_digest()

        MockEventService.assert_called_once_with(provider=None, session=mock_session)
        MockEventService.return_value.get_events.assert_awaited_once()
        filters = MockEventService.return_value.get_events.call_args.args[0]
        assert filters.start_from == NOW
        assert filters.start_to == NOW + timedelta(hours=2)

    async def test_pending_shopping_items_reported_once(self, mock_session, mock_task_service):
        with (
            patch("app.features.core.reminders.service.CalendarEventService") as MockEventService,
            patch("app.features.core.reminders.service.ShoppingRepository") as MockShoppingRepo,
            patch("app.features.core.reminders.service.WorkingMemoryRepository") as MockWMRepo,
            patch("app.features.core.reminders.service.local_now", return_value=NOW),
        ):
            MockEventService.return_value.get_events = AsyncMock(return_value=[])
            MockShoppingRepo.return_value.list = AsyncMock(return_value=[MagicMock(), MagicMock()])
            MockWMRepo.return_value.list = AsyncMock(return_value=[])
            MockWMRepo.return_value.upsert = AsyncMock()

            digest = await _service(mock_session, mock_task_service).build_due_digest()

        assert "Shopping list still has 2 pending item(s)" in digest.text

    async def test_no_content_returns_empty_text(self, mock_session, mock_task_service):
        with (
            patch("app.features.core.reminders.service.CalendarEventService") as MockEventService,
            patch("app.features.core.reminders.service.ShoppingRepository") as MockShoppingRepo,
            patch("app.features.core.reminders.service.WorkingMemoryRepository") as MockWMRepo,
            patch("app.features.core.reminders.service.local_now", return_value=NOW),
        ):
            MockEventService.return_value.get_events = AsyncMock(return_value=[])
            MockShoppingRepo.return_value.list = AsyncMock(return_value=[])
            MockWMRepo.return_value.list = AsyncMock(return_value=[])
            MockWMRepo.return_value.upsert = AsyncMock()

            digest = await _service(mock_session, mock_task_service).build_due_digest()

        assert digest.has_content is False
        assert digest.text == ""


def _make_plan_item(is_done=False):
    item = MagicMock()
    item.is_done = is_done
    return item


def _make_plan(id=1, items=None):
    plan = MagicMock()
    plan.id = id
    plan.items = items if items is not None else [_make_plan_item()]
    return plan


async def _digest_with_plans(mock_session, mock_task_service, mock_study_plan_service, plans, reminded=False):
    mock_study_plan_service.return_value.get_active_plans = AsyncMock(return_value=plans)
    with (
        patch("app.features.core.reminders.service.CalendarEventService") as MockEventService,
        patch("app.features.core.reminders.service.ShoppingRepository") as MockShoppingRepo,
        patch("app.features.core.reminders.service.WorkingMemoryRepository") as MockWMRepo,
        patch("app.features.core.reminders.service.local_now", return_value=NOW),
    ):
        MockEventService.return_value.get_events = AsyncMock(return_value=[])
        MockShoppingRepo.return_value.list = AsyncMock(return_value=[])
        MockWMRepo.return_value.list = AsyncMock(return_value=[MagicMock()] if reminded else [])
        MockWMRepo.return_value.upsert = AsyncMock()

        digest = await _service(mock_session, mock_task_service).build_due_digest()
    return digest, MockWMRepo.return_value.upsert


class TestBuildDueDigestStudyPlans:
    async def test_counts_active_plans_with_open_items(
        self, mock_session, mock_task_service, mock_study_plan_service
    ):
        plans = [
            _make_plan(id=1),
            _make_plan(id=2, items=[_make_plan_item(is_done=True), _make_plan_item()]),
            _make_plan(id=3, items=[_make_plan_item(is_done=True)]),
        ]

        digest, upsert = await _digest_with_plans(mock_session, mock_task_service, mock_study_plan_service, plans)

        assert "You have open items in 2 study plan(s)" in digest.text
        upsert.assert_awaited_once()
        assert upsert.call_args[0][0].key == f"reminder:study_plans:0:{NOW.date().isoformat()}"

    async def test_no_line_when_every_active_plan_is_done(
        self, mock_session, mock_task_service, mock_study_plan_service
    ):
        plans = [_make_plan(items=[_make_plan_item(is_done=True)])]

        digest, upsert = await _digest_with_plans(mock_session, mock_task_service, mock_study_plan_service, plans)

        assert "study plan" not in digest.text
        upsert.assert_not_awaited()

    async def test_no_line_without_active_plans(self, mock_session, mock_task_service, mock_study_plan_service):
        digest, upsert = await _digest_with_plans(mock_session, mock_task_service, mock_study_plan_service, [])

        assert "study plan" not in digest.text
        upsert.assert_not_awaited()

    async def test_sent_at_most_once_a_day(self, mock_session, mock_task_service, mock_study_plan_service):
        digest, upsert = await _digest_with_plans(
            mock_session, mock_task_service, mock_study_plan_service, [_make_plan()], reminded=True
        )

        assert "study plan" not in digest.text
        upsert.assert_not_awaited()


async def _build_digest(mock_session, mock_task_service, reminded_keys=()):
    """Run build_due_digest with the collaborators the tests below don't care about stubbed."""
    with (
        patch("app.features.core.reminders.service.CalendarEventService") as MockEventService,
        patch("app.features.core.reminders.service.ShoppingRepository") as MockShoppingRepo,
        patch("app.features.core.reminders.service.WorkingMemoryRepository") as MockWMRepo,
        patch("app.features.core.reminders.service.local_now", return_value=NOW),
    ):
        MockEventService.return_value.get_events = AsyncMock(return_value=[])
        MockShoppingRepo.return_value.list = AsyncMock(return_value=[])
        MockWMRepo.return_value.list = AsyncMock(
            side_effect=lambda filters: [MagicMock()] if filters.key in reminded_keys else []
        )
        MockWMRepo.return_value.upsert = AsyncMock()
        digest = await _service(mock_session, mock_task_service).build_due_digest()
    return digest, MockWMRepo.return_value.upsert


def _marker_keys(upsert):
    return {call.args[0].key for call in upsert.await_args_list}


class TestEscalationLadder:
    async def test_overdue_low_task_within_its_grace_is_not_escalated(self, mock_session, mock_task_service):
        task = _make_task(id=1, deadline=NOW - timedelta(days=3), urgency="NORMAL", priority="LOW")
        mock_task_service.get_tasks.return_value = [task]

        digest, _ = await _build_digest(mock_session, mock_task_service)

        mock_task_service.update_task.assert_not_awaited()
        assert "Normal tasks:" in digest.text
        assert "- Pay rent (LOW, overdue)" in digest.text

    async def test_overdue_low_task_past_its_grace_is_escalated(self, mock_session, mock_task_service):
        task = _make_task(id=1, deadline=NOW - timedelta(days=8), urgency="NORMAL", priority="LOW")
        mock_task_service.get_tasks.return_value = [task]

        await _build_digest(mock_session, mock_task_service)

        mock_task_service.update_task.assert_awaited_once_with(1, TaskUpdate(urgency="URGENT"))

    async def test_overdue_medium_task_escalates_after_two_days(self, mock_session, mock_task_service):
        fresh = _make_task(id=1, deadline=NOW - timedelta(hours=47), urgency="NORMAL", priority="MEDIUM")
        stale = _make_task(id=2, deadline=NOW - timedelta(hours=49), urgency="NORMAL", priority="MEDIUM")
        mock_task_service.get_tasks.return_value = [fresh, stale]

        await _build_digest(mock_session, mock_task_service)

        mock_task_service.update_task.assert_awaited_once_with(2, TaskUpdate(urgency="URGENT"))

    async def test_grace_comes_from_settings(self, mock_session, mock_task_service, mock_reminder_settings):
        mock_reminder_settings.get.return_value = default_reminder_settings(overdue_grace_hours_low=1)
        task = _make_task(id=1, deadline=NOW - timedelta(hours=2), urgency="NORMAL", priority="LOW")
        mock_task_service.get_tasks.return_value = [task]

        await _build_digest(mock_session, mock_task_service)

        mock_task_service.update_task.assert_awaited_once_with(1, TaskUpdate(urgency="URGENT"))

    async def test_undated_high_task_escalates_after_a_week(self, mock_session, mock_task_service):
        created_at = NOW - timedelta(days=8)
        task = _make_task(id=5, title="Fix tax form", deadline=None, urgency="NORMAL", priority="HIGH", created_at=created_at)
        mock_task_service.get_tasks.return_value = [task]
        mock_task_service.update_task.return_value = _make_task(
            id=5, title="Fix tax form", deadline=None, urgency="URGENT", priority="HIGH", created_at=created_at
        )

        digest, _ = await _build_digest(mock_session, mock_task_service)

        mock_task_service.update_task.assert_awaited_once_with(5, TaskUpdate(urgency="URGENT"))
        assert "Urgent tasks:" in digest.text

    async def test_undated_medium_task_is_not_escalated_before_three_weeks(self, mock_session, mock_task_service):
        task = _make_task(id=6, deadline=None, urgency="NORMAL", priority="MEDIUM", created_at=NOW - timedelta(days=20))
        mock_task_service.get_tasks.return_value = [task]

        await _build_digest(mock_session, mock_task_service)

        mock_task_service.update_task.assert_not_awaited()


def _urgent_tasks(count, priority="HIGH"):
    return [
        _make_task(id=100 + i, title=f"Task {i}", deadline=NOW - timedelta(days=1, hours=i), urgency="URGENT", priority=priority)
        for i in range(count)
    ]


def _overloaded(mock_overload_service, **overrides):
    mock_overload_service.snapshot.return_value = ok_snapshot(level="overloaded", overdue=9, urgent=8, active=20, **overrides)


class TestOverloadedDigest:
    async def test_not_overloaded_lists_every_task_without_a_header(self, mock_session, mock_task_service):
        mock_task_service.get_tasks.return_value = _urgent_tasks(8)

        digest, _ = await _build_digest(mock_session, mock_task_service)

        assert digest.text.count("- Task ") == 8
        assert "Overloaded" not in digest.text
        assert "more task(s)" not in digest.text

    async def test_overloaded_caps_the_list_and_reports_the_rest(
        self, mock_session, mock_task_service, mock_overload_service
    ):
        _overloaded(mock_overload_service)
        mock_task_service.get_tasks.return_value = _urgent_tasks(8)

        digest, _ = await _build_digest(mock_session, mock_task_service)

        assert digest.text.count("- Task ") == 5
        assert "+3 more task(s) not shown, see the portal" in digest.text

    async def test_overloaded_header_states_the_counts(self, mock_session, mock_task_service, mock_overload_service):
        _overloaded(mock_overload_service)
        mock_task_service.get_tasks.return_value = _urgent_tasks(1)

        digest, _ = await _build_digest(mock_session, mock_task_service)

        assert digest.text.splitlines()[:2] == [
            "⏰ Reminders",
            "⚠️ Overloaded: 9 overdue, 8 urgent. Showing the top tasks only; open the portal to triage.",
        ]

    async def test_cap_comes_from_settings(
        self, mock_session, mock_task_service, mock_overload_service, mock_reminder_settings
    ):
        _overloaded(mock_overload_service)
        mock_reminder_settings.get.return_value = default_reminder_settings(overload_max_listed=2)
        mock_task_service.get_tasks.return_value = _urgent_tasks(4)

        digest, _ = await _build_digest(mock_session, mock_task_service)

        assert digest.text.count("- Task ") == 2
        assert "+2 more task(s)" in digest.text

    async def test_omitted_tasks_are_not_marked_so_they_rotate_into_the_next_run(
        self, mock_session, mock_task_service, mock_overload_service
    ):
        _overloaded(mock_overload_service)
        mock_task_service.get_tasks.return_value = _urgent_tasks(7)

        _, upsert = await _build_digest(mock_session, mock_task_service)

        # Earliest deadlines are listed first: tasks 2..6 of 0..6.
        day = NOW.date().isoformat()
        assert _marker_keys(upsert) == {f"reminder:task:{100 + i}:{day}" for i in range(2, 7)}

    async def test_the_next_run_lists_the_tasks_the_previous_one_left_out(
        self, mock_session, mock_task_service, mock_overload_service
    ):
        _overloaded(mock_overload_service)
        mock_task_service.get_tasks.return_value = _urgent_tasks(7)
        day = NOW.date().isoformat()
        already = {f"reminder:task:{100 + i}:{day}" for i in range(2, 7)}

        digest, _ = await _build_digest(mock_session, mock_task_service, reminded_keys=already)

        assert digest.text.count("- Task ") == 2
        assert "- Task 0 (HIGH, overdue)" in digest.text
        assert "- Task 1 (HIGH, overdue)" in digest.text
        assert "more task(s)" not in digest.text

    async def test_urgent_tasks_are_listed_before_normal_ones_under_the_cap(
        self, mock_session, mock_task_service, mock_overload_service
    ):
        _overloaded(mock_overload_service)
        normal = _make_task(id=1, title="Water plants", deadline=NOW + timedelta(hours=3), priority="HIGH")
        mock_task_service.get_tasks.return_value = [normal, *_urgent_tasks(5, priority="LOW")]

        digest, _ = await _build_digest(mock_session, mock_task_service)

        assert "Water plants" not in digest.text
        assert "+1 more task(s)" in digest.text

    async def test_overloaded_urgent_marker_uses_the_slow_interval(
        self, mock_session, mock_task_service, mock_overload_service
    ):
        _overloaded(mock_overload_service)
        mock_task_service.get_tasks.return_value = _urgent_tasks(1)

        before = datetime.now(timezone.utc)
        _, upsert = await _build_digest(mock_session, mock_task_service)

        marker = upsert.call_args.args[0]
        assert timedelta(hours=3) < marker.expires_at - before < timedelta(hours=4)

    async def test_a_header_alone_is_not_content(self, mock_session, mock_task_service, mock_overload_service):
        _overloaded(mock_overload_service)

        digest, _ = await _build_digest(mock_session, mock_task_service)

        assert digest.has_content is False
        assert digest.text == ""


class TestOverloadRecording:
    async def test_run_is_recorded_with_listed_and_omitted_counts(
        self, mock_session, mock_task_service, mock_overload_service
    ):
        _overloaded(mock_overload_service)
        mock_task_service.get_tasks.return_value = _urgent_tasks(8)

        await _build_digest(mock_session, mock_task_service)

        snapshot = mock_overload_service.snapshot.return_value
        mock_overload_service.record_run.assert_awaited_once_with(snapshot, listed=5, omitted=3)

    async def test_run_is_recorded_even_when_there_is_nothing_to_send(
        self, mock_session, mock_task_service, mock_overload_service
    ):
        digest, _ = await _build_digest(mock_session, mock_task_service)

        assert digest.has_content is False
        mock_overload_service.record_run.assert_awaited_once()

    async def test_overload_is_measured_after_escalation(self, mock_session, mock_task_service, mock_overload_service):
        order: list[str] = []
        mock_task_service.get_tasks.return_value = [
            _make_task(id=1, deadline=NOW - timedelta(hours=2), urgency="NORMAL", priority="HIGH")
        ]
        mock_task_service.update_task.side_effect = lambda *a, **k: order.append("escalate")
        mock_overload_service.snapshot.side_effect = lambda: order.append("snapshot") or ok_snapshot()

        await _build_digest(mock_session, mock_task_service)

        assert order == ["escalate", "snapshot"]


class TestOverloadRecovery:
    async def test_clearing_the_backlog_is_announced_once(self, mock_session, mock_task_service, mock_overload_service):
        mock_overload_service.previous_level.return_value = "overloaded"

        digest, _ = await _build_digest(mock_session, mock_task_service)

        assert digest.has_content is True
        assert "✅ Backlog cleared" in digest.text

    async def test_no_announcement_when_it_was_not_overloaded(self, mock_session, mock_task_service, mock_overload_service):
        mock_overload_service.previous_level.return_value = "elevated"

        digest, _ = await _build_digest(mock_session, mock_task_service)

        assert digest.has_content is False

    async def test_no_announcement_while_still_elevated(self, mock_session, mock_task_service, mock_overload_service):
        mock_overload_service.previous_level.return_value = "overloaded"
        mock_overload_service.snapshot.return_value = ok_snapshot(level="elevated", overdue=3)

        digest, _ = await _build_digest(mock_session, mock_task_service)

        assert "Backlog cleared" not in digest.text
