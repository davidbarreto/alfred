from __future__ import annotations

import logging

from app.integrations.google_oauth.client import GoogleOAuthClient

logger = logging.getLogger(__name__)

_BASE_URL = "https://people.googleapis.com/v1"
_PERSON_FIELDS = "names,emailAddresses,phoneNumbers,birthdays,memberships"
_PAGE_SIZE = 1000


class GoogleContactsClient(GoogleOAuthClient):
    def __init__(self, client_id: str, client_secret: str, refresh_token: str) -> None:
        super().__init__("google_contacts", client_id, client_secret, refresh_token)

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

            data = await self._request("GET", f"{_BASE_URL}/people/me/connections", params=params)
            connections.extend(data.get("connections") or [])
            page_token = data.get("nextPageToken")
            if not page_token:
                break

        logger.info("Fetched %d contacts from Google", len(connections))
        return connections

    async def list_contact_groups(self) -> list[dict]:
        groups: list[dict] = []
        page_token: str | None = None

        while True:
            params: dict = {"pageSize": _PAGE_SIZE}
            if page_token:
                params["pageToken"] = page_token

            data = await self._request("GET", f"{_BASE_URL}/contactGroups", params=params)
            groups.extend(data.get("contactGroups") or [])
            page_token = data.get("nextPageToken")
            if not page_token:
                break

        logger.info("Fetched %d contact groups from Google", len(groups))
        return groups

    async def get_contact(self, resource_name: str) -> dict:
        return await self._request(
            "GET",
            f"{_BASE_URL}/{resource_name}",
            params={"personFields": _PERSON_FIELDS},
        )

    async def create_contact(self, person: dict) -> dict:
        return await self._request(
            "POST",
            f"{_BASE_URL}/people:createContact",
            json=person,
            params={"personFields": _PERSON_FIELDS},
        )

    async def update_contact(self, resource_name: str, person: dict, update_fields: str) -> dict:
        return await self._request(
            "PATCH",
            f"{_BASE_URL}/{resource_name}:updateContact",
            json=person,
            params={"updatePersonFields": update_fields, "personFields": _PERSON_FIELDS},
        )

    async def delete_contact(self, resource_name: str) -> None:
        await self._request("DELETE", f"{_BASE_URL}/{resource_name}:deleteContact")
