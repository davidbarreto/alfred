from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

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
    return task


def _make_event(id=1, title="Team sync", start_datetime=None):
    event = MagicMock()
    event.id = id
    event.title = title
    event.start_datetime = start_datetime or datetime(2026, 7, 11, 14, 30)
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


def _service(session, task_service):
    return ReminderService(session=session, task_service=task_service)


class TestBuildDueDigestTasks:
    async def test_overdue_normal_task_is_escalated_and_included(self, mock_session, mock_task_service):
        task = _make_task(id=1, deadline=NOW - timedelta(hours=2), urgency="NORMAL")
        mock_task_service.get_tasks.return_value = [task]

        with (
            patch("app.features.core.reminders.service.CalendarEventRepository") as MockEventRepo,
            patch("app.features.core.reminders.service.ShoppingRepository") as MockShoppingRepo,
            patch("app.features.core.reminders.service.WorkingMemoryRepository") as MockWMRepo,
            patch("app.features.core.reminders.service.local_now", return_value=NOW),
        ):
            MockEventRepo.return_value.get_events = AsyncMock(return_value=[])
            MockShoppingRepo.return_value.list = AsyncMock(return_value=[])
            MockWMRepo.return_value.list = AsyncMock(return_value=[])
            MockWMRepo.return_value.upsert = AsyncMock()

            digest = await _service(mock_session, mock_task_service).build_due_digest()

        mock_task_service.update_task.assert_awaited_once_with(1, TaskUpdate(urgency="URGENT"))
        assert digest.has_content is True
        assert "Urgent tasks:" in digest.text
        assert "- Pay rent (LOW, overdue)" in digest.text

    async def test_due_today_normal_task_is_not_escalated(self, mock_session, mock_task_service):
        task = _make_task(
            id=13, title="Water plants", deadline=NOW + timedelta(hours=3),
            urgency="NORMAL", priority="LOW",
        )
        mock_task_service.get_tasks.return_value = [task]

        with (
            patch("app.features.core.reminders.service.CalendarEventRepository") as MockEventRepo,
            patch("app.features.core.reminders.service.ShoppingRepository") as MockShoppingRepo,
            patch("app.features.core.reminders.service.WorkingMemoryRepository") as MockWMRepo,
            patch("app.features.core.reminders.service.local_now", return_value=NOW),
        ):
            MockEventRepo.return_value.get_events = AsyncMock(return_value=[])
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
            patch("app.features.core.reminders.service.CalendarEventRepository") as MockEventRepo,
            patch("app.features.core.reminders.service.ShoppingRepository") as MockShoppingRepo,
            patch("app.features.core.reminders.service.WorkingMemoryRepository") as MockWMRepo,
            patch("app.features.core.reminders.service.local_now", return_value=NOW),
        ):
            MockEventRepo.return_value.get_events = AsyncMock(return_value=[])
            MockShoppingRepo.return_value.list = AsyncMock(return_value=[])
            MockWMRepo.return_value.list = AsyncMock(return_value=[])
            MockWMRepo.return_value.upsert = AsyncMock()

            await _service(mock_session, mock_task_service).build_due_digest()

        mock_task_service.update_task.assert_not_awaited()

    async def test_task_already_reminded_today_is_skipped(self, mock_session, mock_task_service):
        task = _make_task(id=3, deadline=NOW - timedelta(hours=1), urgency="URGENT")
        mock_task_service.get_tasks.return_value = [task]

        with (
            patch("app.features.core.reminders.service.CalendarEventRepository") as MockEventRepo,
            patch("app.features.core.reminders.service.ShoppingRepository") as MockShoppingRepo,
            patch("app.features.core.reminders.service.WorkingMemoryRepository") as MockWMRepo,
            patch("app.features.core.reminders.service.local_now", return_value=NOW),
        ):
            MockEventRepo.return_value.get_events = AsyncMock(return_value=[])
            MockShoppingRepo.return_value.list = AsyncMock(return_value=[])
            MockWMRepo.return_value.list = AsyncMock(return_value=[MagicMock()])
            MockWMRepo.return_value.upsert = AsyncMock()

            digest = await _service(mock_session, mock_task_service).build_due_digest()

        MockWMRepo.return_value.upsert.assert_not_awaited()
        assert digest.has_content is False

    async def test_mark_reminded_upserts_marker_with_urgent_ttl_under_an_hour(
        self, mock_session, mock_task_service
    ):
        task = _make_task(id=7, deadline=NOW - timedelta(hours=1), urgency="URGENT")
        mock_task_service.get_tasks.return_value = [task]

        with (
            patch("app.features.core.reminders.service.CalendarEventRepository") as MockEventRepo,
            patch("app.features.core.reminders.service.ShoppingRepository") as MockShoppingRepo,
            patch("app.features.core.reminders.service.WorkingMemoryRepository") as MockWMRepo,
            patch("app.features.core.reminders.service.local_now", return_value=NOW),
        ):
            MockEventRepo.return_value.get_events = AsyncMock(return_value=[])
            MockShoppingRepo.return_value.list = AsyncMock(return_value=[])
            MockWMRepo.return_value.list = AsyncMock(return_value=[])
            MockWMRepo.return_value.upsert = AsyncMock()
            before = datetime.now(timezone.utc)

            digest = await _service(mock_session, mock_task_service).build_due_digest()

        assert "- Pay rent (LOW, overdue)" in digest.text
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
            patch("app.features.core.reminders.service.CalendarEventRepository") as MockEventRepo,
            patch("app.features.core.reminders.service.ShoppingRepository") as MockShoppingRepo,
            patch("app.features.core.reminders.service.WorkingMemoryRepository") as MockWMRepo,
            patch("app.features.core.reminders.service.local_now", return_value=NOW),
        ):
            MockEventRepo.return_value.get_events = AsyncMock(return_value=[])
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
            patch("app.features.core.reminders.service.CalendarEventRepository") as MockEventRepo,
            patch("app.features.core.reminders.service.ShoppingRepository") as MockShoppingRepo,
            patch("app.features.core.reminders.service.WorkingMemoryRepository") as MockWMRepo,
            patch("app.features.core.reminders.service.local_now", return_value=NOW),
        ):
            MockEventRepo.return_value.get_events = AsyncMock(return_value=[])
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
            patch("app.features.core.reminders.service.CalendarEventRepository") as MockEventRepo,
            patch("app.features.core.reminders.service.ShoppingRepository") as MockShoppingRepo,
            patch("app.features.core.reminders.service.WorkingMemoryRepository") as MockWMRepo,
            patch("app.features.core.reminders.service.local_now", return_value=NOW),
        ):
            MockEventRepo.return_value.get_events = AsyncMock(return_value=[])
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
            patch("app.features.core.reminders.service.CalendarEventRepository") as MockEventRepo,
            patch("app.features.core.reminders.service.ShoppingRepository") as MockShoppingRepo,
            patch("app.features.core.reminders.service.WorkingMemoryRepository") as MockWMRepo,
            patch("app.features.core.reminders.service.local_now", return_value=NOW),
        ):
            MockEventRepo.return_value.get_events = AsyncMock(return_value=[])
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
            patch("app.features.core.reminders.service.CalendarEventRepository") as MockEventRepo,
            patch("app.features.core.reminders.service.ShoppingRepository") as MockShoppingRepo,
            patch("app.features.core.reminders.service.WorkingMemoryRepository") as MockWMRepo,
            patch("app.features.core.reminders.service.local_now", return_value=NOW),
        ):
            MockEventRepo.return_value.get_events = AsyncMock(return_value=[])
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
            patch("app.features.core.reminders.service.CalendarEventRepository") as MockEventRepo,
            patch("app.features.core.reminders.service.ShoppingRepository") as MockShoppingRepo,
            patch("app.features.core.reminders.service.WorkingMemoryRepository") as MockWMRepo,
            patch("app.features.core.reminders.service.local_now", return_value=NOW),
        ):
            MockEventRepo.return_value.get_events = AsyncMock(return_value=[])
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
            patch("app.features.core.reminders.service.CalendarEventRepository") as MockEventRepo,
            patch("app.features.core.reminders.service.ShoppingRepository") as MockShoppingRepo,
            patch("app.features.core.reminders.service.WorkingMemoryRepository") as MockWMRepo,
            patch("app.features.core.reminders.service.local_now", return_value=NOW),
        ):
            MockEventRepo.return_value.get_events = AsyncMock(return_value=[])
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
            patch("app.features.core.reminders.service.CalendarEventRepository") as MockEventRepo,
            patch("app.features.core.reminders.service.ShoppingRepository") as MockShoppingRepo,
            patch("app.features.core.reminders.service.WorkingMemoryRepository") as MockWMRepo,
            patch("app.features.core.reminders.service.local_now", return_value=NOW),
        ):
            MockEventRepo.return_value.get_events = AsyncMock(return_value=[])
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
            patch("app.features.core.reminders.service.CalendarEventRepository") as MockEventRepo,
            patch("app.features.core.reminders.service.ShoppingRepository") as MockShoppingRepo,
            patch("app.features.core.reminders.service.WorkingMemoryRepository") as MockWMRepo,
            patch("app.features.core.reminders.service.local_now", return_value=NOW),
        ):
            MockEventRepo.return_value.get_events = AsyncMock(return_value=[])
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
            patch("app.features.core.reminders.service.CalendarEventRepository") as MockEventRepo,
            patch("app.features.core.reminders.service.ShoppingRepository") as MockShoppingRepo,
            patch("app.features.core.reminders.service.WorkingMemoryRepository") as MockWMRepo,
            patch("app.features.core.reminders.service.local_now", return_value=NOW),
        ):
            MockEventRepo.return_value.get_events = AsyncMock(return_value=[])
            MockShoppingRepo.return_value.list = AsyncMock(return_value=[])
            MockWMRepo.return_value.list = AsyncMock(return_value=[])
            MockWMRepo.return_value.upsert = AsyncMock()

            digest = await _service(mock_session, mock_task_service).build_due_digest()

        mock_task_service.update_task.assert_not_awaited()
        assert "Normal tasks:" in digest.text
        assert "- Renew passport (HIGH)" in digest.text

    async def test_undated_task_older_than_a_month_is_escalated_and_listed(self, mock_session, mock_task_service):
        stale_created_at = NOW - timedelta(days=31)
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
            patch("app.features.core.reminders.service.CalendarEventRepository") as MockEventRepo,
            patch("app.features.core.reminders.service.ShoppingRepository") as MockShoppingRepo,
            patch("app.features.core.reminders.service.WorkingMemoryRepository") as MockWMRepo,
            patch("app.features.core.reminders.service.local_now", return_value=NOW),
        ):
            MockEventRepo.return_value.get_events = AsyncMock(return_value=[])
            MockShoppingRepo.return_value.list = AsyncMock(return_value=[])
            MockWMRepo.return_value.list = AsyncMock(return_value=[])
            MockWMRepo.return_value.upsert = AsyncMock()

            digest = await _service(mock_session, mock_task_service).build_due_digest()

        mock_task_service.update_task.assert_awaited_once_with(8, TaskUpdate(urgency="URGENT"))
        assert "Urgent tasks:" in digest.text
        assert "- Learn guitar (LOW)" in digest.text

    async def test_undated_task_under_a_month_old_is_not_escalated(self, mock_session, mock_task_service):
        task = _make_task(
            id=9, title="Learn guitar", deadline=None, urgency="NORMAL", priority="LOW",
            created_at=NOW - timedelta(days=10),
        )
        mock_task_service.get_tasks.return_value = [task]

        with (
            patch("app.features.core.reminders.service.CalendarEventRepository") as MockEventRepo,
            patch("app.features.core.reminders.service.ShoppingRepository") as MockShoppingRepo,
            patch("app.features.core.reminders.service.WorkingMemoryRepository") as MockWMRepo,
            patch("app.features.core.reminders.service.local_now", return_value=NOW),
        ):
            MockEventRepo.return_value.get_events = AsyncMock(return_value=[])
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
            patch("app.features.core.reminders.service.CalendarEventRepository") as MockEventRepo,
            patch("app.features.core.reminders.service.ShoppingRepository") as MockShoppingRepo,
            patch("app.features.core.reminders.service.WorkingMemoryRepository") as MockWMRepo,
            patch("app.features.core.reminders.service.local_now", return_value=NOW),
        ):
            MockEventRepo.return_value.get_events = AsyncMock(return_value=[])
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
            patch("app.features.core.reminders.service.CalendarEventRepository") as MockEventRepo,
            patch("app.features.core.reminders.service.ShoppingRepository") as MockShoppingRepo,
            patch("app.features.core.reminders.service.WorkingMemoryRepository") as MockWMRepo,
            patch("app.features.core.reminders.service.local_now", return_value=NOW),
        ):
            MockEventRepo.return_value.get_events = AsyncMock(return_value=[])
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
            patch("app.features.core.reminders.service.CalendarEventRepository") as MockEventRepo,
            patch("app.features.core.reminders.service.ShoppingRepository") as MockShoppingRepo,
            patch("app.features.core.reminders.service.WorkingMemoryRepository") as MockWMRepo,
            patch("app.features.core.reminders.service.local_now", return_value=NOW),
        ):
            MockEventRepo.return_value.get_events = AsyncMock(return_value=[])
            MockShoppingRepo.return_value.list = AsyncMock(return_value=[])
            MockWMRepo.return_value.list = AsyncMock(return_value=[])
            MockWMRepo.return_value.upsert = AsyncMock()

            digest = await _service(mock_session, mock_task_service).build_due_digest()

        assert "- Early flight (MEDIUM, due tomorrow 06:00)" in digest.text


class TestReminderFrequency:
    """The dedup TTL sets how often the hourly cron (08:00-22:00) re-reminds a task."""

    def test_urgent_reminds_every_hourly_run(self):
        from app.features.core.reminders.service import _task_dedup_ttl

        assert _task_dedup_ttl("URGENT", "LOW") < timedelta(hours=1)

    def test_high_priority_reminds_four_times_a_day(self):
        from app.features.core.reminders.service import _task_dedup_ttl

        ttl = _task_dedup_ttl("NORMAL", "HIGH")
        assert timedelta(hours=3) < ttl < timedelta(hours=4)

    def test_medium_priority_reminds_twice_a_day(self):
        from app.features.core.reminders.service import _task_dedup_ttl

        ttl = _task_dedup_ttl("NORMAL", "MEDIUM")
        assert timedelta(hours=7) < ttl < timedelta(hours=8)

    def test_low_priority_reminds_once_a_day(self):
        from app.features.core.reminders.service import _task_dedup_ttl

        assert _task_dedup_ttl("NORMAL", "LOW") >= timedelta(hours=24)

    def test_urgency_wins_over_priority(self):
        from app.features.core.reminders.service import _task_dedup_ttl

        assert _task_dedup_ttl("URGENT", "HIGH") < timedelta(hours=1)

    async def test_due_today_medium_task_marker_uses_twice_a_day_ttl(self, mock_session, mock_task_service):
        task = _make_task(
            id=14, title="Send invoice", deadline=NOW + timedelta(hours=5),
            urgency="NORMAL", priority="MEDIUM",
        )
        mock_task_service.get_tasks.return_value = [task]

        with (
            patch("app.features.core.reminders.service.CalendarEventRepository") as MockEventRepo,
            patch("app.features.core.reminders.service.ShoppingRepository") as MockShoppingRepo,
            patch("app.features.core.reminders.service.WorkingMemoryRepository") as MockWMRepo,
            patch("app.features.core.reminders.service.local_now", return_value=NOW),
        ):
            MockEventRepo.return_value.get_events = AsyncMock(return_value=[])
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


class TestUndatedTaskEscalationConfigAndSnooze:
    async def test_escalation_age_respects_setting(self, mock_session, mock_task_service):
        task = _make_task(
            id=20, title="Organize garage", deadline=None, urgency="NORMAL", priority="LOW",
            created_at=NOW - timedelta(days=8),
        )
        mock_task_service.get_tasks.return_value = [task]
        mock_task_service.update_task.return_value = _make_task(
            id=20, title="Organize garage", deadline=None, urgency="URGENT", priority="LOW",
            created_at=NOW - timedelta(days=8),
        )
        settings = MagicMock(undated_task_escalation_days=7)

        with (
            patch("app.features.core.reminders.service.CalendarEventRepository") as MockEventRepo,
            patch("app.features.core.reminders.service.ShoppingRepository") as MockShoppingRepo,
            patch("app.features.core.reminders.service.WorkingMemoryRepository") as MockWMRepo,
            patch("app.features.core.reminders.service.local_now", return_value=NOW),
            patch("app.features.core.reminders.service.get_settings", return_value=settings),
        ):
            MockEventRepo.return_value.get_events = AsyncMock(return_value=[])
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
            patch("app.features.core.reminders.service.CalendarEventRepository") as MockEventRepo,
            patch("app.features.core.reminders.service.ShoppingRepository") as MockShoppingRepo,
            patch("app.features.core.reminders.service.WorkingMemoryRepository") as MockWMRepo,
            patch("app.features.core.reminders.service.local_now", return_value=NOW),
        ):
            MockEventRepo.return_value.get_events = AsyncMock(return_value=[])
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
            patch("app.features.core.reminders.service.CalendarEventRepository") as MockEventRepo,
            patch("app.features.core.reminders.service.ShoppingRepository") as MockShoppingRepo,
            patch("app.features.core.reminders.service.WorkingMemoryRepository") as MockWMRepo,
            patch("app.features.core.reminders.service.local_now", return_value=NOW),
        ):
            MockEventRepo.return_value.get_events = AsyncMock(return_value=[])
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
            patch("app.features.core.reminders.service.CalendarEventRepository") as MockEventRepo,
            patch("app.features.core.reminders.service.ShoppingRepository") as MockShoppingRepo,
            patch("app.features.core.reminders.service.WorkingMemoryRepository") as MockWMRepo,
            patch("app.features.core.reminders.service.local_now", return_value=NOW),
        ):
            MockEventRepo.return_value.get_events = AsyncMock(return_value=[event])
            MockShoppingRepo.return_value.list = AsyncMock(return_value=[])
            MockWMRepo.return_value.list = AsyncMock(return_value=[])
            MockWMRepo.return_value.upsert = AsyncMock()

            digest = await _service(mock_session, mock_task_service).build_due_digest()

        assert "Starting soon (11:00): Team sync" in digest.text

    async def test_pending_shopping_items_reported_once(self, mock_session, mock_task_service):
        with (
            patch("app.features.core.reminders.service.CalendarEventRepository") as MockEventRepo,
            patch("app.features.core.reminders.service.ShoppingRepository") as MockShoppingRepo,
            patch("app.features.core.reminders.service.WorkingMemoryRepository") as MockWMRepo,
            patch("app.features.core.reminders.service.local_now", return_value=NOW),
        ):
            MockEventRepo.return_value.get_events = AsyncMock(return_value=[])
            MockShoppingRepo.return_value.list = AsyncMock(return_value=[MagicMock(), MagicMock()])
            MockWMRepo.return_value.list = AsyncMock(return_value=[])
            MockWMRepo.return_value.upsert = AsyncMock()

            digest = await _service(mock_session, mock_task_service).build_due_digest()

        assert "Shopping list still has 2 pending item(s)" in digest.text

    async def test_no_content_returns_empty_text(self, mock_session, mock_task_service):
        with (
            patch("app.features.core.reminders.service.CalendarEventRepository") as MockEventRepo,
            patch("app.features.core.reminders.service.ShoppingRepository") as MockShoppingRepo,
            patch("app.features.core.reminders.service.WorkingMemoryRepository") as MockWMRepo,
            patch("app.features.core.reminders.service.local_now", return_value=NOW),
        ):
            MockEventRepo.return_value.get_events = AsyncMock(return_value=[])
            MockShoppingRepo.return_value.list = AsyncMock(return_value=[])
            MockWMRepo.return_value.list = AsyncMock(return_value=[])
            MockWMRepo.return_value.upsert = AsyncMock()

            digest = await _service(mock_session, mock_task_service).build_due_digest()

        assert digest.has_content is False
        assert digest.text == ""
