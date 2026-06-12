from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.storage import StorageProvider
from app.features.organizer.notes.tables import Note  # noqa: F401 — ensures Note is registered with SQLAlchemy mapper
from app.features.organizer.notes.schemas import NoteCreate, NoteUpdate, NoteFilters, NoteRead
from app.features.organizer.notes.repository import NoteRepository


class NoteService:

    def __init__(self, provider: StorageProvider, session: AsyncSession) -> None:
        self._provider = provider
        self._session = session
        self._repo = NoteRepository(session)

    async def get_note(self, note_id: int) -> NoteRead | None:
        note_orm = await self._repo.get_note(note_id)
        if note_orm is None:
            return None
        return NoteRead.model_validate(note_orm)

    async def get_notes(self, filters: NoteFilters) -> list[NoteRead]:
        notes_orm = await self._repo.get_notes(filters)
        return [NoteRead.model_validate(note_orm) for note_orm in notes_orm]

    async def create_note(self, note_create: NoteCreate) -> NoteRead:
        note_record = await self._provider.create(note_create.model_dump(), self._session)
        note_orm = await self._repo.create_note(note_create, note_record["id"])
        return NoteRead.model_validate(note_orm)

    async def update_note(self, note_id: int, note_update: NoteUpdate) -> NoteRead | None:
        note = await self._repo.get_note(note_id)
        if note is None:
            return None
        await self._provider.update(
            note.provider_id,
            note_update.model_dump(exclude_unset=True),
            self._session,
        )
        note_orm = await self._repo.update_note(note_id, note_update)
        return NoteRead.model_validate(note_orm)

    async def delete_note(self, note_id: int):
        note = await self._repo.get_note(note_id)
        if note:
            await self._provider.delete(note.provider_id, self._session)
            await self._repo.delete_note(note_id)
