import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.core.working_memory.repository import WorkingMemoryRepository
from app.features.core.working_memory.schemas import (
    WorkingMemoryCreate,
    WorkingMemoryFilters,
    WorkingMemoryRead,
)

logger = logging.getLogger(__name__)


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
        logger.info("WorkingMemory created: id=%d key=%r", obj.id, data.key)
        return WorkingMemoryRead.model_validate(obj)

    async def delete(self, item_id: int) -> bool:
        deleted = await self._repo.delete(item_id)
        if deleted:
            logger.info("WorkingMemory deleted: id=%d", item_id)
        else:
            logger.debug("WorkingMemory delete: id=%d not found", item_id)
        return deleted
