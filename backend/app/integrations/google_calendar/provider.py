from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.provider_calls.repository import create_sync_log

from .client import GoogleCalendarClient

logger = logging.getLogger(__name__)


class GoogleCalendarProvider:
    def __init__(
        self,
        client: GoogleCalendarClient,
        calendar_id: str = "primary",
        entity_type: str = "unknown",
    ) -> None:
        self._client = client
        self._calendar_id = calendar_id
        self._entity_type = entity_type

    def _to_google_event(self, record: dict[str, Any]) -> dict[str, Any]:
        event: dict[str, Any] = {}

        if "title" in record:
            event["summary"] = record["title"]
        if "description" in record:
            event["description"] = record["description"]
        if "location" in record:
            event["location"] = record["location"]

        all_day = record.get("all_day", False)

        if "start_datetime" in record:
            dt = record["start_datetime"]
            if isinstance(dt, str):
                dt = datetime.fromisoformat(dt)
            event["start"] = {"date": dt.date().isoformat()} if all_day else {"dateTime": dt.isoformat(), "timeZone": "UTC"}

        if "end_datetime" in record:
            dt = record["end_datetime"]
            if isinstance(dt, str):
                dt = datetime.fromisoformat(dt)
            event["end"] = {"date": dt.date().isoformat()} if all_day else {"dateTime": dt.isoformat(), "timeZone": "UTC"}

        if record.get("recurrence_rule"):
            event["recurrence"] = [f"RRULE:{record['recurrence_rule']}"]

        if record.get("host"):
            event["organizer"] = {"email": record["host"]}

        if "invitees" in record and record["invitees"]:
            event["attendees"] = [{"email": e} for e in record["invitees"]]

        return event

    def _from_google_event(self, google_event: dict[str, Any]) -> dict[str, Any]:
        start = google_event.get("start", {})
        end = google_event.get("end", {})

        all_day = "date" in start

        if all_day:
            start_dt: datetime = datetime.fromisoformat(start["date"])
            end_dt: datetime = datetime.fromisoformat(end["date"])
        else:
            start_dt = datetime.fromisoformat(start["dateTime"].replace("Z", "+00:00"))
            end_dt = datetime.fromisoformat(end["dateTime"].replace("Z", "+00:00"))

        recurrence_rule: str | None = None
        for rule in google_event.get("recurrence", []):
            if rule.startswith("RRULE:"):
                recurrence_rule = rule.removeprefix("RRULE:")
                break

        return {
            "id": google_event["id"],
            "title": google_event.get("summary", ""),
            "description": google_event.get("description"),
            "location": google_event.get("location"),
            "start_datetime": start_dt,
            "end_datetime": end_dt,
            "all_day": all_day,
            "recurrence_rule": recurrence_rule,
            "host": google_event.get("organizer", {}).get("email"),
            "invitees": [a["email"] for a in google_event.get("attendees", []) if "email" in a],
        }

    async def create(
        self, record: dict[str, Any], session: AsyncSession | None = None
    ) -> dict[str, Any]:
        google_event = self._to_google_event(record)

        error: str | None = None
        result: dict[str, Any] | None = None
        try:
            result = await self._client.create_event(self._calendar_id, google_event)
        except Exception as exc:
            error = str(exc)
            await self._write_log(session, "create", None, google_event, None, error)
            raise

        await self._write_log(session, "create", result["id"], google_event, result)
        return self._from_google_event(result)

    async def get(
        self, record_id: str, session: AsyncSession | None = None
    ) -> dict[str, Any]:
        result = await self._client.get_event(self._calendar_id, record_id)
        return self._from_google_event(result)

    async def update(
        self,
        record_id: str,
        record: dict[str, Any],
        session: AsyncSession | None = None,
    ) -> dict[str, Any]:
        google_event = self._to_google_event(record)

        error: str | None = None
        result: dict[str, Any] | None = None
        try:
            result = await self._client.update_event(self._calendar_id, record_id, google_event)
        except Exception as exc:
            error = str(exc)
            await self._write_log(session, "update", record_id, google_event, None, error)
            raise

        await self._write_log(session, "update", record_id, google_event, result)
        return self._from_google_event(result)

    async def delete(
        self, record_id: str, session: AsyncSession | None = None
    ) -> None:
        error: str | None = None
        try:
            await self._client.delete_event(self._calendar_id, record_id)
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
        params: dict[str, Any] = {}
        if filters:
            if "start_from" in filters and filters["start_from"] is not None:
                dt = filters["start_from"]
                params["timeMin"] = dt.isoformat() if isinstance(dt, datetime) else dt
            if "start_to" in filters and filters["start_to"] is not None:
                dt = filters["start_to"]
                params["timeMax"] = dt.isoformat() if isinstance(dt, datetime) else dt
        results = await self._client.list_events(self._calendar_id, params)
        return [self._from_google_event(e) for e in results]

    # ------------------------------------------------------------------
    # Internal logging helper
    # ------------------------------------------------------------------

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
                provider="google_calendar",
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
