from __future__ import annotations

from app.integrations.google_oauth.client import GoogleOAuthClient

_BASE_URL = "https://www.googleapis.com/calendar/v3"


class GoogleCalendarClient(GoogleOAuthClient):
    def __init__(self, client_id: str, client_secret: str, refresh_token: str) -> None:
        super().__init__("google_calendar", client_id, client_secret, refresh_token)

    async def create_event(self, calendar_id: str, event: dict) -> dict:
        return await self._request(
            "POST", f"{_BASE_URL}/calendars/{calendar_id}/events", json=event
        )

    async def get_event(self, calendar_id: str, event_id: str) -> dict:
        return await self._request(
            "GET", f"{_BASE_URL}/calendars/{calendar_id}/events/{event_id}"
        )

    async def update_event(self, calendar_id: str, event_id: str, event: dict) -> dict:
        return await self._request(
            "PATCH", f"{_BASE_URL}/calendars/{calendar_id}/events/{event_id}", json=event
        )

    async def delete_event(self, calendar_id: str, event_id: str) -> None:
        await self._request(
            "DELETE", f"{_BASE_URL}/calendars/{calendar_id}/events/{event_id}"
        )

    async def list_events(self, calendar_id: str, params: dict | None = None) -> list[dict]:
        result = await self._request(
            "GET", f"{_BASE_URL}/calendars/{calendar_id}/events", params=params or {}
        )
        return result.get("items", [])
