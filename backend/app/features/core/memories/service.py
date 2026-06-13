from sqlalchemy.ext.asyncio import AsyncSession

from app.features.core.memories.repository import MemoryRepository
from app.features.core.memories.schemas import (
    MemoryCreate,
    MemoryFilters,
    MemoryRead,
    MemoryUpdate,
)


class MemoryService:
    def __init__(self, session: AsyncSession) -> None:
        self._repo = MemoryRepository(session)

    async def get(self, memory_id: int) -> MemoryRead | None:
        obj = await self._repo.get(memory_id)
        return MemoryRead.model_validate(obj) if obj else None

    async def list(self, filters: MemoryFilters) -> list[MemoryRead]:
        items = await self._repo.list(filters)
        return [MemoryRead.model_validate(i) for i in items]

    async def create(self, data: MemoryCreate) -> MemoryRead:
        obj = await self._repo.create(data)
        return MemoryRead.model_validate(obj)

    async def update(self, memory_id: int, data: MemoryUpdate) -> MemoryRead | None:
        obj = await self._repo.update(memory_id, data)
        return MemoryRead.model_validate(obj) if obj else None

    async def delete(self, memory_id: int) -> bool:
        return await self._repo.delete(memory_id)
