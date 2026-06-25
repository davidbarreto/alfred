from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)

_TOKEN_URL = "https://oauth2.googleapis.com/token"
_BASE_URL = "https://people.googleapis.com/v1"
_PERSON_FIELDS = "names,emailAddresses,phoneNumbers,birthdays"
_PAGE_SIZE = 1000


class GoogleContactsClient:
    def __init__(self, client_id: str, client_secret: str, refresh_token: str) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._refresh_token = refresh_token
        self._access_token: str | None = None

    def _raise(self, response: httpx.Response) -> None:
        if response.is_error:
            logger.error("Google Contacts API error %s: %s", response.status_code, response.text)
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

    async def _get(self, url: str, params: dict | None = None) -> dict:
        headers = await self._headers()
        async with httpx.AsyncClient() as http:
            resp = await http.get(url, headers=headers, params=params or {})
            if resp.status_code == 401:
                self._access_token = await self._refresh_access_token()
                headers = {"Authorization": f"Bearer {self._access_token}"}
                resp = await http.get(url, headers=headers, params=params or {})
            self._raise(resp)
            return resp.json()

    async def _post(self, url: str, body: dict, params: dict | None = None) -> dict:
        headers = await self._headers()
        async with httpx.AsyncClient() as http:
            resp = await http.post(url, headers=headers, json=body, params=params or {})
            if resp.status_code == 401:
                self._access_token = await self._refresh_access_token()
                headers = {"Authorization": f"Bearer {self._access_token}"}
                resp = await http.post(url, headers=headers, json=body, params=params or {})
            self._raise(resp)
            return resp.json()

    async def _patch(self, url: str, body: dict, params: dict | None = None) -> dict:
        headers = await self._headers()
        async with httpx.AsyncClient() as http:
            resp = await http.patch(url, headers=headers, json=body, params=params or {})
            if resp.status_code == 401:
                self._access_token = await self._refresh_access_token()
                headers = {"Authorization": f"Bearer {self._access_token}"}
                resp = await http.patch(url, headers=headers, json=body, params=params or {})
            self._raise(resp)
            return resp.json()

    async def _delete(self, url: str) -> None:
        headers = await self._headers()
        async with httpx.AsyncClient() as http:
            resp = await http.delete(url, headers=headers)
            if resp.status_code == 401:
                self._access_token = await self._refresh_access_token()
                headers = {"Authorization": f"Bearer {self._access_token}"}
                resp = await http.delete(url, headers=headers)
            self._raise(resp)

    async def list_connections(self) -> list[dict]:
        connections: list[dict] = []
        page_token: str | None = None

        while True:
            params: dict = {
                "personFields": _PERSON_FIELDS,
                "pageSize": _PAGE_SIZE,
                "sortOrder": "LAST_MODIFIED_DESCENDING",
            }
            if page_token:
                params["pageToken"] = page_token

            data = await self._get(f"{_BASE_URL}/people/me/connections", params=params)
            connections.extend(data.get("connections") or [])
            page_token = data.get("nextPageToken")
            if not page_token:
                break

        logger.info("Fetched %d contacts from Google", len(connections))
        return connections

    async def get_contact(self, resource_name: str) -> dict:
        return await self._get(
            f"{_BASE_URL}/{resource_name}",
            params={"personFields": _PERSON_FIELDS},
        )

    async def create_contact(self, person: dict) -> dict:
        return await self._post(
            f"{_BASE_URL}/people:createContact",
            body=person,
            params={"personFields": _PERSON_FIELDS},
        )

    async def update_contact(self, resource_name: str, person: dict, update_fields: str) -> dict:
        return await self._patch(
            f"{_BASE_URL}/{resource_name}:updateContact",
            body=person,
            params={"updatePersonFields": update_fields, "personFields": _PERSON_FIELDS},
        )

    async def delete_contact(self, resource_name: str) -> None:
        await self._delete(f"{_BASE_URL}/{resource_name}:deleteContact")
