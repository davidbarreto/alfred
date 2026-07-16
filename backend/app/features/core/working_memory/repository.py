from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.core.working_memory.schemas import WorkingMemoryCreate, WorkingMemoryFilters
from app.features.core.working_memory.tables import WorkingMemory


class WorkingMemoryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, item_id: int) -> WorkingMemory | None:
        result = await self._session.execute(
            select(WorkingMemory).where(WorkingMemory.id == item_id)
        )
        return result.scalars().first()

    async def list(self, filters: WorkingMemoryFilters) -> list[WorkingMemory]:
        query = select(WorkingMemory)
        if filters.active_only:
            now = datetime.now(timezone.utc)
            query = query.where(
                (WorkingMemory.expires_at.is_(None)) | (WorkingMemory.expires_at > now)
            )
        if filters.key is not None:
            query = query.where(WorkingMemory.key == filters.key)
        if filters.session_id is not None:
            query = query.where(WorkingMemory.session_id == filters.session_id)
        query = query.order_by(WorkingMemory.created_at.desc()).limit(filters.limit).offset(filters.offset)
        result = await self._session.execute(query)
        return list(result.scalars().all())

    async def create(self, data: WorkingMemoryCreate) -> WorkingMemory:
        item = WorkingMemory(**data.model_dump())
        self._session.add(item)
        await self._session.commit()
        await self._session.refresh(item)
        return item

    async def upsert(self, data: WorkingMemoryCreate) -> WorkingMemory:
        # key is unique and expired rows are not purged, so a plain insert would fail
        # whenever the same key is written again after its marker expired.
        values = data.model_dump()
        stmt = (
            pg_insert(WorkingMemory)
            .values(**values)
            .on_conflict_do_update(
                constraint="uq_core_working_memory_key",
                set_={field: value for field, value in values.items() if field != "key"},
            )
            .returning(WorkingMemory)
        )
        result = await self._session.execute(stmt)
        await self._session.commit()
        return result.scalars().one()

    async def delete(self, item_id: int) -> bool:
        item = await self.get(item_id)
        if item is None:
            return False
        await self._session.delete(item)
        await self._session.commit()
        return True
