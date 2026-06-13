import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from app.features.core.embeddings.schemas import (
    EmbeddingCreate,
    EmbeddingRead,
    EmbeddingSearchRequest,
    EmbeddingSearchResult,
)
from app.features.core.embeddings.service import EmbeddingService


def _make_embedding_orm(**kwargs):
    obj = MagicMock()
    obj.id = kwargs.get("id", 1)
    obj.source_type = kwargs.get("source_type", "memory")
    obj.source_id = kwargs.get("source_id", 10)
    obj.content = kwargs.get("content", "Some memory content")
    obj.model = kwargs.get("model", "text-embedding-3-small")
    obj.dimensions = kwargs.get("dimensions", 1536)
    obj.embedded_at = kwargs.get("embedded_at", datetime(2026, 6, 13, 12, 0, 0, tzinfo=timezone.utc))
    return obj


def _make_provider(vector: list[float] | None = None):
    provider = MagicMock()
    provider.model = "text-embedding-3-small"
    provider.dimensions = 1536
    provider.embed = AsyncMock(return_value=vector or [0.1] * 1536)
    return provider


class TestEmbedMethod:
    @pytest.mark.asyncio
    async def test_creates_embedding_and_returns_schema(self):
        orm_obj = _make_embedding_orm()
        session = AsyncMock()
        provider = _make_provider()

        with patch(
            "app.features.core.embeddings.service.EmbeddingRepository"
        ) as MockRepo:
            repo_instance = MockRepo.return_value
            repo_instance.upsert = AsyncMock(return_value=orm_obj)

            service = EmbeddingService(session, provider)
            result = await service.embed(
                EmbeddingCreate(source_type="memory", source_id=10, content="Some memory content")
            )

        assert isinstance(result, EmbeddingRead)
        assert result.source_type == "memory"
        assert result.source_id == 10
        provider.embed.assert_awaited_once_with("Some memory content")
        repo_instance.upsert.assert_awaited_once_with(
            source_type="memory",
            source_id=10,
            content="Some memory content",
            vector=[0.1] * 1536,
            model="text-embedding-3-small",
            dimensions=1536,
        )

    @pytest.mark.asyncio
    async def test_provider_vector_passed_to_repo(self):
        vector = [0.5] * 1536
        orm_obj = _make_embedding_orm()
        session = AsyncMock()
        provider = _make_provider(vector=vector)

        with patch(
            "app.features.core.embeddings.service.EmbeddingRepository"
        ) as MockRepo:
            repo_instance = MockRepo.return_value
            repo_instance.upsert = AsyncMock(return_value=orm_obj)

            service = EmbeddingService(session, provider)
            await service.embed(
                EmbeddingCreate(source_type="note", source_id=5, content="A note")
            )

        _, kwargs = repo_instance.upsert.call_args
        assert kwargs["vector"] == vector


class TestSearchMethod:
    @pytest.mark.asyncio
    async def test_returns_search_results_with_similarity(self):
        orm_obj = _make_embedding_orm()
        session = AsyncMock()
        provider = _make_provider()

        with patch(
            "app.features.core.embeddings.service.EmbeddingRepository"
        ) as MockRepo:
            repo_instance = MockRepo.return_value
            repo_instance.search = AsyncMock(return_value=[(orm_obj, 0.92)])

            service = EmbeddingService(session, provider)
            results = await service.search(
                EmbeddingSearchRequest(query="test query", limit=5, threshold=0.7)
            )

        assert len(results) == 1
        assert isinstance(results[0], EmbeddingSearchResult)
        assert results[0].similarity == 0.92
        assert results[0].source_type == "memory"

    @pytest.mark.asyncio
    async def test_passes_source_types_filter(self):
        session = AsyncMock()
        provider = _make_provider()

        with patch(
            "app.features.core.embeddings.service.EmbeddingRepository"
        ) as MockRepo:
            repo_instance = MockRepo.return_value
            repo_instance.search = AsyncMock(return_value=[])

            service = EmbeddingService(session, provider)
            await service.search(
                EmbeddingSearchRequest(
                    query="anything", source_types=["memory", "note"], limit=10, threshold=0.5
                )
            )

        _, kwargs = repo_instance.search.call_args
        assert kwargs["source_types"] == ["memory", "note"]
        assert kwargs["limit"] == 10
        assert kwargs["threshold"] == 0.5

    @pytest.mark.asyncio
    async def test_similarity_rounded_to_four_decimals(self):
        orm_obj = _make_embedding_orm()
        session = AsyncMock()
        provider = _make_provider()

        with patch(
            "app.features.core.embeddings.service.EmbeddingRepository"
        ) as MockRepo:
            repo_instance = MockRepo.return_value
            repo_instance.search = AsyncMock(return_value=[(orm_obj, 0.912345678)])

            service = EmbeddingService(session, provider)
            results = await service.search(EmbeddingSearchRequest(query="q"))

        assert results[0].similarity == 0.9123

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_matches(self):
        session = AsyncMock()
        provider = _make_provider()

        with patch(
            "app.features.core.embeddings.service.EmbeddingRepository"
        ) as MockRepo:
            repo_instance = MockRepo.return_value
            repo_instance.search = AsyncMock(return_value=[])

            service = EmbeddingService(session, provider)
            results = await service.search(EmbeddingSearchRequest(query="nothing"))

        assert results == []


class TestDeleteMethod:
    @pytest.mark.asyncio
    async def test_returns_true_when_found(self):
        session = AsyncMock()
        provider = _make_provider()

        with patch(
            "app.features.core.embeddings.service.EmbeddingRepository"
        ) as MockRepo:
            repo_instance = MockRepo.return_value
            repo_instance.delete = AsyncMock(return_value=True)

            service = EmbeddingService(session, provider)
            result = await service.delete(1)

        assert result is True

    @pytest.mark.asyncio
    async def test_returns_false_when_not_found(self):
        session = AsyncMock()
        provider = _make_provider()

        with patch(
            "app.features.core.embeddings.service.EmbeddingRepository"
        ) as MockRepo:
            repo_instance = MockRepo.return_value
            repo_instance.delete = AsyncMock(return_value=False)

            service = EmbeddingService(session, provider)
            result = await service.delete(999)

        assert result is False
