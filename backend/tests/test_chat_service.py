import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import HTTPException

from app.features.core.chats.schemas import ChatRequest
from app.features.core.chats.service import (
    ChatService,
    _build_system_prompt,
    _strip_markdown,
    _to_message_dicts,
)
from app.features.core.embeddings.schemas import EmbeddingSearchResult
from app.features.core.messages.schemas import MessageRead
from app.shared.llm import LlmResponse


def _make_embedding_result(source_type: str, content: str, similarity: float = 0.9) -> EmbeddingSearchResult:
    return EmbeddingSearchResult(
        id=1,
        source_type=source_type,
        source_id=1,
        content=content,
        model="all-MiniLM-L6-v2",
        dimensions=384,
        embedded_at=datetime(2024, 1, 1),
        similarity=similarity,
    )


def _make_message(content: str, role: str = "user") -> MessageRead:
    return MessageRead(
        id=1,
        session_id=1,
        role=role,
        content=content,
        created_at=datetime(2024, 1, 1),
    )


def _make_llm_provider(text: str = "ok") -> MagicMock:
    provider = MagicMock()
    provider.provider = "google"
    provider.model = "gemini-2.0-flash"
    provider.complete = AsyncMock(return_value=LlmResponse(text=text, tokens_input=10, tokens_output=5))
    return provider


def _make_service(llm_text: str = "ok") -> tuple[ChatService, MagicMock, AsyncMock, AsyncMock, MagicMock]:
    session = AsyncMock()
    session.add = MagicMock()
    llm_provider = _make_llm_provider(llm_text)
    embedding_service = AsyncMock()
    embedding_service.search = AsyncMock(return_value=[])
    message_service = AsyncMock()
    message_service.list = AsyncMock(return_value=[])
    message_service.create = AsyncMock()
    memory_extraction_service = MagicMock()
    memory_extraction_service.extract_and_save = AsyncMock()
    session_summary_service = MagicMock()
    session_summary_service.get_recent_summaries = AsyncMock(return_value=[])
    service = ChatService(
        session=session,
        llm_provider=llm_provider,
        embedding_service=embedding_service,
        message_service=message_service,
        memory_extraction_service=memory_extraction_service,
        session_summary_service=session_summary_service,
    )
    return service, llm_provider, embedding_service, message_service, memory_extraction_service


class TestChatServiceResponse:
    async def test_returns_llm_response(self):
        service, _, _, message_service, _ = _make_service("Hello from Alfred!")
        message_service.list.return_value = [_make_message("Hello")]
        result = await service.chat(ChatRequest(session_id=1))
        assert result == "Hello from Alfred!"

    async def test_uses_last_user_message_as_agent_input(self):
        service, llm_provider, _, message_service, _ = _make_service()
        message_service.list.return_value = [_make_message("What tasks do I have?")]
        await service.chat(ChatRequest(session_id=1))
        messages = llm_provider.complete.call_args[0][0]
        assert messages[-1]["content"] == "What tasks do I have?"
        assert messages[-1]["role"] == "user"

    async def test_raises_422_when_no_messages_in_session(self):
        service, _, _, message_service, _ = _make_service()
        message_service.list.return_value = []
        with pytest.raises(HTTPException) as exc_info:
            await service.chat(ChatRequest(session_id=1))
        assert exc_info.value.status_code == 422


class TestChatServiceHistory:
    async def test_retrieves_history_for_session(self):
        service, _, _, message_service, _ = _make_service()
        message_service.list.return_value = [_make_message("hi")]
        await service.chat(ChatRequest(session_id=42))
        filters = message_service.list.call_args[0][0]
        assert filters.session_id == 42

    async def test_excludes_current_message_from_history(self):
        service, llm_provider, _, message_service, _ = _make_service()
        msgs = [_make_message("previous"), _make_message("current")]
        message_service.list.return_value = msgs
        await service.chat(ChatRequest(session_id=1))
        messages = llm_provider.complete.call_args[0][0]
        # history is all but last; last is current → only "previous" + "current" in messages
        assert messages[-1]["content"] == "current"
        assert len([m for m in messages if m["content"] == "previous"]) == 1

    async def test_requests_history_limit_plus_one_from_repository(self):
        service, _, _, message_service, _ = _make_service()
        message_service.list.return_value = [_make_message("hi")]
        await service.chat(ChatRequest(session_id=1))
        filters = message_service.list.call_args[0][0]
        # service delegates limiting to the repository: _HISTORY_LIMIT history + 1 current
        assert filters.limit == 11


class TestChatServiceMemorySearch:
    async def test_searches_memories_with_current_message_text(self):
        service, _, embedding_service, message_service, _ = _make_service()
        message_service.list.return_value = [_make_message("what did I note about bread?")]
        await service.chat(ChatRequest(session_id=1))
        req = embedding_service.search.call_args[0][0]
        assert req.query == "what did I note about bread?"
        assert set(req.source_types) == {"memory", "note", "task"}

    async def test_empty_memories_still_works(self):
        service, _, embedding_service, message_service, _ = _make_service("ok")
        message_service.list.return_value = [_make_message("hi")]
        embedding_service.search = AsyncMock(return_value=[])
        result = await service.chat(ChatRequest(session_id=1))
        assert result == "ok"


class TestChatServiceMessageSaving:
    async def test_saves_assistant_message_after_reply(self):
        service, _, _, message_service, _ = _make_service("Alfred's reply")
        message_service.list.return_value = [_make_message("hello", role="user")]
        await service.chat(ChatRequest(session_id=5))
        message_service.create.assert_called_once()
        created = message_service.create.call_args[0][0]
        assert created.session_id == 5
        assert created.role == "assistant"
        assert created.content == "Alfred's reply"

    async def test_assistant_message_has_no_meta(self):
        service, _, _, message_service, _ = _make_service()
        message_service.list.return_value = [_make_message("hi")]
        await service.chat(ChatRequest(session_id=1))
        created = message_service.create.call_args[0][0]
        assert created.meta is None


def _fixed_now(year=2026, month=6, day=17, hour=14, minute=30):
    return datetime(year, month, day, hour, minute, tzinfo=timezone.utc)


class TestBuildSystemPrompt:
    def test_includes_real_persona_not_fallback(self):
        prompt = _build_system_prompt([])
        # A string only present in the real persona.md — fails if path is wrong and fallback fires
        assert "Alfred" in prompt and "David" in prompt

    def test_includes_memories(self):
        memories = [_make_embedding_result("memory", "David likes bread")]
        prompt = _build_system_prompt(memories)
        assert "David likes bread" in prompt
        assert "memory" in prompt

    def test_no_memory_section_when_empty(self):
        prompt = _build_system_prompt([])
        assert "Relevant context" not in prompt

    def test_includes_current_datetime(self):
        with patch("app.features.core.chats.service.datetime") as mock_dt:
            mock_dt.now.return_value = _fixed_now()
            prompt = _build_system_prompt([])
        assert "Wednesday, June 17, 2026 at 14:30 UTC" in prompt

    def test_includes_formatting_instructions(self):
        prompt = _build_system_prompt([])
        assert "plain text" in prompt
        assert "Telegram" in prompt

    def test_includes_detected_intents_in_prompt(self):
        prompt = _build_system_prompt([], detected_intents=["event.add"])
        assert "event.add" in prompt
        assert "Parallel command pipeline" in prompt

    def test_no_intent_section_when_none(self):
        prompt = _build_system_prompt([])
        assert "Parallel command pipeline" not in prompt

    def test_command_boundary_included_when_no_intents(self):
        prompt = _build_system_prompt([])
        assert "Never offer to create" in prompt
        assert "slash command" in prompt

    def test_command_boundary_excluded_when_intents_present(self):
        prompt = _build_system_prompt([], detected_intents=["task.add"])
        assert "Never offer to create" not in prompt

    def test_includes_recent_session_summaries(self):
        summaries = [(_fixed_now(), "User discussed event scheduling.")]
        prompt = _build_system_prompt([], recent_summaries=summaries)
        assert "Recent conversations" in prompt
        assert "User discussed event scheduling." in prompt
        assert "June 17, 2026" in prompt

    def test_no_summary_section_when_empty(self):
        prompt = _build_system_prompt([], recent_summaries=[])
        assert "Recent conversations" not in prompt

    def test_summaries_appear_before_memories(self):
        memories = [_make_embedding_result("memory", "Likes coffee")]
        summaries = [(_fixed_now(), "Talked about tasks.")]
        prompt = _build_system_prompt(memories, recent_summaries=summaries)
        assert prompt.index("Recent conversations") < prompt.index("Relevant context from memory")

    def test_intent_section_appears_before_persona(self):
        prompt = _build_system_prompt([], detected_intents=["event.add"])
        assert prompt.index("Parallel command pipeline") < prompt.index("Alfred")


class TestChatServiceMemoryExtraction:
    async def test_schedules_extraction_after_chat(self):
        service, _, _, message_service, memory_extraction_service = _make_service()
        msg = _make_message("I prefer dark mode")
        message_service.list.return_value = [msg]
        with patch("app.features.core.chats.service.asyncio.create_task") as mock_create_task:
            await service.chat(ChatRequest(session_id=1))
        mock_create_task.assert_called_once()

    async def test_detected_intents_appear_in_system_prompt(self):
        service, llm_provider, _, message_service, _ = _make_service()
        message_service.list.return_value = [_make_message("add event")]
        await service.chat(ChatRequest(session_id=1, detected_intents=["event.add"]))
        system_prompt = llm_provider.complete.call_args[1]["system"]
        assert "event.add" in system_prompt
        assert "Parallel command pipeline" in system_prompt

    async def test_no_intent_hint_when_not_provided(self):
        service, llm_provider, _, message_service, _ = _make_service()
        message_service.list.return_value = [_make_message("hi")]
        await service.chat(ChatRequest(session_id=1))
        system_prompt = llm_provider.complete.call_args[1]["system"]
        assert "Parallel command pipeline" not in system_prompt


class TestStripMarkdown:
    def test_removes_bold_asterisks(self):
        assert _strip_markdown("Hello **world**") == "Hello world"

    def test_removes_italic_asterisks(self):
        assert _strip_markdown("Hello *world*") == "Hello world"

    def test_removes_italic_underscores(self):
        assert _strip_markdown("Hello _world_") == "Hello world"

    def test_removes_bold_underscores(self):
        assert _strip_markdown("Hello __world__") == "Hello world"

    def test_removes_inline_code(self):
        assert _strip_markdown("Use `print()` to debug") == "Use print() to debug"

    def test_removes_code_block(self):
        assert _strip_markdown("```\ncode here\n```") == ""

    def test_removes_headings(self):
        assert _strip_markdown("## Section title") == "Section title"

    def test_preserves_plain_text(self):
        assert _strip_markdown("Hello, how are you?") == "Hello, how are you?"

    def test_realistic_llm_response(self):
        text = "**Event Name:** Batizado Capoeira\n**Date:** Next Sunday\n**Start Time:** 3:00 PM"
        result = _strip_markdown(text)
        assert "**" not in result
        assert "Batizado Capoeira" in result


class TestToMessageDicts:
    def test_maps_user_message(self):
        messages = [_make_message("hello", role="user")]
        result = _to_message_dicts(messages)
        assert result == [{"role": "user", "content": "hello"}]

    def test_maps_assistant_message(self):
        messages = [_make_message("hi there", role="assistant")]
        result = _to_message_dicts(messages)
        assert result == [{"role": "assistant", "content": "hi there"}]

    def test_preserves_order(self):
        messages = [
            _make_message("question", role="user"),
            _make_message("answer", role="assistant"),
            _make_message("follow-up", role="user"),
        ]
        result = _to_message_dicts(messages)
        assert len(result) == 3
        assert result[0]["role"] == "user"
        assert result[1]["role"] == "assistant"

    def test_empty_list(self):
        assert _to_message_dicts([]) == []
