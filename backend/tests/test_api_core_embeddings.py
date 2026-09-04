import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.api.routes.core.embeddings import backfill_embeddings, read_embedding_source_types, read_embeddings


def _note(id=1, title="Title", content="Content"):
    note = MagicMock()
    note.id = id
    note.title = title
    note.content = content
    return note


def _task(id=1, title="Task"):
    task = MagicMock()
    task.id = id
    task.title = title
    return task


@pytest.fixture
def mock_service():
    svc = AsyncMock()
    svc.embed = AsyncMock()
    return svc


@pytest.fixture
def mock_session():
    return AsyncMock()


class TestListEmbeddings:
    async def test_forwards_filters_to_service(self, mock_service):
        mock_service.list = AsyncMock(return_value=[])

        await read_embeddings(mock_service, source_type="note", q="dentist", skip=10, limit=20)

        mock_service.list.assert_awaited_once_with(source_type="note", q="dentist", skip=10, limit=20)

    async def test_returns_service_result(self, mock_service):
        expected = [MagicMock()]
        mock_service.list = AsyncMock(return_value=expected)

        result = await read_embeddings(mock_service, source_type=None, q=None, skip=0, limit=50)

        assert result == expected


class TestReadEmbeddingSourceTypes:
    async def test_returns_service_result(self, mock_service):
        mock_service.list_source_types = AsyncMock(return_value=["memory", "note", "task", "transaction"])

        result = await read_embedding_source_types(mock_service)

        assert result == ["memory", "note", "task", "transaction"]
        mock_service.list_source_types.assert_awaited_once()


class TestBackfillEmbeddings:
    async def test_embeds_note_and_title_when_distinct(self, mock_service, mock_session):
        notes = [_note(id=1, title="Go project", content="Build a Redis-compatible cache")]
        with patch("app.api.routes.core.embeddings.NoteRepository") as MockNoteRepo, \
             patch("app.api.routes.core.embeddings.TaskRepository") as MockTaskRepo:
            MockNoteRepo.return_value.get_notes = AsyncMock(side_effect=[notes, []])
            MockTaskRepo.return_value.get_tasks = AsyncMock(return_value=[])

            result = await backfill_embeddings(mock_service, mock_session)

        assert result.notes_embedded == 1
        assert result.note_titles_embedded == 1
        assert result.errors == 0
        source_types = {c.args[0].source_type for c in mock_service.embed.call_args_list}
        assert source_types == {"note", "note_title"}

    async def test_skips_title_embedding_when_content_equals_title(self, mock_service, mock_session):
        notes = [_note(id=2, title="Same", content="Same")]
        with patch("app.api.routes.core.embeddings.NoteRepository") as MockNoteRepo, \
             patch("app.api.routes.core.embeddings.TaskRepository") as MockTaskRepo:
            MockNoteRepo.return_value.get_notes = AsyncMock(side_effect=[notes, []])
            MockTaskRepo.return_value.get_tasks = AsyncMock(return_value=[])

            result = await backfill_embeddings(mock_service, mock_session)

        assert result.notes_embedded == 1
        assert result.note_titles_embedded == 0
        assert mock_service.embed.call_count == 1

    async def test_covers_both_archived_and_active_notes(self, mock_service, mock_session):
        active = [_note(id=1, title="Active", content="Active body")]
        archived = [_note(id=2, title="Archived", content="Archived body")]
        with patch("app.api.routes.core.embeddings.NoteRepository") as MockNoteRepo, \
             patch("app.api.routes.core.embeddings.TaskRepository") as MockTaskRepo:
            MockNoteRepo.return_value.get_notes = AsyncMock(side_effect=[active, archived])
            MockTaskRepo.return_value.get_tasks = AsyncMock(return_value=[])

            result = await backfill_embeddings(mock_service, mock_session)

        assert result.notes_embedded == 2
        assert result.note_titles_embedded == 2

    async def test_embeds_tasks(self, mock_service, mock_session):
        with patch("app.api.routes.core.embeddings.NoteRepository") as MockNoteRepo, \
             patch("app.api.routes.core.embeddings.TaskRepository") as MockTaskRepo:
            MockNoteRepo.return_value.get_notes = AsyncMock(side_effect=[[], []])
            MockTaskRepo.return_value.get_tasks = AsyncMock(return_value=[_task(id=1, title="Fix bug")])

            result = await backfill_embeddings(mock_service, mock_session)

        assert result.tasks_embedded == 1

    async def test_counts_errors_and_continues(self, mock_service, mock_session):
        notes = [_note(id=1, title="A", content="Body A"), _note(id=2, title="B", content="Body B")]
        mock_service.embed = AsyncMock(side_effect=[Exception("boom"), None, None])
        with patch("app.api.routes.core.embeddings.NoteRepository") as MockNoteRepo, \
             patch("app.api.routes.core.embeddings.TaskRepository") as MockTaskRepo:
            MockNoteRepo.return_value.get_notes = AsyncMock(side_effect=[notes, []])
            MockTaskRepo.return_value.get_tasks = AsyncMock(return_value=[])

            result = await backfill_embeddings(mock_service, mock_session)

        assert result.errors == 1
        assert result.notes_embedded == 1
