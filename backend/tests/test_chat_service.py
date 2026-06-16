import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

from fastapi import HTTPException

from app.features.core.chats.schemas import ChatRequest
from app.features.core.chats.service import (
    ChatService,
    _build_system_prompt,
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


def _make_service(llm_text: str = "ok") -> tuple[ChatService, MagicMock, AsyncMock, AsyncMock]:
    session = AsyncMock()
    session.add = MagicMock()
    llm_provider = _make_llm_provider(llm_text)
    embedding_service = AsyncMock()
    embedding_service.search = AsyncMock(return_value=[])
    message_service = AsyncMock()
    message_service.list = AsyncMock(return_value=[])
    message_service.create = AsyncMock()
    service = ChatService(
        session=session,
        llm_provider=llm_provider,
        embedding_service=embedding_service,
        message_service=message_service,
    )
    return service, llm_provider, embedding_service, message_service


class TestChatServiceResponse:
    async def test_returns_llm_response(self):
        service, _, _, message_service = _make_service("Hello from Alfred!")
        message_service.list.return_value = [_make_message("Hello")]
        result = await service.chat(ChatRequest(session_id=1))
        assert result == "Hello from Alfred!"

    async def test_uses_last_user_message_as_agent_input(self):
        service, llm_provider, _, message_service = _make_service()
        message_service.list.return_value = [_make_message("What tasks do I have?")]
        await service.chat(ChatRequest(session_id=1))
        messages = llm_provider.complete.call_args[0][0]
        assert messages[-1]["content"] == "What tasks do I have?"
        assert messages[-1]["role"] == "user"

    async def test_raises_422_when_no_messages_in_session(self):
        service, _, _, message_service = _make_service()
        message_service.list.return_value = []
        with pytest.raises(HTTPException) as exc_info:
            await service.chat(ChatRequest(session_id=1))
        assert exc_info.value.status_code == 422


class TestChatServiceHistory:
    async def test_retrieves_history_for_session(self):
        service, _, _, message_service = _make_service()
        message_service.list.return_value = [_make_message("hi")]
        await service.chat(ChatRequest(session_id=42))
        filters = message_service.list.call_args[0][0]
        assert filters.session_id == 42

    async def test_excludes_current_message_from_history(self):
        service, llm_provider, _, message_service = _make_service()
        msgs = [_make_message("previous"), _make_message("current")]
        message_service.list.return_value = msgs
        await service.chat(ChatRequest(session_id=1))
        messages = llm_provider.complete.call_args[0][0]
        # history is all but last; last is current → only "previous" + "current" in messages
        assert messages[-1]["content"] == "current"
        assert len([m for m in messages if m["content"] == "previous"]) == 1

    async def test_slices_to_last_10_history_messages(self):
        service, llm_provider, _, message_service = _make_service()
        # 11 prior messages + 1 current = 12 total; only last 10 prior should appear before current
        msgs = [_make_message(f"msg {i}") for i in range(12)]
        message_service.list.return_value = msgs
        await service.chat(ChatRequest(session_id=1))
        messages = llm_provider.complete.call_args[0][0]
        # last message is current; preceding 10 are history
        assert len(messages) == 11  # 10 history + 1 current


class TestChatServiceMemorySearch:
    async def test_searches_memories_with_current_message_text(self):
        service, _, embedding_service, message_service = _make_service()
        message_service.list.return_value = [_make_message("what did I note about bread?")]
        await service.chat(ChatRequest(session_id=1))
        req = embedding_service.search.call_args[0][0]
        assert req.query == "what did I note about bread?"
        assert set(req.source_types) == {"memory", "note", "task"}

    async def test_empty_memories_still_works(self):
        service, _, embedding_service, message_service = _make_service("ok")
        message_service.list.return_value = [_make_message("hi")]
        embedding_service.search = AsyncMock(return_value=[])
        result = await service.chat(ChatRequest(session_id=1))
        assert result == "ok"


class TestChatServiceMessageSaving:
    async def test_saves_assistant_message_after_reply(self):
        service, _, _, message_service = _make_service("Alfred's reply")
        message_service.list.return_value = [_make_message("hello", role="user")]
        await service.chat(ChatRequest(session_id=5))
        message_service.create.assert_called_once()
        created = message_service.create.call_args[0][0]
        assert created.session_id == 5
        assert created.role == "assistant"
        assert created.content == "Alfred's reply"

    async def test_assistant_message_has_no_meta(self):
        service, _, _, message_service = _make_service()
        message_service.list.return_value = [_make_message("hi")]
        await service.chat(ChatRequest(session_id=1))
        created = message_service.create.call_args[0][0]
        assert created.meta is None


class TestBuildSystemPrompt:
    def test_includes_persona(self):
        prompt = _build_system_prompt([])
        assert len(prompt) > 0

    def test_includes_memories(self):
        memories = [_make_embedding_result("memory", "David likes bread")]
        prompt = _build_system_prompt(memories)
        assert "David likes bread" in prompt
        assert "memory" in prompt

    def test_no_memory_section_when_empty(self):
        prompt = _build_system_prompt([])
        assert "Relevant context" not in prompt


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
