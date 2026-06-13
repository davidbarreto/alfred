from sqlalchemy.ext.asyncio import AsyncSession

from app.features.core.command_executions.repository import CommandExecutionRepository
from app.features.core.command_executions.schemas import (
    CommandExecutionCreate,
    CommandExecutionFilters,
    CommandExecutionRead,
    CommandExecutionUpdate,
)


class CommandExecutionService:
    def __init__(self, session: AsyncSession) -> None:
        self._repo = CommandExecutionRepository(session)

    async def get(self, execution_id: int) -> CommandExecutionRead | None:
        obj = await self._repo.get(execution_id)
        return CommandExecutionRead.model_validate(obj) if obj else None

    async def list(self, filters: CommandExecutionFilters) -> list[CommandExecutionRead]:
        items = await self._repo.list(filters)
        return [CommandExecutionRead.model_validate(i) for i in items]

    async def create(self, data: CommandExecutionCreate) -> CommandExecutionRead:
        obj = await self._repo.create(data)
        return CommandExecutionRead.model_validate(obj)

    async def update(self, execution_id: int, data: CommandExecutionUpdate) -> CommandExecutionRead | None:
        obj = await self._repo.update(execution_id, data)
        return CommandExecutionRead.model_validate(obj) if obj else None
