from __future__ import annotations

import logging
from datetime import date
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.provider_calls.repository import create_sync_log

from .client import GoogleContactsClient

logger = logging.getLogger(__name__)

_PERSON_FIELDS = "names,emailAddresses,phoneNumbers,birthdays"
_PLACEHOLDER_YEAR = 2000


class GoogleContactsProvider:
    def __init__(self, client: GoogleContactsClient, entity_type: str = "contact") -> None:
        self._client = client
        self._entity_type = entity_type

    def _to_person(self, record: dict[str, Any]) -> tuple[dict[str, Any], str]:
        person: dict[str, Any] = {}
        update_fields: list[str] = []

        if "name" in record and record["name"] is not None:
            person["names"] = [{"unstructuredName": record["name"]}]
            update_fields.append("names")
        if "email" in record:
            person["emailAddresses"] = [{"value": record["email"]}] if record["email"] else []
            update_fields.append("emailAddresses")
        if "phone" in record:
            person["phoneNumbers"] = [{"value": record["phone"]}] if record["phone"] else []
            update_fields.append("phoneNumbers")
        if "birthday" in record:
            bd = record["birthday"]
            if bd:
                person["birthdays"] = [{"date": {"year": bd.year, "month": bd.month, "day": bd.day}}]
            else:
                person["birthdays"] = []
            update_fields.append("birthdays")

        return person, ",".join(update_fields)

    def _from_person(self, person: dict[str, Any]) -> dict[str, Any]:
        names = person.get("names") or []
        emails = person.get("emailAddresses") or []
        phones = person.get("phoneNumbers") or []
        birthdays = person.get("birthdays") or []

        name = names[0].get("displayName", "") if names else ""
        email = emails[0].get("value") if emails else None
        phone = phones[0].get("value") if phones else None

        birthday: date | None = None
        if birthdays:
            bd = birthdays[0].get("date")
            if bd:
                month = bd.get("month")
                day = bd.get("day")
                year = bd.get("year") or _PLACEHOLDER_YEAR
                if month and day:
                    try:
                        birthday = date(year, month, day)
                    except ValueError:
                        pass

        return {
            "id": person["resourceName"],
            "name": name,
            "email": email,
            "phone": phone,
            "birthday": birthday,
        }

    async def create(self, record: dict[str, Any], session: AsyncSession | None = None) -> dict[str, Any]:
        person, _ = self._to_person(record)

        error: str | None = None
        result: dict[str, Any] | None = None
        try:
            result = await self._client.create_contact(person)
        except Exception as exc:
            error = str(exc)
            await self._write_log(session, "create", None, person, None, error)
            raise

        await self._write_log(session, "create", result["resourceName"], person, result)
        return self._from_person(result)

    async def get(self, record_id: str, session: AsyncSession | None = None) -> dict[str, Any]:
        result = await self._client.get_contact(record_id)
        return self._from_person(result)

    async def update(
        self,
        record_id: str,
        record: dict[str, Any],
        session: AsyncSession | None = None,
    ) -> dict[str, Any]:
        person, update_fields = self._to_person(record)
        if not update_fields:
            return {"id": record_id}

        error: str | None = None
        result: dict[str, Any] | None = None
        try:
            result = await self._client.update_contact(record_id, person, update_fields)
        except Exception as exc:
            error = str(exc)
            await self._write_log(session, "update", record_id, person, None, error)
            raise

        await self._write_log(session, "update", record_id, person, result)
        return self._from_person(result)

    async def delete(self, record_id: str, session: AsyncSession | None = None) -> None:
        error: str | None = None
        try:
            await self._client.delete_contact(record_id)
        except Exception as exc:
            error = str(exc)
            await self._write_log(session, "delete", record_id, None, None, error)
            raise

        await self._write_log(session, "delete", record_id, None, None)

    async def list(
        self,
        filters: dict[str, Any] | None = None,
        session: AsyncSession | None = None,
    ) -> list[dict[str, Any]]:
        people = await self._client.list_connections()
        return [self._from_person(p) for p in people]

    async def _write_log(
        self,
        session: AsyncSession | None,
        operation: str,
        provider_entity_id: str | None,
        request_payload: dict[str, Any] | None,
        response_payload: dict[str, Any] | None,
        error: str | None = None,
    ) -> None:
        if session is None:
            return
        try:
            await create_sync_log(
                session,
                provider="google_contacts",
                operation=operation,
                entity_type=self._entity_type,
                provider_entity_id=provider_entity_id,
                status="error" if error else "ok",
                request_payload=request_payload,
                response_payload=response_payload,
                error=error,
            )
        except Exception:
            logger.warning("Failed to write integration sync log", exc_info=True)
