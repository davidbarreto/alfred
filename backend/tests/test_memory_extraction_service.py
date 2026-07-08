import json
import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from app.features.core.memories.extraction_service import MemoryExtractionService
from app.features.core.embeddings.schemas import EmbeddingSearchResult
from app.features.core.memories.schemas import MemoryRead
from app.shared.llm import LlmResponse


def _make_llm_provider(response_text: str) -> MagicMock:
    provider = MagicMock()
    provider.complete = AsyncMock(
        return_value=LlmResponse(text=response_text, tokens_input=10, tokens_output=5)
    )
    return provider


def _make_embedding_provider() -> MagicMock:
    provider = MagicMock()
    provider.model = "all-MiniLM-L6-v2"
    provider.dimensions = 384
    return provider


def _make_memory_read(memory_id: int, importance: float = 0.5) -> MemoryRead:
    return MemoryRead(
        id=memory_id,
        category="fact",
        content="existing memory",
        importance=importance,
        confidence=1.0,
        active=True,
        created_at=datetime(2024, 1, 1),
        updated_at=datetime(2024, 1, 1),
    )


def _make_embedding_result(source_id: int) -> EmbeddingSearchResult:
    return EmbeddingSearchResult(
        id=1,
        source_type="memory",
        source_id=source_id,
        content="existing memory",
        model="all-MiniLM-L6-v2",
        dimensions=384,
        embedded_at=datetime(2024, 1, 1),
        similarity=0.92,
    )


def _make_service() -> tuple[MemoryExtractionService, MagicMock, MagicMock]:
    llm_provider = _make_llm_provider("[]")
    embedding_provider = _make_embedding_provider()
    service = MemoryExtractionService(
        llm_provider=llm_provider,
        embedding_provider=embedding_provider,
    )
    return service, llm_provider, embedding_provider


class TestMemoryExtractionService:
    async def test_creates_memory_for_valid_candidate(self):
        candidates = [{"category": "preference", "content": "Prefers dark mode", "importance": 0.7, "confidence": 0.9}]
        service, llm_provider, _ = _make_service()
        llm_provider.complete.return_value = LlmResponse(
            text=json.dumps(candidates), tokens_input=10, tokens_output=5
        )

        memory_service = AsyncMock()
        memory_service.get = AsyncMock(return_value=None)
        memory_service.create = AsyncMock(return_value=_make_memory_read(99))
        embedding_service = AsyncMock()
        embedding_service.search = AsyncMock(return_value=[])
        embedding_service.embed = AsyncMock()

        with patch("app.features.core.memories.extraction_service.async_session") as mock_session_ctx:
            mock_session = AsyncMock()
            mock_session_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session_ctx.return_value.__aexit__ = AsyncMock(return_value=False)
            with (
                patch("app.features.core.memories.extraction_service.MemoryService", return_value=memory_service),
                patch("app.features.core.memories.extraction_service.EmbeddingService", return_value=embedding_service),
            ):
                await service.extract_and_save("I prefer dark mode", message_id=1)

        memory_service.create.assert_called_once()
        created = memory_service.create.call_args[0][0]
        assert created.content == "Prefers dark mode"
        assert created.category == "preference"
        assert created.origin_message_id == 1
        embedding_service.embed.assert_called_once()

    async def test_skips_extraction_when_llm_returns_empty(self):
        service, llm_provider, _ = _make_service()
        llm_provider.complete.return_value = LlmResponse(text="[]", tokens_input=10, tokens_output=5)

        with patch("app.features.core.memories.extraction_service.async_session") as mock_session_ctx:
            mock_session = AsyncMock()
            mock_session_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session_ctx.return_value.__aexit__ = AsyncMock(return_value=False)
            memory_service = AsyncMock()
            with (
                patch("app.features.core.memories.extraction_service.MemoryService", return_value=memory_service),
                patch("app.features.core.memories.extraction_service.EmbeddingService", return_value=AsyncMock()),
            ):
                await service.extract_and_save("What time is it?", message_id=1)

        memory_service.create.assert_not_called()

    async def test_bumps_importance_for_duplicate_memory(self):
        candidates = [{"category": "fact", "content": "Likes coffee", "importance": 0.6, "confidence": 1.0}]
        service, llm_provider, _ = _make_service()
        llm_provider.complete.return_value = LlmResponse(text=json.dumps(candidates), tokens_input=10, tokens_output=5)

        existing_memory = _make_memory_read(memory_id=5, importance=0.6)
        memory_service = AsyncMock()
        memory_service.get = AsyncMock(return_value=existing_memory)
        memory_service.update = AsyncMock()
        embedding_service = AsyncMock()
        embedding_service.search = AsyncMock(return_value=[_make_embedding_result(source_id=5)])

        with patch("app.features.core.memories.extraction_service.async_session") as mock_session_ctx:
            mock_session = AsyncMock()
            mock_session_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session_ctx.return_value.__aexit__ = AsyncMock(return_value=False)
            with (
                patch("app.features.core.memories.extraction_service.MemoryService", return_value=memory_service),
                patch("app.features.core.memories.extraction_service.EmbeddingService", return_value=embedding_service),
            ):
                await service.extract_and_save("I like coffee", message_id=2)

        memory_service.update.assert_called_once()
        update_arg = memory_service.update.call_args[0][1]
        assert update_arg.importance == pytest.approx(0.7)
        memory_service.create.assert_not_called()

    async def test_importance_capped_at_1_when_bumping(self):
        candidates = [{"category": "fact", "content": "Likes coffee", "importance": 0.6, "confidence": 1.0}]
        service, llm_provider, _ = _make_service()
        llm_provider.complete.return_value = LlmResponse(text=json.dumps(candidates), tokens_input=10, tokens_output=5)

        existing_memory = _make_memory_read(memory_id=5, importance=0.95)
        memory_service = AsyncMock()
        memory_service.get = AsyncMock(return_value=existing_memory)
        memory_service.update = AsyncMock()
        embedding_service = AsyncMock()
        embedding_service.search = AsyncMock(return_value=[_make_embedding_result(source_id=5)])

        with patch("app.features.core.memories.extraction_service.async_session") as mock_session_ctx:
            mock_session = AsyncMock()
            mock_session_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session_ctx.return_value.__aexit__ = AsyncMock(return_value=False)
            with (
                patch("app.features.core.memories.extraction_service.MemoryService", return_value=memory_service),
                patch("app.features.core.memories.extraction_service.EmbeddingService", return_value=embedding_service),
            ):
                await service.extract_and_save("I like coffee", message_id=2)

        update_arg = memory_service.update.call_args[0][1]
        assert update_arg.importance == pytest.approx(1.0)

    async def test_handles_invalid_json_gracefully(self):
        service, llm_provider, _ = _make_service()
        llm_provider.complete.return_value = LlmResponse(
            text="not valid json", tokens_input=10, tokens_output=5
        )
        # Should not raise
        await service.extract_and_save("some message", message_id=1)

    async def test_strips_markdown_fences_from_llm_response(self):
        candidates = [{"category": "fact", "content": "Wakes at 6am", "importance": 0.5, "confidence": 1.0}]
        fenced = f"```json\n{json.dumps(candidates)}\n```"
        service, llm_provider, _ = _make_service()
        llm_provider.complete.return_value = LlmResponse(text=fenced, tokens_input=10, tokens_output=5)

        memory_service = AsyncMock()
        memory_service.create = AsyncMock(return_value=_make_memory_read(1))
        embedding_service = AsyncMock()
        embedding_service.search = AsyncMock(return_value=[])
        embedding_service.embed = AsyncMock()

        with patch("app.features.core.memories.extraction_service.async_session") as mock_session_ctx:
            mock_session = AsyncMock()
            mock_session_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session_ctx.return_value.__aexit__ = AsyncMock(return_value=False)
            with (
                patch("app.features.core.memories.extraction_service.MemoryService", return_value=memory_service),
                patch("app.features.core.memories.extraction_service.EmbeddingService", return_value=embedding_service),
            ):
                await service.extract_and_save("I wake up at 6am", message_id=1)

        memory_service.create.assert_called_once()

    async def test_unknown_category_is_skipped(self):
        candidates = [{"category": "transient", "content": "Spent 70 euros at the gym", "importance": 0.2, "confidence": 1.0}]
        service, llm_provider, _ = _make_service()
        llm_provider.complete.return_value = LlmResponse(text=json.dumps(candidates), tokens_input=10, tokens_output=5)

        memory_service = AsyncMock()
        embedding_service = AsyncMock()

        with patch("app.features.core.memories.extraction_service.async_session") as mock_session_ctx:
            mock_session = AsyncMock()
            mock_session_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session_ctx.return_value.__aexit__ = AsyncMock(return_value=False)
            with (
                patch("app.features.core.memories.extraction_service.MemoryService", return_value=memory_service),
                patch("app.features.core.memories.extraction_service.EmbeddingService", return_value=embedding_service),
            ):
                await service.extract_and_save("I spent 70 euros at the gym today", message_id=10)

        memory_service.create.assert_not_called()
        embedding_service.search.assert_not_called()
        embedding_service.embed.assert_not_called()

    async def test_creates_memory_with_expires_at_when_expires_days_set(self):
        candidates = [{"category": "fact", "content": "Currently in Marseille", "importance": 0.5, "confidence": 0.9, "expires_days": 5}]
        service, llm_provider, _ = _make_service()
        llm_provider.complete.return_value = LlmResponse(text=json.dumps(candidates), tokens_input=10, tokens_output=5)

        memory_service = AsyncMock()
        memory_service.create = AsyncMock(return_value=_make_memory_read(10))
        embedding_service = AsyncMock()
        embedding_service.search = AsyncMock(return_value=[])
        embedding_service.embed = AsyncMock()

        with patch("app.features.core.memories.extraction_service.async_session") as mock_session_ctx:
            mock_session = AsyncMock()
            mock_session_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session_ctx.return_value.__aexit__ = AsyncMock(return_value=False)
            with (
                patch("app.features.core.memories.extraction_service.MemoryService", return_value=memory_service),
                patch("app.features.core.memories.extraction_service.EmbeddingService", return_value=embedding_service),
            ):
                await service.extract_and_save("I am currently in Marseille", message_id=5)

        created = memory_service.create.call_args[0][0]
        assert created.expires_at is not None

    async def test_creates_memory_without_expires_at_when_expires_days_null(self):
        candidates = [{"category": "fact", "content": "User lives in Porto", "importance": 0.8, "confidence": 1.0, "expires_days": None}]
        service, llm_provider, _ = _make_service()
        llm_provider.complete.return_value = LlmResponse(text=json.dumps(candidates), tokens_input=10, tokens_output=5)

        memory_service = AsyncMock()
        memory_service.create = AsyncMock(return_value=_make_memory_read(11))
        embedding_service = AsyncMock()
        embedding_service.search = AsyncMock(return_value=[])
        embedding_service.embed = AsyncMock()

        with patch("app.features.core.memories.extraction_service.async_session") as mock_session_ctx:
            mock_session = AsyncMock()
            mock_session_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session_ctx.return_value.__aexit__ = AsyncMock(return_value=False)
            with (
                patch("app.features.core.memories.extraction_service.MemoryService", return_value=memory_service),
                patch("app.features.core.memories.extraction_service.EmbeddingService", return_value=embedding_service),
            ):
                await service.extract_and_save("I live in Porto", message_id=6)

        created = memory_service.create.call_args[0][0]
        assert created.expires_at is None

    async def test_bumps_importance_and_updates_expires_at_for_duplicate(self):
        candidates = [{"category": "fact", "content": "Currently in Marseille", "importance": 0.5, "confidence": 0.9, "expires_days": 3}]
        service, llm_provider, _ = _make_service()
        llm_provider.complete.return_value = LlmResponse(text=json.dumps(candidates), tokens_input=10, tokens_output=5)

        existing_memory = _make_memory_read(memory_id=7, importance=0.5)
        memory_service = AsyncMock()
        memory_service.get = AsyncMock(return_value=existing_memory)
        memory_service.update = AsyncMock()
        embedding_service = AsyncMock()
        embedding_service.search = AsyncMock(return_value=[_make_embedding_result(source_id=7)])

        with patch("app.features.core.memories.extraction_service.async_session") as mock_session_ctx:
            mock_session = AsyncMock()
            mock_session_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session_ctx.return_value.__aexit__ = AsyncMock(return_value=False)
            with (
                patch("app.features.core.memories.extraction_service.MemoryService", return_value=memory_service),
                patch("app.features.core.memories.extraction_service.EmbeddingService", return_value=embedding_service),
            ):
                await service.extract_and_save("Still in Marseille", message_id=8)

        update_arg = memory_service.update.call_args[0][1]
        assert update_arg.importance == pytest.approx(0.6)
        assert update_arg.expires_at is not None

    async def test_structured_domain_data_produces_no_memories(self):
        # LLM should return [] for structured domain data per the prompt rules,
        # but even if it hallucinates a known category the content would be domain data.
        # This test validates the empty-list fast-path covers that case.
        service, llm_provider, _ = _make_service()
        llm_provider.complete.return_value = LlmResponse(text="[]", tokens_input=10, tokens_output=5)

        memory_service = AsyncMock()

        with patch("app.features.core.memories.extraction_service.async_session") as mock_session_ctx:
            mock_session = AsyncMock()
            mock_session_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session_ctx.return_value.__aexit__ = AsyncMock(return_value=False)
            with patch("app.features.core.memories.extraction_service.MemoryService", return_value=memory_service):
                await service.extract_and_save("/expense 45 -m Pingo Doce", message_id=11)

        memory_service.create.assert_not_called()
