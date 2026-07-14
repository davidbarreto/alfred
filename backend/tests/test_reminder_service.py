from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.exc import IntegrityError

from app.features.core.reminders.service import ReminderService
from app.features.organizer.tasks.schemas import TaskUpdate


def _make_task(id=1, title="Pay rent", deadline=None, urgency="NORMAL", priority="LOW", created_at=None):
    task = MagicMock()
    task.id = id
    task.title = title
    task.deadline = deadline
    task.urgency = urgency
    task.priority = priority
    task.created_at = created_at or NOW
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
            MockWMRepo.return_value.create = AsyncMock()

            digest = await _service(mock_session, mock_task_service).build_due_digest()

        mock_task_service.update_task.assert_awaited_once_with(1, TaskUpdate(urgency="URGENT"))
        assert digest.has_content is True
        assert "Overdue (URGENT): Pay rent" in digest.text

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
            MockWMRepo.return_value.create = AsyncMock()

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
            MockWMRepo.return_value.create = AsyncMock()

            digest = await _service(mock_session, mock_task_service).build_due_digest()

        MockWMRepo.return_value.create.assert_not_awaited()
        assert digest.has_content is False

    async def test_concurrent_mark_reminded_race_is_swallowed(self, mock_session, mock_task_service):
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
            MockWMRepo.return_value.create = AsyncMock(
                side_effect=IntegrityError("insert", {}, Exception("duplicate key"))
            )

            digest = await _service(mock_session, mock_task_service).build_due_digest()

        mock_session.rollback.assert_awaited_once()
        assert "Overdue (URGENT): Pay rent" in digest.text

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
            MockWMRepo.return_value.create = AsyncMock()

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
            MockWMRepo.return_value.create = AsyncMock()

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
            MockWMRepo.return_value.create = AsyncMock()

            digest = await _service(mock_session, mock_task_service).build_due_digest()

        MockWMRepo.return_value.create.assert_not_awaited()
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
            MockWMRepo.return_value.create = AsyncMock()

            digest = await _service(mock_session, mock_task_service).build_due_digest()

        mock_task_service.update_task.assert_not_awaited()
        assert "No due date (NORMAL): Renew passport" in digest.text

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
            MockWMRepo.return_value.create = AsyncMock()

            digest = await _service(mock_session, mock_task_service).build_due_digest()

        mock_task_service.update_task.assert_awaited_once_with(8, TaskUpdate(urgency="URGENT"))
        assert "No due date (URGENT): Learn guitar" in digest.text

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
            MockWMRepo.return_value.create = AsyncMock()

            digest = await _service(mock_session, mock_task_service).build_due_digest()

        mock_task_service.update_task.assert_not_awaited()
        assert "1 other task(s) without a due date" in digest.text


def _snooze_list_side_effect(snoozed_task_id: int):
    from app.features.core.reminders.service import undated_escalation_snooze_key

    def _side_effect(filters):
        if filters.key == undated_escalation_snooze_key(snoozed_task_id):
            return [MagicMock()]
        return []

    return _side_effect


class TestSnoozeUndatedEscalation:
    async def test_creates_marker_with_default_days(self):
        from app.features.core.reminders.service import snooze_undated_escalation, undated_escalation_snooze_key

        wm_service = AsyncMock()
        wm_service.list.return_value = []

        expires_at = await snooze_undated_escalation(wm_service, task_id=5)

        wm_service.create.assert_awaited_once()
        created = wm_service.create.call_args.args[0]
        assert created.key == undated_escalation_snooze_key(5)
        assert created.expires_at == expires_at

    async def test_respects_explicit_days(self):
        from app.features.core.reminders.service import snooze_undated_escalation

        wm_service = AsyncMock()
        wm_service.list.return_value = []
        before = datetime.now(timezone.utc)

        await snooze_undated_escalation(wm_service, task_id=5, days=3)

        created = wm_service.create.call_args.args[0]
        assert 2 <= (created.expires_at - before).days <= 3

    async def test_replaces_existing_marker(self):
        from app.features.core.reminders.service import snooze_undated_escalation

        wm_service = AsyncMock()
        wm_service.list.return_value = [MagicMock(id=99)]

        await snooze_undated_escalation(wm_service, task_id=5)

        wm_service.delete.assert_awaited_once_with(99)


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
            MockWMRepo.return_value.create = AsyncMock()

            digest = await _service(mock_session, mock_task_service).build_due_digest()

        mock_task_service.update_task.assert_awaited_once_with(20, TaskUpdate(urgency="URGENT"))
        assert "No due date (URGENT): Organize garage" in digest.text

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
            MockWMRepo.return_value.create = AsyncMock()

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
            MockWMRepo.return_value.create = AsyncMock()

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
            MockWMRepo.return_value.create = AsyncMock()

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
            MockWMRepo.return_value.create = AsyncMock()

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
            MockWMRepo.return_value.create = AsyncMock()

            digest = await _service(mock_session, mock_task_service).build_due_digest()

        assert digest.has_content is False
        assert digest.text == ""
