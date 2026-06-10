from __future__ import annotations
from typing import Any
import logging
import httpx

logger = logging.getLogger(__name__)

class NotionClient:
    """
    Thin async wrapper around the Notion REST API.
    Knows nothing about domain concepts — only HTTP and Notion's wire format.
    """

    def _raise(self, response: httpx.Response) -> None:
        if response.is_error:
            logger.error("Notion API error %s: %s", response.status_code, response.text)
            response.raise_for_status()

    def __init__(self, api_key: str, base_url: str, api_version: str = "2022-06-28") -> None:
        self._base_url = base_url
        self._headers = {
            "Authorization": f"Bearer {api_key}",
            "Notion-Version": api_version,
            "Content-Type": "application/json",
        }

    # ------------------------------------------------------------------
    # Pages (records inside a database)
    # ------------------------------------------------------------------

    async def create_page(self, database_id: str, properties: dict[str, Any]) -> dict[str, Any]:
        async with httpx.AsyncClient() as http:
            response = await http.post(
                f"{self._base_url}/pages",
                headers=self._headers,
                json={"parent": {"database_id": database_id}, "properties": properties},
            )
            self._raise(response)
            return response.json()

    async def get_page(self, page_id: str) -> dict[str, Any]:
        async with httpx.AsyncClient() as http:
            response = await http.get(
                f"{self._base_url}/pages/{page_id}",
                headers=self._headers,
            )
            self._raise(response)
            return response.json()

    async def update_page(self, page_id: str, properties: dict[str, Any]) -> dict[str, Any]:
        async with httpx.AsyncClient() as http:
            response = await http.patch(
                f"{self._base_url}/pages/{page_id}",
                headers=self._headers,
                json={"properties": properties},
            )
            self._raise(response)
            return response.json()

    async def archive_page(self, page_id: str) -> dict[str, Any]:
        """Notion doesn't hard-delete pages; archiving is the equivalent of delete."""
        async with httpx.AsyncClient() as http:
            response = await http.patch(
                f"{self._base_url}/pages/{page_id}",
                headers=self._headers,
                json={"archived": True},
            )
            self._raise(response)
            return response.json()

    # ------------------------------------------------------------------
    # Database queries
    # ------------------------------------------------------------------

    async def query_database(
        self,
        database_id: str,
        filter_payload: dict[str, Any] | None = None,
        sorts: list[dict[str, Any]] | None = None,
        page_size: int = 100,
    ) -> list[dict[str, Any]]:
        """Returns all pages matching the filter, handling pagination automatically."""
        results: list[dict[str, Any]] = []
        body: dict[str, Any] = {"page_size": page_size}
        if filter_payload:
            body["filter"] = filter_payload
        if sorts:
            body["sorts"] = sorts

        async with httpx.AsyncClient() as http:
            while True:
                response = await http.post(
                    f"{self._base_url}/databases/{database_id}/query",
                    headers=self._headers,
                    json=body,
                )
                self._raise(response)
                data = response.json()
                results.extend(data.get("results", []))
                if not data.get("has_more"):
                    break
                body["start_cursor"] = data["next_cursor"]

        return results