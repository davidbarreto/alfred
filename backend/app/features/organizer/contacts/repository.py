from __future__ import annotations

from datetime import date
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.organizer.contacts.schemas import ContactCreate, ContactFilters, ContactUpdate
from app.features.organizer.contacts.tables import Contact


class ContactRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_contact(self, contact_id: int) -> Contact | None:
        result = await self._session.execute(
            select(Contact).where(Contact.id == contact_id)
        )
        return result.scalars().first()

    async def get_contacts(self, filters: ContactFilters) -> list[Contact]:
        stmt = select(Contact)
        if filters.name is not None:
            stmt = stmt.where(Contact.name.ilike(f"%{filters.name}%"))
        if filters.email is not None:
            stmt = stmt.where(Contact.email.ilike(f"%{filters.email}%"))
        if filters.letter is not None:
            stmt = stmt.where(Contact.name.ilike(f"{filters.letter}%"))
        if filters.has_birthday is True:
            stmt = stmt.where(Contact.birthday.is_not(None))
        elif filters.has_birthday is False:
            stmt = stmt.where(Contact.birthday.is_(None))
        if filters.relationship is not None:
            stmt = stmt.where(Contact.relationship == filters.relationship)
        stmt = stmt.order_by(Contact.name).offset(filters.offset).limit(filters.limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_all_with_birthday(self) -> Sequence[Contact]:
        result = await self._session.execute(
            select(Contact).where(Contact.birthday.is_not(None))
        )
        return result.scalars().all()

    async def create_contact(self, contact_create: ContactCreate, provider_id: str) -> Contact:
        contact = Contact(
            provider_id=provider_id,
            name=contact_create.name,
            email=contact_create.email,
            phone=contact_create.phone,
            birthday=contact_create.birthday,
        )
        self._session.add(contact)
        await self._session.commit()
        await self._session.refresh(contact)
        return contact

    async def update_contact(self, contact_id: int, contact_update: ContactUpdate) -> Contact | None:
        contact = await self.get_contact(contact_id)
        if contact is None:
            return None
        for field, value in contact_update.model_dump(exclude_unset=True).items():
            setattr(contact, field, value)
        await self._session.commit()
        await self._session.refresh(contact)
        return contact

    async def delete_contact(self, contact_id: int) -> None:
        contact = await self.get_contact(contact_id)
        if contact is not None:
            await self._session.delete(contact)
            await self._session.commit()

    async def upsert(self, contacts: list[dict]) -> int:
        if not contacts:
            return 0
        stmt = (
            insert(Contact)
            .values(contacts)
            .on_conflict_do_update(
                index_elements=["provider_id"],
                set_={
                    "name": insert(Contact).excluded.name,
                    "email": insert(Contact).excluded.email,
                    "phone": insert(Contact).excluded.phone,
                    "birthday": insert(Contact).excluded.birthday,
                    "relationship": insert(Contact).excluded.relationship,
                },
            )
        )
        await self._session.execute(stmt)
        await self._session.commit()
        return len(contacts)
