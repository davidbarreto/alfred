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

    async def test_includes_note_title_in_search_scope(self, mock_embedding_service):
        mock_embedding_service.search.return_value = []

        await handle_recall("search", {"query": "deployment notes"}, mock_embedding_service)

        call_arg = mock_embedding_service.search.call_args[0][0]
        assert "note_title" in call_arg.source_types

    async def test_collapses_note_and_note_title_hits_into_one_result(self, mock_embedding_service):
        mock_embedding_service.search.return_value = [
            _make_result(source_type="note_title", source_id=7, content="Go project", similarity=0.72),
            _make_result(source_type="note", source_id=7, content="Go project: build a Redis-compatible cache", similarity=0.48),
        ]

        result = await handle_recall("search", {"query": "Go Project"}, mock_embedding_service)

        assert len(result) == 1
        assert result[0]["type"] == "note"
        assert result[0]["source_id"] == 7
        # Best similarity across both embeddings wins the ranking...
        assert result[0]["similarity"] == 0.72
        # ...but the full note content is shown, not just the title.
        assert result[0]["content"] == "Go project: build a Redis-compatible cache"

    async def test_does_not_collapse_notes_with_different_ids(self, mock_embedding_service):
        mock_embedding_service.search.return_value = [
            _make_result(source_type="note", source_id=1, content="Note one", similarity=0.9),
            _make_result(source_type="note", source_id=2, content="Note two", similarity=0.8),
        ]

        result = await handle_recall("search", {"query": "note"}, mock_embedding_service)

        assert len(result) == 2

    async def test_backfills_full_content_when_only_title_matched(self, mock_embedding_service):
        # Only the title embedding scored above threshold; the full "note" embedding
        # never showed up in the results at all.
        mock_embedding_service.search.return_value = [
            _make_result(source_type="note_title", source_id=7, content="Go project", similarity=0.72),
        ]
        note_service = AsyncMock()
        note = AsyncMock(title="Go project", content="Build a Redis-compatible cache in Go")
        note_service.get_note = AsyncMock(return_value=note)

        result = await handle_recall(
            "search", {"query": "Go project"}, mock_embedding_service, note_service=note_service
        )

        assert len(result) == 1
        assert result[0]["content"] == "Go project: Build a Redis-compatible cache in Go"
        assert "_has_full_content" not in result[0]
        note_service.get_note.assert_awaited_once_with(7)

    async def test_leaves_title_only_content_when_note_service_not_provided(self, mock_embedding_service):
        mock_embedding_service.search.return_value = [
            _make_result(source_type="note_title", source_id=7, content="Go project", similarity=0.72),
        ]

        result = await handle_recall("search", {"query": "Go project"}, mock_embedding_service)

        assert result[0]["content"] == "Go project"
        assert "_has_full_content" not in result[0]
