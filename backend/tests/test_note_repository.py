import pytest
from unittest.mock import AsyncMock, MagicMock
from sqlalchemy.ext.asyncio import AsyncSession
from app.features.organizer.notes.repository import NoteRepository
from app.features.organizer.notes.schemas import NoteCreate, NoteUpdate, NoteFilters
import app.features.organizer.tasks.tables  # noqa: F401 — registers Task with SQLAlchemy mapper
import app.features.organizer.calendar_events.tables  # noqa: F401 — registers CalendarEvent with SQLAlchemy mapper


def _make_session() -> AsyncMock:
    return AsyncMock(spec=AsyncSession)


def _make_note_orm(id=1, **kwargs):
    note = MagicMock()
    note.id = id
    note.title = kwargs.get("title", "Test Note")
    note.content = kwargs.get("content", "Some content")
    note.tags = kwargs.get("tags", [])
    note.provider_id = kwargs.get("provider_id", "provider-1")
    return note


def _scalar_first(value):
    result = MagicMock()
    result.scalars.return_value.first.return_value = value
    return result


def _scalar_all(values):
    result = MagicMock()
    result.scalars.return_value.all.return_value = values
    return result


def _scalar_one(value):
    result = MagicMock()
    result.scalars.return_value.one.return_value = value
    return result


class TestGetNote:
    async def test_found(self):
        session = _make_session()
        note = _make_note_orm()
        session.execute.return_value = _scalar_first(note)

        repo = NoteRepository(session)
        result = await repo.get_note(1)

        assert result == note
        session.execute.assert_called_once()

    async def test_not_found(self):
        session = _make_session()
        session.execute.return_value = _scalar_first(None)

        repo = NoteRepository(session)
        result = await repo.get_note(999)

        assert result is None


class TestGetNotes:
    async def test_returns_list(self):
        session = _make_session()
        notes = [_make_note_orm(id=i) for i in range(3)]
        session.execute.return_value = _scalar_all(notes)

        repo = NoteRepository(session)
        result = await repo.get_notes(NoteFilters())

        assert len(result) == 3
        session.execute.assert_called_once()

    async def test_empty_list(self):
        session = _make_session()
        session.execute.return_value = _scalar_all([])

        repo = NoteRepository(session)
        result = await repo.get_notes(NoteFilters())
        assert result == []

    async def test_tags_filter_applied(self):
        session = _make_session()
        session.execute.return_value = _scalar_all([])

        repo = NoteRepository(session)
        await repo.get_notes(NoteFilters(tags=["work"]))
        session.execute.assert_called_once()


class TestCreateNote:
    async def test_create_with_no_tags(self):
        session = _make_session()
        note = _make_note_orm()
        session.execute.return_value = _scalar_one(note)

        repo = NoteRepository(session)
        result = await repo.create_note(NoteCreate(title="New Note", tags=[]), "provider-1")

        session.add.assert_called()
        session.commit.assert_called_once()
        assert result == note

    async def test_create_with_existing_tag(self):
        session = _make_session()
        from app.features.organizer.tags.tables import Tag
        existing_tag = Tag(name="work", provider_id="provider-1")
        note = _make_note_orm()

        session.execute.side_effect = [_scalar_first(existing_tag), _scalar_one(note)]

        repo = NoteRepository(session)
        result = await repo.create_note(NoteCreate(title="New Note", tags=["work"]), "provider-1")

        session.commit.assert_called_once()
        assert result == note

    async def test_create_with_new_tag(self):
        session = _make_session()
        note = _make_note_orm()

        session.execute.side_effect = [_scalar_first(None), _scalar_one(note)]

        repo = NoteRepository(session)
        result = await repo.create_note(NoteCreate(title="New Note", tags=["newtag"]), "provider-1")

        session.commit.assert_called_once()
        assert session.add.call_count >= 2
        assert result == note


class TestUpdateNote:
    async def test_update_found(self):
        session = _make_session()
        note = _make_note_orm()

        session.execute.side_effect = [_scalar_first(note), _scalar_one(note)]

        repo = NoteRepository(session)
        result = await repo.update_note(1, NoteUpdate(title="Updated"))

        session.commit.assert_called_once()
        assert result == note

    async def test_update_not_found(self):
        session = _make_session()
        session.execute.return_value = _scalar_first(None)

        repo = NoteRepository(session)
        result = await repo.update_note(999, NoteUpdate(title="X"))

        assert result is None
        session.commit.assert_not_called()

    async def test_update_resolves_tags(self):
        session = _make_session()
        from app.features.organizer.tags.tables import Tag
        note = _make_note_orm(provider_id="provider-1")
        existing_tag = Tag(name="work", provider_id="provider-1")

        # get_note (first), _resolve_tags (first), reload after commit (one)
        session.execute.side_effect = [
            _scalar_first(note),
            _scalar_first(existing_tag),
            _scalar_one(note),
        ]

        repo = NoteRepository(session)
        result = await repo.update_note(1, NoteUpdate(tags=["work"]))

        session.commit.assert_called_once()
        assert result == note


class TestDeleteNote:
    async def test_delete_found(self):
        session = _make_session()
        note = _make_note_orm()

        session.execute.side_effect = [_scalar_first(note), MagicMock()]

        repo = NoteRepository(session)
        await repo.delete_note(1)

        session.commit.assert_called_once()

    async def test_delete_not_found(self):
        session = _make_session()
        session.execute.return_value = _scalar_first(None)

        repo = NoteRepository(session)
        result = await repo.delete_note(999)

        assert result is None
        session.commit.assert_not_called()


class TestResolveTags:
    async def test_returns_existing_tag(self):
        session = _make_session()
        from app.features.organizer.tags.tables import Tag
        existing_tag = Tag(name="work", provider_id="provider-1")
        session.execute.return_value = _scalar_first(existing_tag)

        repo = NoteRepository(session)
        tags = await repo._resolve_tags(["work"], "provider-1")

        assert len(tags) == 1
        assert tags[0] is existing_tag
        session.add.assert_not_called()

    async def test_creates_new_tag(self):
        session = _make_session()
        session.execute.return_value = _scalar_first(None)

        repo = NoteRepository(session)
        tags = await repo._resolve_tags(["newtag"], "provider-1")

        assert len(tags) == 1
        session.add.assert_called_once()

    async def test_empty_tags_list(self):
        session = _make_session()
        repo = NoteRepository(session)
        tags = await repo._resolve_tags([], "provider-1")
        assert tags == []
        session.execute.assert_not_called()

    async def test_multiple_tags(self):
        session = _make_session()
        from app.features.organizer.tags.tables import Tag
        existing = Tag(name="existing", provider_id="provider-1")

        session.execute.side_effect = [_scalar_first(existing), _scalar_first(None)]

        repo = NoteRepository(session)
        tags = await repo._resolve_tags(["existing", "new"], "provider-1")

        assert len(tags) == 2
        assert session.add.call_count == 1
