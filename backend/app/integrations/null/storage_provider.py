from typing import Any
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession


class NullStorageProvider:
    """No-op StorageProvider backed by an in-memory dict.

    Used when DISABLE_INTEGRATIONS is set (CI smoke tests) so TaskService/
    NoteService can run full create/read/update/delete/list cycles without a
    real Notion workspace. State only lives for the process lifetime — fine
    for a throwaway CI container.
    """

    def __init__(self) -> None:
        self._records: dict[str, dict[str, Any]] = {}

    async def create(
        self,
        record: dict[str, Any],
        session: AsyncSession | None = None,
    ) -> dict[str, Any]:
        record_id = str(uuid4())
        stored = {**record, "id": record_id}
        self._records[record_id] = stored
        return stored

    async def get(
        self,
        record_id: str,
        session: AsyncSession | None = None,
    ) -> dict[str, Any]:
        return self._records.get(record_id, {"id": record_id})

    async def update(
        self,
        record_id: str,
        record: dict[str, Any],
        session: AsyncSession | None = None,
    ) -> dict[str, Any]:
        stored = self._records.setdefault(record_id, {"id": record_id})
        stored.update(record)
        return stored

    async def delete(
        self,
        record_id: str,
        session: AsyncSession | None = None,
    ) -> None:
        self._records.pop(record_id, None)

    async def list(
        self,
        filters: dict[str, Any] | None = None,
        session: AsyncSession | None = None,
    ) -> list[dict[str, Any]]:
        return list(self._records.values())
