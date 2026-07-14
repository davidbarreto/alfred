import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.storage import StorageProvider
from app.features.organizer.notes.tables import Note  # noqa: F401 — ensures Note is registered with SQLAlchemy mapper
from app.features.organizer.notes.schemas import NoteCreate, NoteUpdate, NoteFilters, NoteRead
from app.features.organizer.notes.repository import NoteRepository
from app.features.core.embeddings.schemas import EmbeddingCreate
from app.features.core.embeddings.service import EmbeddingService

logger = logging.getLogger(__name__)

_SOURCE_TYPE = "note"


def _note_embed_content(title: str, content: str | None) -> str:
    return f"{title}: {content}" if content and content != title else title


class NoteService:

    def __init__(
        self,
        provider: StorageProvider,
        session: AsyncSession,
        embedding_service: EmbeddingService | None = None,
    ) -> None:
        self._provider = provider
        self._session = session
        self._repo = NoteRepository(session)
        self._embedding_service = embedding_service

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
        logger.info("Note created: id=%d title=%r", note_orm.id, note_create.title)
        if self._embedding_service:
            try:
                content = _note_embed_content(note_orm.title, note_orm.content)
                await self._embedding_service.embed(
                    EmbeddingCreate(source_type=_SOURCE_TYPE, source_id=note_orm.id, content=content)
                )
            except Exception as exc:
                logger.warning("Note embed failed: id=%d error=%s", note_orm.id, exc)
        return NoteRead.model_validate(note_orm)

    async def update_note(self, note_id: int, note_update: NoteUpdate) -> NoteRead | None:
        note = await self._repo.get_note(note_id)
        if note is None:
            logger.debug("Note update: id=%d not found", note_id)
            return None
        await self._provider.update(
            note.provider_id,
            note_update.model_dump(exclude_unset=True),
            self._session,
        )
        note_orm = await self._repo.update_note(note_id, note_update)
        logger.info("Note updated: id=%d fields=%s", note_id, list(note_update.model_dump(exclude_unset=True).keys()))
        if self._embedding_service:
            try:
                content = _note_embed_content(note_orm.title, note_orm.content)
                await self._embedding_service.embed(
                    EmbeddingCreate(source_type=_SOURCE_TYPE, source_id=note_id, content=content)
                )
            except Exception as exc:
                logger.warning("Note embed failed on update: id=%d error=%s", note_id, exc)
        return NoteRead.model_validate(note_orm)

    async def delete_note(self, note_id: int) -> None:
        note = await self._repo.get_note(note_id)
        if note:
            await self._provider.delete(note.provider_id, self._session)
            await self._repo.delete_note(note_id)
            logger.info("Note deleted: id=%d", note_id)
            if self._embedding_service:
                try:
                    await self._embedding_service.delete_by_source(_SOURCE_TYPE, note_id)
                except Exception as exc:
                    logger.warning("Note embedding delete failed: id=%d error=%s", note_id, exc)
        else:
            logger.debug("Note delete: id=%d not found", note_id)

    async def archive_note(self, note_id: int) -> NoteRead | None:
        note = await self._repo.get_note(note_id)
        if note is None:
            logger.debug("Note archive: id=%d not found", note_id)
            return None
        note_orm = await self._repo.archive_note(note_id)
        logger.info("Note archived: id=%d", note_id)
        return NoteRead.model_validate(note_orm)

    async def unarchive_note(self, note_id: int) -> NoteRead | None:
        note = await self._repo.get_note(note_id)
        if note is None:
            logger.debug("Note unarchive: id=%d not found", note_id)
            return None
        note_orm = await self._repo.unarchive_note(note_id)
        logger.info("Note unarchived: id=%d", note_id)
        return NoteRead.model_validate(note_orm)
