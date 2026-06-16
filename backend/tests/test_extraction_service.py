import json
import pytest
from unittest.mock import AsyncMock, MagicMock

from app.assistant.intents.extraction_service import (
    CreateTaskArgs,
    CreateNoteArgs,
    GetCalendarArgs,
    GetTasksArgs,
    extract_args,
)
from app.shared.llm import LlmResponse


def _make_provider(response_text: str) -> MagicMock:
    provider = MagicMock()
    provider.provider = "google"
    provider.model = "gemini-2.0-flash"
    provider.complete = AsyncMock(return_value=LlmResponse(text=response_text, tokens_input=10, tokens_output=5))
    return provider


class TestExtractArgs:
    async def test_unknown_intent_returns_empty_dict(self):
        provider = _make_provider("{}")
        result = await extract_args("finance.budget_add", "some text", llm_provider=provider)
        assert result == {}
        provider.complete.assert_not_called()

    async def test_unmapped_intent_returns_empty_dict(self):
        provider = _make_provider("{}")
        result = await extract_args("unknown", "tell me a joke", llm_provider=provider)
        assert result == {}

    async def test_task_add_returns_create_task_args(self):
        payload = json.dumps({"title": "Buy milk", "due_date": "tomorrow", "priority": "high"})
        provider = _make_provider(payload)
        result = await extract_args("task.add", "Buy milk tomorrow, high priority", llm_provider=provider)
        assert result == {"title": "Buy milk", "due_date": "tomorrow", "priority": "high"}

    async def test_task_list_returns_get_tasks_args(self):
        payload = json.dumps({"filter": "overdue"})
        provider = _make_provider(payload)
        result = await extract_args("task.list", "show me overdue tasks", llm_provider=provider)
        assert result == {"filter": "overdue"}

    async def test_note_add_returns_create_note_args(self):
        payload = json.dumps({"title": "Meeting insights", "content": "Key decisions from today"})
        provider = _make_provider(payload)
        result = await extract_args("note.add", "Take a note about meeting insights", llm_provider=provider)
        assert result == {"title": "Meeting insights", "content": "Key decisions from today"}

    async def test_event_list_returns_get_calendar_args(self):
        payload = json.dumps({"date_range": "next week"})
        provider = _make_provider(payload)
        result = await extract_args("event.list", "what's on my calendar next week?", llm_provider=provider)
        assert result == {"date_range": "next week"}

    async def test_provider_called_with_user_message(self):
        payload = json.dumps({"title": "Call John"})
        provider = _make_provider(payload)
        await extract_args("task.add", "Call John tomorrow", llm_provider=provider)
        messages = provider.complete.call_args[0][0]
        assert messages[-1] == {"role": "user", "content": "Call John tomorrow"}

    async def test_schema_included_in_system_prompt(self):
        payload = json.dumps({"title": "Call John"})
        provider = _make_provider(payload)
        await extract_args("task.add", "Call John", llm_provider=provider)
        system = provider.complete.call_args[1]["system"]
        assert "title" in system

    async def test_optional_fields_default_to_none(self):
        payload = json.dumps({"title": "Review PRs"})
        provider = _make_provider(payload)
        result = await extract_args("task.add", "Review PRs", llm_provider=provider)
        assert result["due_date"] is None
        assert result["priority"] is None

    async def test_invalid_json_returns_empty_dict(self):
        provider = _make_provider("not valid json at all")
        result = await extract_args("task.add", "Buy milk", llm_provider=provider)
        assert result == {}

    async def test_provider_error_returns_empty_dict(self):
        provider = MagicMock()
        provider.provider = "google"
        provider.model = "gemini-2.0-flash"
        provider.complete = AsyncMock(side_effect=Exception("connection error"))
        result = await extract_args("task.add", "Buy milk", llm_provider=provider)
        assert result == {}
