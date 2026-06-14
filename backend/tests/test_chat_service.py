import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from app.features.core.chats.schemas import ChatRequest, ExecutedCommandResult
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


def _make_message(input_text: str, response: str | None = "ok") -> MessageRead:
    return MessageRead(
        id=1,
        session_id=1,
        source="telegram",
        input=input_text,
        response=response,
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
        service, _, _ = _make_service()
        with patch("app.features.core.chats.service._create_agent", return_value=_stub_agent("Hello from Alfred!")):
            result = await service.chat(ChatRequest(text="Hello"))
        assert result == "Hello from Alfred!"

    async def test_uses_text_as_agent_input(self):
        service, _, _ = _make_service()
        stub = _stub_agent("response")
        with patch("app.features.core.chats.service._create_agent", return_value=stub):
            await service.chat(ChatRequest(text="What tasks do I have?"))
        call_args = stub.run.call_args
        assert call_args[0][0] == "What tasks do I have?"


class TestChatServiceHistory:
    async def test_retrieves_history_when_session_id_provided(self):
        service, _, message_service = _make_service()
        with patch("app.features.core.chats.service._create_agent", return_value=_stub_agent("ok")):
            await service.chat(ChatRequest(text="hi", session_id=42))
        message_service.list.assert_called_once()
        filters = message_service.list.call_args[0][0]
        assert filters.session_id == 42

    async def test_no_history_retrieval_without_session_id(self):
        service, _, message_service = _make_service()
        with patch("app.features.core.chats.service._create_agent", return_value=_stub_agent("ok")):
            await service.chat(ChatRequest(text="hi", session_id=None))
        message_service.list.assert_not_called()

    async def test_passes_history_to_agent(self):
        service, _, message_service = _make_service()
        messages = [_make_message("previous question", "previous answer")]
        message_service.list = AsyncMock(return_value=messages)
        stub = _stub_agent("ok")
        with patch("app.features.core.chats.service._create_agent", return_value=stub):
            await service.chat(ChatRequest(text="follow-up", session_id=1))
        call_kwargs = stub.run.call_args[1]
        assert "message_history" in call_kwargs
        assert len(call_kwargs["message_history"]) == 2  # request + response

    async def test_slices_to_last_10_messages(self):
        service, _, message_service = _make_service()
        messages = [_make_message(f"msg {i}") for i in range(15)]
        message_service.list = AsyncMock(return_value=messages)
        stub = _stub_agent("ok")
        with patch("app.features.core.chats.service._create_agent", return_value=stub):
            await service.chat(ChatRequest(text="hi", session_id=1))
        call_kwargs = stub.run.call_args[1]
        # 10 messages × 2 history entries each (request + response) = 20
        assert len(call_kwargs["message_history"]) == 20


class TestChatServiceMemorySearch:
    async def test_searches_memories_with_user_text(self):
        service, embedding_service, _ = _make_service()
        with patch("app.features.core.chats.service._create_agent", return_value=_stub_agent("ok")):
            await service.chat(ChatRequest(text="what did I note about bread?"))
        embedding_service.search.assert_called_once()
        req = embedding_service.search.call_args[0][0]
        assert req.query == "what did I note about bread?"
        assert set(req.source_types) == {"memory", "note", "task"}

    async def test_empty_memories_still_works(self):
        service, embedding_service, _ = _make_service()
        embedding_service.search = AsyncMock(return_value=[])
        with patch("app.features.core.chats.service._create_agent", return_value=_stub_agent("ok")):
            result = await service.chat(ChatRequest(text="hi"))
        assert result == "ok"


class TestChatServiceMessageSaving:
    async def test_saves_message_when_session_id_provided(self):
        service, _, message_service = _make_service()
        with patch("app.features.core.chats.service._create_agent", return_value=_stub_agent("Alfred's reply")):
            await service.chat(ChatRequest(text="hello", session_id=5, source="telegram"))
        message_service.create.assert_called_once()
        created = message_service.create.call_args[0][0]
        assert created.session_id == 5
        assert created.source == "telegram"
        assert created.input == "hello"
        assert created.response == "Alfred's reply"

    async def test_does_not_save_without_session_id(self):
        service, _, message_service = _make_service()
        with patch("app.features.core.chats.service._create_agent", return_value=_stub_agent("ok")):
            await service.chat(ChatRequest(text="hi", session_id=None))
        message_service.create.assert_not_called()


class TestBuildSystemPrompt:
    def test_includes_persona(self):
        prompt = _build_system_prompt([], [])
        assert len(prompt) > 0

    def test_includes_memories(self):
        memories = [_make_embedding_result("memory", "David likes bread")]
        prompt = _build_system_prompt(memories, [])
        assert "David likes bread" in prompt
        assert "memory" in prompt

    def test_includes_executed_commands(self):
        cmds = [ExecutedCommandResult(type="task", command="add", result="Task created")]
        prompt = _build_system_prompt([], cmds)
        assert "task.add" in prompt
        assert "Task created" in prompt

    def test_no_memory_section_when_empty(self):
        prompt = _build_system_prompt([], [])
        assert "Relevant context" not in prompt

    def test_no_commands_section_when_empty(self):
        prompt = _build_system_prompt([], [])
        assert "Commands executed" not in prompt


class TestToMessageHistory:
    def test_converts_message_pair(self):
        messages = [_make_message("hello", "hi there")]
        history = _to_message_history(messages)
        assert len(history) == 2

    def test_skips_response_when_none(self):
        messages = [_make_message("hello", None)]
        history = _to_message_history(messages)
        assert len(history) == 1

    def test_empty_list(self):
        assert _to_message_history([]) == []

    def test_multiple_messages(self):
        messages = [_make_message(f"msg{i}") for i in range(3)]
        history = _to_message_history(messages)
        assert len(history) == 6
