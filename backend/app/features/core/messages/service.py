from sqlalchemy.ext.asyncio import AsyncSession

from app.features.core.messages.repository import MessageRepository
from app.features.core.messages.schemas import MessageCreate, MessageFilters, MessageRead


class MessageService:
    def __init__(self, session: AsyncSession) -> None:
        self._repo = MessageRepository(session)

    async def get(self, message_id: int) -> MessageRead | None:
        obj = await self._repo.get(message_id)
        return MessageRead.model_validate(obj) if obj else None

    async def list(self, filters: MessageFilters) -> list[MessageRead]:
        items = await self._repo.list(filters)
        return [MessageRead.model_validate(i) for i in items]

    async def create(self, data: MessageCreate) -> MessageRead:
        obj = await self._repo.create(data)
        return MessageRead.model_validate(obj)
