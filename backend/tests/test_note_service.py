import pytest
from unittest.mock import AsyncMock, MagicMock
from app.features.organizer.notes.service import NoteService
from app.features.organizer.notes.schemas import NoteCreate, NoteUpdate, NoteFilters, NoteRead


def _make_note_read(**kwargs):
    defaults = dict(id=1, title="Test Note", description="Some content", tags=[])
    defaults.update(kwargs)
    return NoteRead(**defaults)


def _make_note_orm(**kwargs):
    note = MagicMock()
    note.id = kwargs.get("id", 1)
    note.title = kwargs.get("title", "Test Note")
    note.description = kwargs.get("description", "Some content")
    note.tags = kwargs.get("tags", [])
    note.provider_id = kwargs.get("provider_id", "provider-1")
    return note


@pytest.fixture
def mock_provider():
    return AsyncMock()


@pytest.fixture
def mock_session():
    return AsyncMock()


@pytest.fixture
def service(mock_provider, mock_session):
    svc = NoteService(provider=mock_provider, session=mock_session)
    svc._repo = AsyncMock()
    return svc


class TestGetNote:
    async def test_returns_note_read_when_found(self, service):
        note_orm = _make_note_orm()
        service._repo.get_note.return_value = note_orm

        result = await service.get_note(1)

        service._repo.get_note.assert_called_once_with(1)
        assert result is not None
        assert result.id == 1

    async def test_returns_none_when_not_found(self, service):
        service._repo.get_note.return_value = None

        result = await service.get_note(999)
        assert result is None

    async def test_returns_note_read_type(self, service):
        service._repo.get_note.return_value = _make_note_orm()
        result = await service.get_note(1)
        assert isinstance(result, NoteRead)


class TestGetNotes:
    async def test_returns_list_of_note_reads(self, service):
        service._repo.get_notes.return_value = [_make_note_orm(id=i) for i in range(3)]

        result = await service.get_notes(NoteFilters())

        assert len(result) == 3
        assert all(isinstance(n, NoteRead) for n in result)

    async def test_empty_list(self, service):
        service._repo.get_notes.return_value = []
        result = await service.get_notes(NoteFilters())
        assert result == []

    async def test_passes_filters_to_repo(self, service):
        service._repo.get_notes.return_value = []
        filters = NoteFilters(tags=["work"])
        await service.get_notes(filters)
        service._repo.get_notes.assert_called_once_with(filters)


class TestCreateNote:
    async def test_calls_provider_create(self, service, mock_provider):
        note_create = NoteCreate(title="New Note")
        mock_provider.create.return_value = {"id": "provider-abc"}
        service._repo.create_note.return_value = _make_note_orm(title="New Note")

        await service.create_note(note_create)

        mock_provider.create.assert_called_once()

    async def test_calls_repo_create_with_provider_id(self, service, mock_provider):
        note_create = NoteCreate(title="New Note")
        mock_provider.create.return_value = {"id": "provider-xyz"}
        service._repo.create_note.return_value = _make_note_orm()

        await service.create_note(note_create)

        service._repo.create_note.assert_called_once_with(note_create, "provider-xyz")

    async def test_returns_note_read(self, service, mock_provider):
        mock_provider.create.return_value = {"id": "provider-1"}
        service._repo.create_note.return_value = _make_note_orm()

        result = await service.create_note(NoteCreate(title="Test"))
        assert isinstance(result, NoteRead)


class TestUpdateNote:
    async def test_returns_updated_note(self, service):
        service._repo.get_note.return_value = _make_note_orm()
        service._repo.update_note.return_value = _make_note_orm(title="Updated")
        note_update = NoteUpdate(title="Updated")

        result = await service.update_note(1, note_update)

        service._repo.update_note.assert_called_once_with(1, note_update)
        assert isinstance(result, NoteRead)

    async def test_returns_none_when_not_found(self, service):
        service._repo.get_note.return_value = None
        result = await service.update_note(999, NoteUpdate(title="X"))
        assert result is None

    async def test_calls_provider_update(self, service, mock_provider):
        note_orm = _make_note_orm(provider_id="provider-abc")
        service._repo.get_note.return_value = note_orm
        service._repo.update_note.return_value = note_orm
        note_update = NoteUpdate(title="Updated")

        await service.update_note(1, note_update)

        mock_provider.update.assert_called_once_with("provider-abc", {"title": "Updated"}, service._session)


class TestDeleteNote:
    async def test_calls_delete_when_found(self, service):
        service._repo.get_note.return_value = _make_note_orm()

        await service.delete_note(1)

        service._repo.delete_note.assert_called_once_with(1)

    async def test_does_not_call_delete_when_not_found(self, service):
        service._repo.get_note.return_value = None

        await service.delete_note(999)

        service._repo.delete_note.assert_not_called()

    async def test_calls_provider_delete(self, service, mock_provider):
        service._repo.get_note.return_value = _make_note_orm(provider_id="provider-abc")

        await service.delete_note(1)

        mock_provider.delete.assert_called_once_with("provider-abc", service._session)
