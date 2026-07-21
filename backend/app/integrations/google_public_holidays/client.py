from __future__ import annotations

from typing import Any
from urllib.parse import quote

import httpx

_BASE_URL = "https://www.googleapis.com/calendar/v3/calendars"


class GooglePublicHolidayClient:
    """Thin async wrapper around Google's public-holiday calendars (Calendar API,
    read-only, keyed by API key rather than OAuth). Knows nothing about domain
    concepts (countries, HolidayItem) -- only HTTP and the calendar events wire format.
    """

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    async def fetch_events(self, calendar_id: str, time_min: str, time_max: str) -> list[dict[str, Any]]:
        async with httpx.AsyncClient(timeout=10.0) as http:
            response = await http.get(
                f"{_BASE_URL}/{quote(calendar_id, safe='')}/events",
                params={
                    "key": self._api_key,
                    "timeMin": time_min,
                    "timeMax": time_max,
                    "singleEvents": "true",
                    "orderBy": "startTime",
                },
            )
            response.raise_for_status()
            return response.json().get("items", [])
