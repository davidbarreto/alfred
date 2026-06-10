from __future__ import annotations
from datetime import datetime
from typing import Any

from .client import NotionClient

class NotionProvider:
    """
    Implements the StorageProvider protocol backed by Notion.

    Handles the translation between the generic record dict and
    Notion's property format in both directions.
    """

    def __init__(self, client: NotionClient, database_id: str) -> None:
        self._client = client
        self._db = database_id

    # ------------------------------------------------------------------
    # StorageProvider implementation
    # ------------------------------------------------------------------

    async def create(self, record: dict[str, Any]) -> dict[str, Any]:
        properties = self._to_notion_properties(record)
        page = await self._client.create_page(self._db, properties)
        return self._from_notion_page(page)

    async def get(self, record_id: str) -> dict[str, Any]:
        page = await self._client.get_page(record_id)
        return self._from_notion_page(page)

    async def update(self, record_id: str, record: dict[str, Any]) -> dict[str, Any]:
        properties = self._to_notion_properties(record)
        page = await self._client.update_page(record_id, properties)
        return self._from_notion_page(page)

    async def delete(self, record_id: str) -> None:
        await self._client.archive_page(record_id)

    async def list(
        self,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        notion_filter = self._to_notion_filter(filters) if filters else None
        pages = await self._client.query_database(self._db, filter_payload=notion_filter)
        return [self._from_notion_page(p) for p in pages]

    # ------------------------------------------------------------------
    # Notion ↔ generic record translation
    # ------------------------------------------------------------------

    _SELECT_FIELDS = {"priority", "urgency"}
    _STATUS_FIELDS = {"status"}

    def _to_notion_properties(self, record: dict[str, Any]) -> dict[str, Any]:
        """
        Converts a flat dict into Notion's property format.

        Supported value types:
        str   → title (for "title" key) or rich_text
        bool  → checkbox
        list  → multi_select  (list of strings)
        str   → select        (if key is in _SELECT_FIELDS or ends with "_select")
        date  → date          (datetime objects or keys ending with "_at"/"_date")
        """
        properties: dict[str, Any] = {}

        for key, value in record.items():
            if value is None:
                continue
            if key == "title":
                properties["title"] = {"title": [{"text": {"content": str(value)}}]}
            elif isinstance(value, bool):
                properties[key] = {"checkbox": value}
            elif isinstance(value, list):
                properties[key] = {"multi_select": [{"name": v} for v in value]}
            elif isinstance(value, datetime):
                properties[key] = {"date": {"start": value.isoformat()}}
            elif key.endswith(("_at", "_date")):
                properties[key] = {"date": {"start": value}}
            elif key in self._STATUS_FIELDS:
                properties[key] = {"status": {"name": value}}
            elif key in self._SELECT_FIELDS or key.endswith("_select"):
                clean_key = key[: -len("_select")] if key.endswith("_select") else key
                properties[clean_key] = {"select": {"name": value}}
            elif isinstance(value, str):
                properties[key] = {"rich_text": [{"text": {"content": value}}]}

        return properties

    def _from_notion_page(self, page: dict[str, Any]) -> dict[str, Any]:
        """Flattens a Notion page into a simple dict the domain layer can use."""
        record: dict[str, Any] = {"id": page["id"]}

        for prop_name, prop_data in page.get("properties", {}).items():
            record[prop_name] = self._extract_property_value(prop_data)

        return record

    def _extract_property_value(self, prop: dict[str, Any]) -> Any:
        t = prop.get("type")
        if t == "title":
            items = prop.get("title", [])
            return items[0]["plain_text"] if items else ""
        if t == "rich_text":
            items = prop.get("rich_text", [])
            return items[0]["plain_text"] if items else ""
        if t == "checkbox":
            return prop.get("checkbox", False)
        if t == "select":
            sel = prop.get("select")
            return sel["name"] if sel else None
        if t == "multi_select":
            return [o["name"] for o in prop.get("multi_select", [])]
        if t == "date":
            d = prop.get("date")
            return d["start"] if d else None
        if t == "status":
            s = prop.get("status")
            return s["name"] if s else None
        # fallback — return raw
        return prop

    def _to_notion_filter(self, filters: dict[str, Any]) -> dict[str, Any]:
        """
        Converts a simple {field: value} dict into a Notion AND filter.
        Extend this for OR / compound logic as needed.
        """
        conditions = []
        for key, value in filters.items():
            if isinstance(value, bool):
                conditions.append({"property": key, "checkbox": {"equals": value}})
            elif isinstance(value, str):
                if key == "title":
                    conditions.append({"property": key, "title": {"equals": value}})
                else:
                    conditions.append({"property": key, "rich_text": {"equals": value}})
            elif isinstance(value, list):
                for v in value:
                    conditions.append({"property": key, "multi_select": {"contains": v}})

        if not conditions:
            return {}
        if len(conditions) == 1:
            return conditions[0]
        return {"and": conditions}