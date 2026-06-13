from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.core.command_executions.schemas import (
    CommandExecutionCreate,
    CommandExecutionFilters,
    CommandExecutionUpdate,
)
from app.features.core.command_executions.tables import CommandExecution


class CommandExecutionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, execution_id: int) -> CommandExecution | None:
        result = await self._session.execute(
            select(CommandExecution).where(CommandExecution.id == execution_id)
        )
        return result.scalars().first()

    async def list(self, filters: CommandExecutionFilters) -> list[CommandExecution]:
        query = select(CommandExecution)
        if filters.message_id is not None:
            query = query.where(CommandExecution.message_id == filters.message_id)
        if filters.status is not None:
            query = query.where(CommandExecution.status == filters.status)
        if filters.command_name is not None:
            query = query.where(CommandExecution.command_name == filters.command_name)
        query = query.order_by(CommandExecution.created_at.desc())
        result = await self._session.execute(query)
        return list(result.scalars().all())

    async def create(self, data: CommandExecutionCreate) -> CommandExecution:
        execution = CommandExecution(**data.model_dump())
        self._session.add(execution)
        await self._session.commit()
        await self._session.refresh(execution)
        return execution

    async def update(self, execution_id: int, data: CommandExecutionUpdate) -> CommandExecution | None:
        execution = await self.get(execution_id)
        if execution is None:
            return None
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(execution, field, value)
        await self._session.commit()
        await self._session.refresh(execution)
        return execution
