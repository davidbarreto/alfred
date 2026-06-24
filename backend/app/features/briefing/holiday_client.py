from __future__ import annotations

import logging
from datetime import date, timedelta

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

    async def get_holidays(self, for_date: date) -> list[HolidayItem]:
        time_min = f"{for_date.isoformat()}T00:00:00Z"
        time_max = f"{(for_date + timedelta(days=1)).isoformat()}T00:00:00Z"
        results: list[HolidayItem] = []

        async with httpx.AsyncClient(timeout=10.0) as http:
            for country, calendar_id in _CALENDARS.items():
                try:
                    resp = await http.get(
                        f"{_BASE_URL}/{calendar_id}/events",
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
                        results.append(HolidayItem(name=name, local_name=name, country=country))
                except Exception:
                    logger.warning("Failed to fetch holidays for %s", country, exc_info=True)

        return results
