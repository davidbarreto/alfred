import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.assistant.intents.extraction_service import (
    CreateTaskArgs,
    CreateNoteArgs,
    GetCalendarArgs,
    GetTasksArgs,
    extract_args,
)


@pytest.fixture()
def mock_agent():
    agent = MagicMock()
    agent.run = AsyncMock()
    return agent


class TestExtractArgs:
    async def test_unknown_intent_returns_empty_dict(self):
        result = await extract_args("finance.budget_add", "some text")
        assert result == {}

    async def test_unmapped_intent_returns_empty_dict(self):
        result = await extract_args("unknown", "tell me a joke")
        assert result == {}

    async def test_task_add_returns_create_task_args(self, mock_agent):
        mock_agent.run.return_value = MagicMock(
            output=CreateTaskArgs(title="Buy milk", due_date="tomorrow", priority="high")
        )
        with patch("app.assistant.intents.extraction_service._get_agent", return_value=mock_agent):
            result = await extract_args("task.add", "Buy milk tomorrow, high priority")

        assert result == {"title": "Buy milk", "due_date": "tomorrow", "priority": "high"}

    async def test_task_list_returns_get_tasks_args(self, mock_agent):
        mock_agent.run.return_value = MagicMock(
            output=GetTasksArgs(filter="overdue")
        )
        with patch("app.assistant.intents.extraction_service._get_agent", return_value=mock_agent):
            result = await extract_args("task.list", "show me overdue tasks")

        assert result == {"filter": "overdue"}

    async def test_note_add_returns_create_note_args(self, mock_agent):
        mock_agent.run.return_value = MagicMock(
            output=CreateNoteArgs(title="Meeting insights", content="Key decisions from today")
        )
        with patch("app.assistant.intents.extraction_service._get_agent", return_value=mock_agent):
            result = await extract_args("note.add", "Take a note about meeting insights")

        assert result == {"title": "Meeting insights", "content": "Key decisions from today"}

    async def test_event_list_returns_get_calendar_args(self, mock_agent):
        mock_agent.run.return_value = MagicMock(
            output=GetCalendarArgs(date_range="next week")
        )
        with patch("app.assistant.intents.extraction_service._get_agent", return_value=mock_agent):
            result = await extract_args("event.list", "what's on my calendar next week?")

        assert result == {"date_range": "next week"}

    async def test_agent_run_called_with_input_text(self, mock_agent):
        mock_agent.run.return_value = MagicMock(
            output=CreateTaskArgs(title="Call John")
        )
        with patch("app.assistant.intents.extraction_service._get_agent", return_value=mock_agent):
            await extract_args("task.add", "Call John tomorrow")

        mock_agent.run.assert_called_once_with("Call John tomorrow")

    async def test_optional_fields_default_to_none(self, mock_agent):
        mock_agent.run.return_value = MagicMock(
            output=CreateTaskArgs(title="Review PRs")
        )
        with patch("app.assistant.intents.extraction_service._get_agent", return_value=mock_agent):
            result = await extract_args("task.add", "Review PRs")

        assert result["due_date"] is None
        assert result["priority"] is None
