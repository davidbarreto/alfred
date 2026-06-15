import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import HTTPException

from app.features.core.chats.schemas import ChatRequest
from app.features.core.chats.service import (
    ChatService,
    _build_system_prompt,
    _to_message_history,
)
from app.features.core.embeddings.schemas import EmbeddingSearchResult
from app.features.core.messages.schemas import MessageRead


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


def _make_service() -> tuple[ChatService, AsyncMock, AsyncMock]:
    embedding_service = AsyncMock()
    embedding_service.search = AsyncMock(return_value=[])
    message_service = AsyncMock()
    message_service.list = AsyncMock(return_value=[])
    message_service.create = AsyncMock()
    service = ChatService(embedding_service=embedding_service, message_service=message_service)
    return service, embedding_service, message_service


def _stub_agent(text: str) -> MagicMock:
    mock_result = MagicMock()
    mock_result.output = text
    mock_instance = MagicMock()
    mock_instance.run = AsyncMock(return_value=mock_result)
    return mock_instance


class TestChatServiceResponse:
    async def test_returns_llm_response(self):
        service, _, message_service = _make_service()
        message_service.list.return_value = [_make_message("Hello")]
        with patch("app.features.core.chats.service._create_agent", return_value=_stub_agent("Hello from Alfred!")):
            result = await service.chat(ChatRequest(session_id=1))
        assert result == "Hello from Alfred!"

    async def test_uses_last_user_message_as_agent_input(self):
        service, _, message_service = _make_service()
        message_service.list.return_value = [_make_message("What tasks do I have?")]
        stub = _stub_agent("response")
        with patch("app.features.core.chats.service._create_agent", return_value=stub):
            await service.chat(ChatRequest(session_id=1))
        assert stub.run.call_args[0][0] == "What tasks do I have?"

    async def test_raises_422_when_no_messages_in_session(self):
        service, _, message_service = _make_service()
        message_service.list.return_value = []
        with pytest.raises(HTTPException) as exc_info:
            await service.chat(ChatRequest(session_id=1))
        assert exc_info.value.status_code == 422


class TestChatServiceHistory:
    async def test_retrieves_history_for_session(self):
        service, _, message_service = _make_service()
        message_service.list.return_value = [_make_message("hi")]
        with patch("app.features.core.chats.service._create_agent", return_value=_stub_agent("ok")):
            await service.chat(ChatRequest(session_id=42))
        filters = message_service.list.call_args[0][0]
        assert filters.session_id == 42

    async def test_excludes_current_message_from_history(self):
        service, _, message_service = _make_service()
        msgs = [_make_message("previous"), _make_message("current")]
        message_service.list.return_value = msgs
        stub = _stub_agent("ok")
        with patch("app.features.core.chats.service._create_agent", return_value=stub):
            await service.chat(ChatRequest(session_id=1))
        history = stub.run.call_args[1]["message_history"]
        assert len(history) == 1  # only "previous"

    async def test_slices_to_last_10_history_messages(self):
        service, _, message_service = _make_service()
        # 11 prior messages + 1 current = 12 total; only last 10 prior should appear in history
        msgs = [_make_message(f"msg {i}") for i in range(12)]
        message_service.list.return_value = msgs
        stub = _stub_agent("ok")
        with patch("app.features.core.chats.service._create_agent", return_value=stub):
            await service.chat(ChatRequest(session_id=1))
        history = stub.run.call_args[1]["message_history"]
        assert len(history) == 10


class TestChatServiceMemorySearch:
    async def test_searches_memories_with_current_message_text(self):
        service, embedding_service, message_service = _make_service()
        message_service.list.return_value = [_make_message("what did I note about bread?")]
        with patch("app.features.core.chats.service._create_agent", return_value=_stub_agent("ok")):
            await service.chat(ChatRequest(session_id=1))
        req = embedding_service.search.call_args[0][0]
        assert req.query == "what did I note about bread?"
        assert set(req.source_types) == {"memory", "note", "task"}

    async def test_empty_memories_still_works(self):
        service, embedding_service, message_service = _make_service()
        message_service.list.return_value = [_make_message("hi")]
        embedding_service.search = AsyncMock(return_value=[])
        with patch("app.features.core.chats.service._create_agent", return_value=_stub_agent("ok")):
            result = await service.chat(ChatRequest(session_id=1))
        assert result == "ok"


class TestChatServiceMessageSaving:
    async def test_saves_assistant_message_after_reply(self):
        service, _, message_service = _make_service()
        message_service.list.return_value = [_make_message("hello", role="user")]
        with patch("app.features.core.chats.service._create_agent", return_value=_stub_agent("Alfred's reply")):
            await service.chat(ChatRequest(session_id=5))
        message_service.create.assert_called_once()
        created = message_service.create.call_args[0][0]
        assert created.session_id == 5
        assert created.role == "assistant"
        assert created.content == "Alfred's reply"

    async def test_assistant_message_has_no_meta(self):
        service, _, message_service = _make_service()
        message_service.list.return_value = [_make_message("hi")]
        with patch("app.features.core.chats.service._create_agent", return_value=_stub_agent("ok")):
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


class TestToMessageHistory:
    def test_maps_user_message_to_model_request(self):
        messages = [_make_message("hello", role="user")]
        history = _to_message_history(messages)
        assert len(history) == 1

    def test_maps_assistant_message_to_model_response(self):
        messages = [_make_message("hi there", role="assistant")]
        history = _to_message_history(messages)
        assert len(history) == 1

    def test_preserves_order(self):
        messages = [
            _make_message("question", role="user"),
            _make_message("answer", role="assistant"),
            _make_message("follow-up", role="user"),
        ]
        history = _to_message_history(messages)
        assert len(history) == 3

    def test_empty_list(self):
        assert _to_message_history([]) == []
