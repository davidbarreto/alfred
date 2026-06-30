from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.core.memories.schemas import MemoryCreate, MemoryFilters, MemoryUpdate
from app.features.core.memories.tables import Memory


class MemoryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, memory_id: int) -> Memory | None:
        result = await self._session.execute(select(Memory).where(Memory.id == memory_id))
        return result.scalars().first()

    async def list(self, filters: MemoryFilters) -> list[Memory]:
        now = datetime.now(timezone.utc)
        query = select(Memory).where(
            (Memory.expires_at.is_(None)) | (Memory.expires_at > now)
        )
        if filters.category is not None:
            query = query.where(Memory.category == filters.category)
        if filters.active is not None:
            query = query.where(Memory.active == filters.active)
        query = query.order_by(Memory.created_at.desc()).limit(filters.limit).offset(filters.offset)
        result = await self._session.execute(query)
        return list(result.scalars().all())

    async def create(self, data: MemoryCreate) -> Memory:
        memory = Memory(**data.model_dump())
        self._session.add(memory)
        await self._session.commit()
        await self._session.refresh(memory)
        return memory

    async def update(self, memory_id: int, data: MemoryUpdate) -> Memory | None:
        memory = await self.get(memory_id)
        if memory is None:
            return None
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(memory, field, value)
        await self._session.commit()
        await self._session.refresh(memory)
        return memory

    async def delete(self, memory_id: int) -> bool:
        memory = await self.get(memory_id)
        if memory is None:
            return False
        await self._session.delete(memory)
        await self._session.commit()
        return True
