from __future__ import annotations

import logging
from datetime import date, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.briefing.schemas import HolidayItem
from app.integrations.provider_calls.repository import create_sync_log

from .client import GooglePublicHolidayClient

logger = logging.getLogger(__name__)

_CALENDARS: dict[str, str] = {
    "PT": "pt.portuguese#holiday@group.v.calendar.google.com",
    "BR": "en.brazilian#holiday@group.v.calendar.google.com",
}


class GooglePublicHolidayProvider:
    def __init__(self, client: GooglePublicHolidayClient) -> None:
        self._client = client

    async def get_holidays(
        self, from_date: date, to_date: date, session: AsyncSession | None = None
    ) -> list[HolidayItem]:
        time_min = f"{from_date.isoformat()}T00:00:00Z"
        time_max = f"{(to_date + timedelta(days=1)).isoformat()}T00:00:00Z"
        results: list[HolidayItem] = []

        for country, calendar_id in _CALENDARS.items():
            country_results: list[HolidayItem] = []
            error: str | None = None
            try:
                items = await self._client.fetch_events(calendar_id, time_min, time_max)
                for item in items:
                    name = item.get("summary", "")
                    event_date_str = item.get("start", {}).get("date", "")
                    if not event_date_str:
                        continue
                    event_date = date.fromisoformat(event_date_str)
                    days_until = (event_date - from_date).days
                    country_results.append(
                        HolidayItem(name=name, local_name=name, country=country, days_until=days_until, date=event_date)
                    )
            except Exception as exc:
                error = str(exc)
                logger.warning("Failed to fetch holidays for %s", country, exc_info=True)
            else:
                results.extend(country_results)
            await self._write_log(session, country, from_date, to_date, country_results, error)

        results.sort(key=lambda h: (h.days_until, h.country))
        return results

    async def _write_log(
        self,
        session: AsyncSession | None,
        country: str,
        from_date: date,
        to_date: date,
        holidays: list[HolidayItem],
        error: str | None,
    ) -> None:
        if session is None:
            return
        try:
            await create_sync_log(
                session,
                provider="google_public_holidays",
                operation="get_holidays",
                entity_type="holiday",
                provider_entity_id=country,
                status="error" if error else "ok",
                request_payload={"country": country, "from": from_date.isoformat(), "to": to_date.isoformat()},
                response_payload={"holidays": [h.model_dump(mode="json") for h in holidays]} if not error else None,
                error=error,
            )
        except Exception:
            logger.warning("Failed to write integration sync log", exc_info=True)
