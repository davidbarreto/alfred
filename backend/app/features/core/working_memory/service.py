from sqlalchemy.ext.asyncio import AsyncSession

from app.features.core.working_memory.repository import WorkingMemoryRepository
from app.features.core.working_memory.schemas import (
    WorkingMemoryCreate,
    WorkingMemoryFilters,
    WorkingMemoryRead,
)


class WorkingMemoryService:
    def __init__(self, session: AsyncSession) -> None:
        self._repo = WorkingMemoryRepository(session)

    async def get(self, item_id: int) -> WorkingMemoryRead | None:
        obj = await self._repo.get(item_id)
        return WorkingMemoryRead.model_validate(obj) if obj else None

    async def list(self, filters: WorkingMemoryFilters) -> list[WorkingMemoryRead]:
        items = await self._repo.list(filters)
        return [WorkingMemoryRead.model_validate(i) for i in items]

    async def create(self, data: WorkingMemoryCreate) -> WorkingMemoryRead:
        obj = await self._repo.create(data)
        return WorkingMemoryRead.model_validate(obj)

    async def delete(self, item_id: int) -> bool:
        return await self._repo.delete(item_id)
