import pytest
from fastapi import HTTPException
from unittest.mock import AsyncMock
from datetime import datetime, timezone

from app.assistant.commands.handlers.recall import handle_recall
from app.features.core.embeddings.schemas import EmbeddingSearchResult


def _make_result(source_type="note", source_id=1, content="some content", similarity=0.85):
    return EmbeddingSearchResult(
        id=1,
        source_type=source_type,
        source_id=source_id,
        content=content,
        model="test-model",
        dimensions=384,
        embedded_at=datetime.now(timezone.utc),
        similarity=similarity,
    )


@pytest.fixture
def mock_embedding_service():
    svc = AsyncMock()
    svc.search = AsyncMock()
    return svc


class TestHandleRecall:
    async def test_returns_matching_items(self, mock_embedding_service):
        mock_embedding_service.search.return_value = [
            _make_result(source_type="note", source_id=10, content="API migration plan", similarity=0.9),
            _make_result(source_type="memory", source_id=2, content="API uses FastAPI", similarity=0.75),
        ]

        result = await handle_recall("search", {"query": "API migration"}, mock_embedding_service)

        assert len(result) == 2
        assert result[0]["type"] == "note"
        assert result[0]["source_id"] == 10
        assert result[0]["content"] == "API migration plan"
        assert result[0]["similarity"] == 0.9

    async def test_returns_empty_list_when_no_matches(self, mock_embedding_service):
        mock_embedding_service.search.return_value = []

        result = await handle_recall("search", {"query": "something obscure"}, mock_embedding_service)

        assert result == []

    async def test_passes_query_to_embedding_service(self, mock_embedding_service):
        mock_embedding_service.search.return_value = []

        await handle_recall("search", {"query": "deployment notes"}, mock_embedding_service)

        call_arg = mock_embedding_service.search.call_args[0][0]
        assert call_arg.query == "deployment notes"
        assert "note" in call_arg.source_types
        assert "memory" in call_arg.source_types
        assert "task" in call_arg.source_types

    async def test_raises_on_empty_query(self, mock_embedding_service):
        with pytest.raises(HTTPException) as exc_info:
            await handle_recall("search", {"query": ""}, mock_embedding_service)
        assert exc_info.value.status_code == 400

    async def test_raises_on_missing_query(self, mock_embedding_service):
        with pytest.raises(HTTPException) as exc_info:
            await handle_recall("search", {}, mock_embedding_service)
        assert exc_info.value.status_code == 400

    async def test_raises_on_unknown_command(self, mock_embedding_service):
        with pytest.raises(HTTPException) as exc_info:
            await handle_recall("list", {"query": "test"}, mock_embedding_service)
        assert exc_info.value.status_code == 400

    async def test_result_includes_all_fields(self, mock_embedding_service):
        mock_embedding_service.search.return_value = [
            _make_result(source_type="task", source_id=5, content="Fix bug", similarity=0.8)
        ]

        result = await handle_recall("search", {"query": "bug"}, mock_embedding_service)

        assert result[0].keys() == {"type", "source_id", "content", "similarity"}
