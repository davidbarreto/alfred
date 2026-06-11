import logging
import httpx

logger = logging.getLogger(__name__)

_TOKEN_URL = "https://oauth2.googleapis.com/token"
_BASE_URL = "https://www.googleapis.com/calendar/v3"


class GoogleCalendarClient:
    def __init__(self, client_id: str, client_secret: str, refresh_token: str) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._refresh_token = refresh_token
        self._access_token: str | None = None

    def _raise(self, response: httpx.Response) -> None:
        if response.is_error:
            logger.error("Google Calendar API error %s: %s", response.status_code, response.text)
            response.raise_for_status()

    async def _refresh_access_token(self) -> str:
        async with httpx.AsyncClient() as http:
            resp = await http.post(
                _TOKEN_URL,
                data={
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                    "refresh_token": self._refresh_token,
                    "grant_type": "refresh_token",
                },
            )
            self._raise(resp)
            return resp.json()["access_token"]

    async def _headers(self) -> dict[str, str]:
        if self._access_token is None:
            self._access_token = await self._refresh_access_token()
        return {"Authorization": f"Bearer {self._access_token}"}

    async def _request(self, method: str, url: str, **kwargs) -> dict:
        headers = await self._headers()
        async with httpx.AsyncClient() as http:
            resp = await http.request(method, url, headers=headers, **kwargs)
            if resp.status_code == 401:
                self._access_token = await self._refresh_access_token()
                headers = {"Authorization": f"Bearer {self._access_token}"}
                resp = await http.request(method, url, headers=headers, **kwargs)
            self._raise(resp)
            return {} if resp.status_code == 204 else resp.json()

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
