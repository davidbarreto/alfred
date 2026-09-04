from __future__ import annotations

from sqlalchemy import case, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.features.organizer.interviews.companies.tables import Company
from app.features.organizer.interviews.processes.schemas import (
    InterviewProcessCreate,
    InterviewProcessFilters,
    InterviewProcessUpdate,
)
from app.features.organizer.interviews.processes.tables import InterviewProcess
from app.features.organizer.interviews.stages.tables import InterviewStage

_PRIORITY_ORDER = case(
    {"high": 0, "medium": 1, "low": 2},
    value=InterviewProcess.priority,
    else_=3,
)


class InterviewProcessRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_process(self, process_id: int) -> InterviewProcess | None:
        result = await self._session.execute(
            select(InterviewProcess)
            .options(selectinload(InterviewProcess.stages))
            .where(InterviewProcess.id == process_id)
        )
        return result.scalars().first()

    async def get_processes(self, filters: InterviewProcessFilters) -> list[InterviewProcess]:
        stmt = (
            select(InterviewProcess)
            .join(Company, InterviewProcess.company_id == Company.id)
            .options(selectinload(InterviewProcess.stages))
        )
        if filters.company_id is not None:
            stmt = stmt.where(InterviewProcess.company_id == filters.company_id)
        if filters.status is not None:
            stmt = stmt.where(InterviewProcess.status == filters.status)
        stmt = stmt.order_by(
            case({"active": 0}, value=InterviewProcess.status, else_=1),
            _PRIORITY_ORDER,
            Company.name,
            InterviewProcess.role_title,
            InterviewProcess.department,
        ).offset(filters.offset).limit(filters.limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_active_processes(self) -> list[InterviewProcess]:
        result = await self._session.execute(
            select(InterviewProcess)
            .options(selectinload(InterviewProcess.stages))
            .where(InterviewProcess.status == "active")
            .order_by(InterviewProcess.created_at.desc())
        )
        return list(result.scalars().all())

    async def create_process(
        self, data: InterviewProcessCreate, first_stage: InterviewStage | None = None
    ) -> InterviewProcess:
        process = InterviewProcess(**data.model_dump())
        if first_stage is not None:
            process.stages = [first_stage]
        self._session.add(process)
        await self._session.commit()
        return await self.get_process(process.id)

    async def update_process(self, process_id: int, data: InterviewProcessUpdate) -> InterviewProcess | None:
        process = await self.get_process(process_id)
        if process is None:
            return None
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(process, field, value)
        await self._session.commit()
        return await self.get_process(process_id)

    async def delete_process(self, process_id: int) -> None:
        process = await self.get_process(process_id)
        if process is not None:
            await self._session.delete(process)
            await self._session.commit()
