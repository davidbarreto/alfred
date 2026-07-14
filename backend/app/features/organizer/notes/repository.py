from datetime import datetime, timezone
from sqlalchemy import select, update
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.organizer.tags.tables import Tag
from app.features.organizer.notes.tables import Note
from app.features.organizer.notes.schemas import NoteCreate, NoteUpdate, NoteFilters

_NOTE_EXCLUDE = {"tags"}


class NoteRepository:

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_note(self, note_id: int) -> Note | None:
        result = await self._session.execute(
            select(Note)
            .options(selectinload(Note.tags))
            .where(Note.id == note_id, Note.deleted_at.is_(None))
        )
        return result.scalars().first()

    async def get_notes(self, note_filter: NoteFilters) -> list[Note]:
        query = select(Note).options(selectinload(Note.tags)).where(Note.deleted_at.is_(None))
        query = query.where(
            Note.archived_at.isnot(None) if note_filter.archived else Note.archived_at.is_(None)
        )
        if note_filter.tags:
            query = query.where(Note.tags.any(Tag.name.in_(note_filter.tags)))
        order_by = Note.updated_at.desc() if note_filter.sort == "updated" else Note.created_at.desc()
        query = query.order_by(order_by).limit(note_filter.limit).offset(note_filter.offset)
        result = await self._session.execute(query)
        return list(result.scalars().all())

    async def _resolve_tags(self, tag_names: list[str], provider_id: str) -> list[Tag]:
        tags = []
        for name in tag_names:
            result = await self._session.execute(
                select(Tag).where(Tag.provider_id == provider_id, Tag.name == name)
            )
            tag = result.scalars().first()
            if tag is None:
                tag = Tag(provider_id=provider_id, name=name)
                self._session.add(tag)
            tags.append(tag)
        return tags

    async def create_note(self, note_create: NoteCreate, provider_id: str) -> Note:
        note = Note(**note_create.model_dump(exclude=_NOTE_EXCLUDE), provider_id=provider_id)
        note.tags = await self._resolve_tags(note_create.tags, provider_id)
        self._session.add(note)
        await self._session.commit()
        result = await self._session.execute(
            select(Note).options(selectinload(Note.tags)).where(Note.id == note.id)
        )
        return result.scalars().one()

    async def update_note(self, note_id: int, note_update: NoteUpdate) -> Note | None:
        note = await self.get_note(note_id)
        if note is None:
            return None

        update_data = note_update.model_dump(exclude_unset=True)
        if "tags" in update_data:
            note.tags = await self._resolve_tags(update_data.pop("tags"), note.provider_id)

        for field, value in update_data.items():
            setattr(note, field, value)

        await self._session.commit()
        result = await self._session.execute(
            select(Note).options(selectinload(Note.tags)).where(Note.id == note_id)
        )
        return result.scalars().one()

    async def delete_note(self, note_id: int) -> None:
        await self._session.execute(
            update(Note)
            .where(Note.id == note_id)
            .values(deleted_at=datetime.now(timezone.utc))
        )
        await self._session.commit()

    async def archive_note(self, note_id: int) -> Note | None:
        await self._session.execute(
            update(Note)
            .where(Note.id == note_id)
            .values(archived_at=datetime.now(timezone.utc))
        )
        await self._session.commit()
        result = await self._session.execute(
            select(Note).options(selectinload(Note.tags)).where(Note.id == note_id)
        )
        return result.scalars().first()

    async def unarchive_note(self, note_id: int) -> Note | None:
        await self._session.execute(
            update(Note)
            .where(Note.id == note_id)
            .values(archived_at=None)
        )
        await self._session.commit()
        result = await self._session.execute(
            select(Note).options(selectinload(Note.tags)).where(Note.id == note_id)
        )
        return result.scalars().first()
