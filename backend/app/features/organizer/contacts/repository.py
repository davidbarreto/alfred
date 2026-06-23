from __future__ import annotations

from datetime import date
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.organizer.contacts.tables import Contact


class ContactRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_all_with_birthday(self) -> Sequence[Contact]:
        result = await self._session.execute(
            select(Contact).where(Contact.birthday.is_not(None))
        )
        return result.scalars().all()

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
                },
            )
        )
        await self._session.execute(stmt)
        await self._session.commit()
        return len(contacts)
