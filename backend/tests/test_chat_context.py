from datetime import date, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.features.core.chats.context import build_daily_context


def _make_task_orm(
    id=1,
    title="Task",
    status="TODO",
    deadline=None,
    recurrence_rule=None,
):
    task = MagicMock()
    task.id = id
    task.title = title
    task.status = status
    task.deadline = deadline
    task.recurrence_rule = recurrence_rule
    return task


def _make_event_orm(id=1, title="Standup", start_datetime=None, all_day=False):
    event = MagicMock()
    event.id = id
    event.title = title
    event.start_datetime = start_datetime or datetime(2026, 7, 20, 9, 0)
    event.all_day = all_day
    return event


@pytest.fixture
def mock_session():
    return AsyncMock()


@pytest.fixture(autouse=True)
def _patch_repos():
    with (
        patch("app.features.core.chats.context.TaskRepository") as MockTaskRepo,
        patch("app.features.core.chats.context.CalendarEventRepository") as MockEventRepo,
        patch("app.features.core.chats.context.local_now", return_value=datetime(2026, 7, 20, 8, 0)),
    ):
        MockTaskRepo.return_value.get_tasks = AsyncMock(return_value=[])
        MockTaskRepo.return_value.get_completions_by_task = AsyncMock(return_value={})
        MockEventRepo.return_value.get_events = AsyncMock(return_value=[])
        yield MockTaskRepo, MockEventRepo


class TestBuildDailyContext:
    @pytest.mark.asyncio
    async def test_returns_empty_string_when_nothing_due(self, mock_session):
        result = await build_daily_context(mock_session)
        assert result == ""

    @pytest.mark.asyncio
    async def test_includes_overdue_task(self, mock_session, _patch_repos):
        MockTaskRepo, _ = _patch_repos
        task = _make_task_orm(id=1, title="Pay bill", deadline=datetime(2026, 7, 18))
        MockTaskRepo.return_value.get_tasks.return_value = [task]

        result = await build_daily_context(mock_session)

        assert "Overdue tasks:" in result
        assert "Pay bill" in result

    @pytest.mark.asyncio
    async def test_includes_due_today_task(self, mock_session, _patch_repos):
        MockTaskRepo, _ = _patch_repos
        task = _make_task_orm(id=1, title="Submit report", deadline=datetime(2026, 7, 20, 18, 0))
        MockTaskRepo.return_value.get_tasks.return_value = [task]

        result = await build_daily_context(mock_session)

        assert "Due today:" in result
        assert "Submit report" in result

    @pytest.mark.asyncio
    async def test_includes_events(self, mock_session, _patch_repos):
        _, MockEventRepo = _patch_repos
        event = _make_event_orm(title="Dentist")
        MockEventRepo.return_value.get_events.return_value = [event]

        result = await build_daily_context(mock_session)

        assert "Events:" in result
        assert "Dentist" in result

    @pytest.mark.asyncio
    async def test_habit_due_today_marked_pending(self, mock_session, _patch_repos):
        MockTaskRepo, _ = _patch_repos
        task = _make_task_orm(id=1, title="Meditate", recurrence_rule="FREQ=DAILY")
        MockTaskRepo.return_value.get_tasks.return_value = [task]

        result = await build_daily_context(mock_session)

        assert "○ Meditate" in result

    @pytest.mark.asyncio
    async def test_habit_completed_today_marked_done(self, mock_session, _patch_repos):
        MockTaskRepo, _ = _patch_repos
        task = _make_task_orm(id=1, title="Meditate", recurrence_rule="FREQ=DAILY")
        MockTaskRepo.return_value.get_tasks.return_value = [task]
        MockTaskRepo.return_value.get_completions_by_task.return_value = {1: [date(2026, 7, 20)]}

        result = await build_daily_context(mock_session)

        assert "✓ Meditate" in result

    @pytest.mark.asyncio
    async def test_habit_not_due_today_excluded(self, mock_session, _patch_repos):
        # 2026-07-20 is a Monday; rule only recurs on Sundays.
        MockTaskRepo, _ = _patch_repos
        task = _make_task_orm(id=1, title="Weekly review", recurrence_rule="FREQ=WEEKLY;BYDAY=SU")
        MockTaskRepo.return_value.get_tasks.return_value = [task]

        result = await build_daily_context(mock_session)

        assert result == ""

    @pytest.mark.asyncio
    async def test_returns_empty_string_on_error(self, mock_session, _patch_repos):
        MockTaskRepo, _ = _patch_repos
        MockTaskRepo.return_value.get_tasks.side_effect = RuntimeError("boom")

        result = await build_daily_context(mock_session)

        assert result == ""
