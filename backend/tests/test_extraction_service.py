import json
import pytest
from unittest.mock import AsyncMock, MagicMock

from app.assistant.intents.extraction_service import (
    CreateEventArgs,
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

    async def test_strips_json_markdown_fences(self):
        raw = {"title": "Buy milk", "due_date": None, "priority": None}
        fenced = f"```json\n{json.dumps(raw)}\n```"
        provider = _make_provider(fenced)
        result = await extract_args("task.add", "Buy milk", llm_provider=provider)
        assert result["title"] == "Buy milk"

    async def test_strips_plain_markdown_fences(self):
        raw = {"title": "Buy milk", "due_date": None, "priority": None}
        fenced = f"```\n{json.dumps(raw)}\n```"
        provider = _make_provider(fenced)
        result = await extract_args("task.add", "Buy milk", llm_provider=provider)
        assert result["title"] == "Buy milk"


class TestExtractArgsEventAdd:
    async def test_event_add_extracts_fields(self):
        payload = json.dumps({
            "title": "Batizado Capoeira",
            "start": "2026-06-22T15:00:00",
            "end": "2026-06-22T16:00:00",
            "additional_notes": None,
            "recurrence": None,
        })
        provider = _make_provider(payload)
        result = await extract_args("event.add", "Create an event Batizado Capoeira next Sunday at 3 PM (1h)", llm_provider=provider)
        assert result["title"] == "Batizado Capoeira"
        assert result["start"] == "2026-06-22T15:00:00"
        assert result["end"] == "2026-06-22T16:00:00"

    async def test_event_add_optional_fields_default_to_none(self):
        payload = json.dumps({"title": "Standup"})
        provider = _make_provider(payload)
        result = await extract_args("event.add", "Add standup tomorrow", llm_provider=provider)
        assert result["start"] is None
        assert result["end"] is None
        assert result["additional_notes"] is None
        assert result["recurrence"] is None

    async def test_event_add_date_context_in_system_prompt(self):
        payload = json.dumps({"title": "Gym"})
        provider = _make_provider(payload)
        await extract_args("event.add", "Add gym session", llm_provider=provider)
        system = provider.complete.call_args[1]["system"]
        assert "current date" in system.lower()

    async def test_non_date_intent_has_no_date_context(self):
        payload = json.dumps({"title": "My note", "content": None})
        provider = _make_provider(payload)
        await extract_args("note.add", "Save a note", llm_provider=provider)
        system = provider.complete.call_args[1]["system"]
        assert "current date" not in system.lower()

    async def test_event_add_strips_markdown_fences(self):
        raw = {"title": "Batizado Capoeira", "start": "2026-06-22T15:00:00", "end": "2026-06-22T16:00:00", "additional_notes": None, "recurrence": None}
        fenced = f"```json\n{json.dumps(raw)}\n```"
        provider = _make_provider(fenced)
        result = await extract_args("event.add", "Create event next Sunday", llm_provider=provider)
        assert result["title"] == "Batizado Capoeira"
