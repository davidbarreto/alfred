import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.assistant.intents.intent_service import IntentResult
from app.assistant.intents.shortlist_service import resolve_via_shortlist
from app.shared.llm import LlmResponse


def _make_provider(response_text: str) -> MagicMock:
    provider = MagicMock()
    provider.provider = "google"
    provider.model = "gemini-2.5-flash-lite"
    provider.complete = AsyncMock(return_value=LlmResponse(text=response_text, tokens_input=10, tokens_output=5))
    return provider


def _candidates() -> list[IntentResult]:
    return [
        IntentResult(intent="recall.search", confidence=0.45),
        IntentResult(intent="note.list", confidence=0.40),
        IntentResult(intent="task.add", confidence=0.35),
    ]


class TestResolveViaShortlist:
    async def test_empty_candidates_returns_none(self):
        provider = _make_provider("{}")
        result = await resolve_via_shortlist("some text", [], provider)
        assert result is None
        provider.complete.assert_not_called()

    async def test_picks_candidate_and_extracts_args(self):
        payload = json.dumps({"intent": "recall.search", "args": {"query": "voice commands"}})
        provider = _make_provider(payload)

        result = await resolve_via_shortlist("What did I say about voice commands?", _candidates(), provider)

        assert result is not None
        assert result.type == "recall"
        assert result.command == "search"
        assert result.source == "llm_shortlist"
        assert result.confidence == 0.45
        assert result.args == {"query": "voice commands"}

    async def test_intent_without_schema_returns_empty_args(self):
        payload = json.dumps({"intent": "note.list", "args": {}})
        provider = _make_provider(payload)

        result = await resolve_via_shortlist("show me stuff I wrote", _candidates(), provider)

        assert result.type == "note"
        assert result.command == "list"
        assert result.args == {}

    async def test_null_intent_returns_none(self):
        payload = json.dumps({"intent": None, "args": {}})
        provider = _make_provider(payload)

        result = await resolve_via_shortlist("tell me a joke", _candidates(), provider)

        assert result is None

    async def test_intent_outside_candidates_returns_none(self):
        # Guards against the LLM hallucinating an intent that wasn't in the shortlist.
        payload = json.dumps({"intent": "finance.transaction_add", "args": {"amount": 10}})
        provider = _make_provider(payload)

        result = await resolve_via_shortlist("some text", _candidates(), provider)

        assert result is None

    async def test_strips_markdown_fences(self):
        payload = "```json\n" + json.dumps({"intent": "task.add", "args": {"title": "Buy milk"}}) + "\n```"
        provider = _make_provider(payload)

        result = await resolve_via_shortlist("add a task to buy milk", _candidates(), provider)

        assert result is not None
        assert result.type == "task"
        assert result.args["title"] == "Buy milk"

    async def test_invalid_args_for_schema_returns_none(self):
        # task.add's CreateTaskArgs requires "title" — missing it should fail validation, not crash.
        payload = json.dumps({"intent": "task.add", "args": {}})
        provider = _make_provider(payload)

        result = await resolve_via_shortlist("some text", _candidates(), provider)

        assert result is None

    async def test_malformed_json_returns_none(self):
        provider = _make_provider("not json at all")

        result = await resolve_via_shortlist("some text", _candidates(), provider)

        assert result is None

    async def test_logs_llm_call_when_session_given(self):
        payload = json.dumps({"intent": "recall.search", "args": {"query": "golang"}})
        provider = _make_provider(payload)
        session = AsyncMock()

        with patch("app.assistant.intents.shortlist_service.create_llm_call", AsyncMock()) as mock_log:
            await resolve_via_shortlist("What did I say about golang?", _candidates(), provider, session=session)

        mock_log.assert_awaited_once()
        assert mock_log.call_args.kwargs["feature"] == "intent_shortlist"
