from __future__ import annotations

import logging
from datetime import date, timedelta

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.organizer.contacts.repository import ContactRepository
from app.features.organizer.contacts.schemas import (
    ContactCreate,
    ContactFilters,
    ContactRead,
    ContactUpdate,
)
from app.integrations.google_contacts.client import GoogleContactsClient
from app.shared.storage import StorageProvider

logger = logging.getLogger(__name__)

_BIRTHDAY_LOOKAHEAD_DAYS = 14
_PLACEHOLDER_YEAR = 2000
_NO_WRITE_ACCESS_DETAIL = (
    "Google Contacts write access not authorized. "
    "Re-authorize via GET /integration/google-contacts/oauth/url (full contacts scope required)."
)


class ContactService:
    def __init__(
        self,
        session: AsyncSession,
        client: GoogleContactsClient | None = None,
        provider: StorageProvider | None = None,
    ) -> None:
        self._client = client
        self._session = session
        self._provider = provider

    async def sync(self) -> int:
        if self._client is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Google Contacts not authorized.",
            )
        raw = await self._client.list_connections()
        rows = [_to_row(c) for c in raw if _has_useful_data(c)]
        repo = ContactRepository(self._session)
        count = await repo.upsert(rows)
        logger.info("Synced %d contacts from Google", count)
        return count

    async def get_contact(self, contact_id: int) -> ContactRead | None:
        repo = ContactRepository(self._session)
        contact = await repo.get_contact(contact_id)
        if contact is None:
            return None
        return ContactRead.model_validate(contact)

    async def get_contacts(self, filters: ContactFilters) -> list[ContactRead]:
        repo = ContactRepository(self._session)
        contacts = await repo.get_contacts(filters)
        return [ContactRead.model_validate(c) for c in contacts]

    async def create_contact(self, contact_create: ContactCreate) -> ContactRead:
        if self._provider is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=_NO_WRITE_ACCESS_DETAIL,
            )
        record = await self._provider.create(contact_create.model_dump(), self._session)
        repo = ContactRepository(self._session)
        contact = await repo.create_contact(contact_create, record["id"])
        logger.info("Contact created: id=%d name=%r", contact.id, contact_create.name)
        return ContactRead.model_validate(contact)

    async def update_contact(self, contact_id: int, contact_update: ContactUpdate) -> ContactRead | None:
        repo = ContactRepository(self._session)
        contact = await repo.get_contact(contact_id)
        if contact is None:
            return None
        if self._provider is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=_NO_WRITE_ACCESS_DETAIL,
            )
        await self._provider.update(
            contact.provider_id,
            contact_update.model_dump(exclude_unset=True),
            self._session,
        )
        updated = await repo.update_contact(contact_id, contact_update)
        logger.info("Contact updated: id=%d", contact_id)
        return ContactRead.model_validate(updated)

    async def delete_contact(self, contact_id: int) -> None:
        repo = ContactRepository(self._session)
        contact = await repo.get_contact(contact_id)
        if contact is None:
            return
        if self._provider is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=_NO_WRITE_ACCESS_DETAIL,
            )
        await self._provider.delete(contact.provider_id, self._session)
        await repo.delete_contact(contact_id)
        logger.info("Contact deleted: id=%d", contact_id)

    async def get_upcoming_birthdays(self, today: date) -> list[dict]:
        repo = ContactRepository(self._session)
        contacts = await repo.get_all_with_birthday()
        window_end = today + timedelta(days=_BIRTHDAY_LOOKAHEAD_DAYS)
        result = []
        for contact in contacts:
            next_bd = _next_birthday(contact.birthday, today)  # type: ignore[arg-type]
            if today <= next_bd <= window_end:
                result.append({
                    "name": contact.name,
                    "days_until": (next_bd - today).days,
                    "date": next_bd,
                })
        result.sort(key=lambda x: x["days_until"])
        return result


def _has_useful_data(raw: dict) -> bool:
    names = raw.get("names") or []
    return bool(names)


def _to_row(raw: dict) -> dict:
    names = raw.get("names") or []
    emails = raw.get("emailAddresses") or []
    phones = raw.get("phoneNumbers") or []
    birthdays = raw.get("birthdays") or []

    name = names[0].get("displayName", "") if names else ""
    email = emails[0].get("value") if emails else None
    phone = phones[0].get("value") if phones else None
    birthday = _parse_birthday(birthdays[0].get("date") if birthdays else None)

    return {
        "provider_id": raw["resourceName"],
        "name": name,
        "email": email,
        "phone": phone,
        "birthday": birthday,
    }


def _parse_birthday(bd: dict | None) -> date | None:
    if not bd:
        return None
    month = bd.get("month")
    day = bd.get("day")
    if not month or not day:
        return None
    year = bd.get("year") or _PLACEHOLDER_YEAR
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _next_birthday(birthday: date, today: date) -> date:
    try:
        candidate = birthday.replace(year=today.year)
    except ValueError:
        candidate = date(today.year, 3, 1)
    if candidate < today:
        try:
            candidate = birthday.replace(year=today.year + 1)
        except ValueError:
            candidate = date(today.year + 1, 3, 1)
    return candidate
