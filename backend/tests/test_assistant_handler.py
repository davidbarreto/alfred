from datetime import datetime
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.assistant.commands.handlers.assistant import handle_assistant
from app.features.organizer.calendar_events.schemas import EventRead
from app.features.organizer.notes.schemas import NoteRead
from app.features.organizer.tasks.schemas import TaskRead


def _make_task(**kwargs) -> TaskRead:
    defaults = dict(
        id=1,
        title="Task",
        status="TODO",
        priority="LOW",
        urgency="NORMAL",
        deadline=None,
        tags=[],
        recurrence_rule=None,
        created_at=datetime(2026, 7, 1),
    )
    defaults.update(kwargs)
    return TaskRead(**defaults)


def _make_note(**kwargs) -> NoteRead:
    defaults = dict(
        id=1,
        title="Note",
        content="",
        tags=[],
        created_at=datetime(2026, 7, 1),
        updated_at=datetime(2026, 7, 1),
    )
    defaults.update(kwargs)
    return NoteRead(**defaults)


@pytest.fixture
def task_service():
    svc = AsyncMock()
    svc.get_tasks.return_value = []
    return svc


@pytest.fixture
def event_service():
    svc = AsyncMock()
    svc.get_events.return_value = []
    return svc


@pytest.fixture
def note_service():
    svc = AsyncMock()
    svc.get_notes.return_value = []
    return svc


class TestHandleAssistant:
    @pytest.mark.asyncio
    async def test_unknown_command_raises(self, task_service, event_service, note_service):
        with pytest.raises(HTTPException) as exc_info:
            await handle_assistant("other", {}, task_service, event_service, note_service)
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_filters_to_active_tasks(self, task_service, event_service, note_service):
        task_service.get_tasks.return_value = [
            _make_task(id=1, status="TODO"),
            _make_task(id=2, status="DONE"),
            _make_task(id=3, status="CANCELLED"),
        ]

        result = await handle_assistant("focus", {}, task_service, event_service, note_service)

        assert [t["id"] for t in result["tasks"]] == [1]

    @pytest.mark.asyncio
    async def test_sorts_priority_before_overdue(self, task_service, event_service, note_service):
        # A HIGH-priority undated task must outrank an overdue LOW-priority one --
        # priority beats date, matching the reminders module's ordering.
        task_service.get_tasks.return_value = [
            _make_task(id=1, priority="LOW", deadline=datetime(2020, 1, 1)),
            _make_task(id=2, priority="HIGH", deadline=None),
        ]

        result = await handle_assistant("focus", {}, task_service, event_service, note_service)

        assert result["tasks"][0]["id"] == 2

    @pytest.mark.asyncio
    async def test_includes_recent_notes_as_context(self, task_service, event_service, note_service):
        note_service.get_notes.return_value = [_make_note(id=1, title="Idea")]

        result = await handle_assistant("focus", {}, task_service, event_service, note_service)

        assert result["notes"][0]["title"] == "Idea"

    @pytest.mark.asyncio
    async def test_includes_todays_events(self, task_service, event_service, note_service):
        event_service.get_events.return_value = [
            EventRead(
                id=1,
                title="Standup",
                start_datetime=datetime(2026, 7, 1, 9, 0),
                end_datetime=datetime(2026, 7, 1, 9, 30),
            )
        ]

        result = await handle_assistant("focus", {}, task_service, event_service, note_service)

        assert result["events_today"][0]["title"] == "Standup"
