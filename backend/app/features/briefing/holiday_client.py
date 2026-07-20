from __future__ import annotations

import logging
from datetime import date, timedelta
from urllib.parse import quote

import httpx

from app.features.briefing.schemas import HolidayItem

logger = logging.getLogger(__name__)

_BASE_URL = "https://www.googleapis.com/calendar/v3/calendars"
_CALENDARS: dict[str, str] = {
    "PT": "pt.portuguese#holiday@group.v.calendar.google.com",
    "BR": "en.brazilian#holiday@group.v.calendar.google.com",
}


class GooglePublicHolidayClient:
    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    async def get_holidays(self, from_date: date, to_date: date) -> list[HolidayItem]:
        time_min = f"{from_date.isoformat()}T00:00:00Z"
        time_max = f"{(to_date + timedelta(days=1)).isoformat()}T00:00:00Z"
        results: list[HolidayItem] = []

        async with httpx.AsyncClient(timeout=10.0) as http:
            for country, calendar_id in _CALENDARS.items():
                try:
                    resp = await http.get(
                        f"{_BASE_URL}/{quote(calendar_id, safe='')}/events",
                        params={
                            "key": self._api_key,
                            "timeMin": time_min,
                            "timeMax": time_max,
                            "singleEvents": "true",
                            "orderBy": "startTime",
                        },
                    )
                    resp.raise_for_status()
                    for item in resp.json().get("items", []):
                        name = item.get("summary", "")
                        event_date_str = item.get("start", {}).get("date", "")
                        if not event_date_str:
                            continue
                        event_date = date.fromisoformat(event_date_str)
                        days_until = (event_date - from_date).days
                        results.append(HolidayItem(name=name, local_name=name, country=country, days_until=days_until, date=event_date))
                except Exception:
                    logger.warning("Failed to fetch holidays for %s", country, exc_info=True)

        results.sort(key=lambda h: (h.days_until, h.country))
        return results
