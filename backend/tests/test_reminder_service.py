from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.features.core.reminders.service import ReminderService
from app.features.organizer.tasks.schemas import TaskUpdate


def _make_task(id=1, title="Pay rent", deadline=None, urgency="NORMAL", priority="LOW"):
    task = MagicMock()
    task.id = id
    task.title = title
    task.deadline = deadline
    task.urgency = urgency
    task.priority = priority
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

    async def test_undated_task_is_included_but_not_escalated(self, mock_session, mock_task_service):
        task = _make_task(id=5, title="Read that book", deadline=None, urgency="NORMAL")
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
        assert "No due date: Read that book" in digest.text

    async def test_undated_task_already_reminded_today_is_skipped(self, mock_session, mock_task_service):
        task = _make_task(id=6, title="Read that book", deadline=None, urgency="NORMAL")
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
