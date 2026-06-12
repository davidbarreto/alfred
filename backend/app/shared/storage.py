from __future__ import annotations
from typing import Any, Protocol, runtime_checkable

from sqlalchemy.ext.asyncio import AsyncSession


@runtime_checkable
class StorageProvider(Protocol):
    """
    Generic async CRUD interface for a key/value-ish storage backend.

    `database_id` is an opaque string whose meaning is provider-specific:
    - Notion  → database UUID
    - SQLite  → table name
    … and so on.

    `record`   is a plain dict of field name → value.
    `record_id` is an opaque string (Notion page ID, DB primary key, …).

    The domain layer (TaskService, NoteService) speaks only this interface,
    so swapping providers requires no changes outside this module.
    """

    async def create(
        self,
        record: dict[str, Any],
        session: AsyncSession | None = None,
    ) -> dict[str, Any]: ...

    async def get(
        self,
        record_id: str,
        session: AsyncSession | None = None,
    ) -> dict[str, Any]: ...

    async def update(
        self,
        record_id: str,
        record: dict[str, Any],
        session: AsyncSession | None = None,
    ) -> dict[str, Any]: ...

    async def delete(
        self,
        record_id: str,
        session: AsyncSession | None = None,
    ) -> None: ...

    async def list(
        self,
        filters: dict[str, Any] | None = None,
        session: AsyncSession | None = None,
    ) -> list[dict[str, Any]]: ...