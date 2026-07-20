from datetime import date, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.features.briefing.evening_summary_service import EveningDigestSummaryService


def _make_task_orm(id=1, title="Task", status="TODO", priority="LOW", deadline=None, recurrence_rule=None, tags=None):
    task = MagicMock()
    task.id = id
    task.title = title
    task.status = status
    task.priority = priority
    task.urgency = "NORMAL"
    task.deadline = deadline
    task.recurrence_rule = recurrence_rule
    tag_mocks = []
    for name in (tags or []):
        t = MagicMock()
        t.name = name
        tag_mocks.append(t)
    task.tags = tag_mocks
    return task


def _make_event_orm(id=1, title="Standup", start_datetime=None, end_datetime=None, all_day=False, location=None):
    event = MagicMock()
    event.id = id
    event.title = title
    event.start_datetime = start_datetime or datetime(2026, 7, 19, 9, 0)
    event.end_datetime = end_datetime or datetime(2026, 7, 19, 9, 30)
    event.all_day = all_day
    event.location = location
    return event


def _make_note_orm(id=1, title="Note", content=""):
    note = MagicMock()
    note.id = id
    note.title = title
    note.content = content
    return note


@pytest.fixture
def mock_session():
    return AsyncMock()


@pytest.fixture
def service(mock_session):
    return EveningDigestSummaryService(session=mock_session)


@pytest.fixture(autouse=True)
def _patch_repos():
    with (
        patch("app.features.briefing.evening_summary_service.TaskRepository") as MockTaskRepo,
        patch("app.features.briefing.evening_summary_service.CalendarEventRepository") as MockEventRepo,
        patch("app.features.briefing.evening_summary_service.NoteRepository") as MockNoteRepo,
        patch("app.features.briefing.evening_summary_service.local_now", return_value=datetime(2026, 7, 18, 20, 0)),
    ):
        MockTaskRepo.return_value.get_tasks = AsyncMock(return_value=[])
        MockTaskRepo.return_value.get_completed_task_ids_for_date = AsyncMock(return_value=set())
        MockTaskRepo.return_value.get_tasks_completed_on = AsyncMock(return_value=[])
        MockEventRepo.return_value.get_events = AsyncMock(return_value=[])
        MockNoteRepo.return_value.get_notes = AsyncMock(return_value=[])
        yield MockTaskRepo, MockEventRepo, MockNoteRepo


class TestBuild:
    @pytest.mark.asyncio
    async def test_empty_digest(self, service):
        result = await service.build()

        assert result.date == date(2026, 7, 18)
        assert result.wins == []
        assert result.tasks == []
        assert result.tomorrow_events == []
        assert result.notes == []

    @pytest.mark.asyncio
    async def test_recurring_completion_today_is_a_win(self, service, _patch_repos):
        MockTaskRepo, _, _ = _patch_repos
        task = _make_task_orm(id=1, title="Water plants", recurrence_rule="FREQ=DAILY")
        MockTaskRepo.return_value.get_tasks.return_value = [task]
        MockTaskRepo.return_value.get_completed_task_ids_for_date.return_value = {1}

        result = await service.build()

        assert [w.title for w in result.wins] == ["Water plants"]

    @pytest.mark.asyncio
    async def test_non_recurring_completed_today_is_a_win(self, service, _patch_repos):
        MockTaskRepo, _, _ = _patch_repos
        done_task = _make_task_orm(id=2, title="Pay bill")
        MockTaskRepo.return_value.get_tasks_completed_on.return_value = [done_task]

        result = await service.build()

        assert [w.title for w in result.wins] == ["Pay bill"]

    @pytest.mark.asyncio
    async def test_recurring_task_not_due_today_excluded_from_tasks(self, service, _patch_repos):
        # local_now is patched to 2026-07-18, a Saturday; rule only recurs on Sundays.
        MockTaskRepo, _, _ = _patch_repos
        task = _make_task_orm(id=1, title="Weekly review", recurrence_rule="FREQ=WEEKLY;BYDAY=SU")
        MockTaskRepo.return_value.get_tasks.return_value = [task]

        result = await service.build()

        assert result.tasks == []

    @pytest.mark.asyncio
    async def test_recurring_task_completed_today_excluded_from_tasks(self, service, _patch_repos):
        MockTaskRepo, _, _ = _patch_repos
        task = _make_task_orm(id=1, title="Water plants", recurrence_rule="FREQ=DAILY")
        MockTaskRepo.return_value.get_tasks.return_value = [task]
        MockTaskRepo.return_value.get_completed_task_ids_for_date.return_value = {1}

        result = await service.build()

        assert result.tasks == []

    @pytest.mark.asyncio
    async def test_active_tasks_sorted_priority_first(self, service, _patch_repos):
        MockTaskRepo, _, _ = _patch_repos
        overdue_low = _make_task_orm(id=1, title="Low overdue", priority="LOW", deadline=datetime(2020, 1, 1))
        undated_high = _make_task_orm(id=2, title="High undated", priority="HIGH", deadline=None)
        MockTaskRepo.return_value.get_tasks.return_value = [overdue_low, undated_high]

        result = await service.build()

        assert result.tasks[0].title == "High undated"

    @pytest.mark.asyncio
    async def test_marks_overdue_tasks(self, service, _patch_repos):
        MockTaskRepo, _, _ = _patch_repos
        task = _make_task_orm(id=1, title="Overdue", deadline=datetime(2020, 1, 1))
        MockTaskRepo.return_value.get_tasks.return_value = [task]

        result = await service.build()

        assert result.tasks[0].is_overdue is True

    @pytest.mark.asyncio
    async def test_includes_tomorrow_events(self, service, _patch_repos):
        _, MockEventRepo, _ = _patch_repos
        event = _make_event_orm(title="Dentist")
        MockEventRepo.return_value.get_events.return_value = [event]

        result = await service.build()

        assert result.tomorrow_events[0].title == "Dentist"

    @pytest.mark.asyncio
    async def test_all_day_event_label(self, service, _patch_repos):
        _, MockEventRepo, _ = _patch_repos
        event = _make_event_orm(title="Holiday", all_day=True)
        MockEventRepo.return_value.get_events.return_value = [event]

        result = await service.build()

        assert result.tomorrow_events[0].start_time == "All day"
        assert result.tomorrow_events[0].end_time is None

    @pytest.mark.asyncio
    async def test_includes_recent_notes(self, service, _patch_repos):
        _, _, MockNoteRepo = _patch_repos
        MockNoteRepo.return_value.get_notes.return_value = [_make_note_orm(title="Idea")]

        result = await service.build()

        assert result.notes[0].title == "Idea"
