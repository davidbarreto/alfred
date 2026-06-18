from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.core.messages.schemas import MessageCreate, MessageFilters
from app.features.core.messages.tables import Message


class MessageRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, message_id: int) -> Message | None:
        result = await self._session.execute(select(Message).where(Message.id == message_id))
        return result.scalars().first()

    async def list(self, filters: MessageFilters) -> list[Message]:
        query = select(Message)
        if filters.session_id is not None:
            query = query.where(Message.session_id == filters.session_id)
        if filters.role is not None:
            query = query.where(Message.role == filters.role)
        if filters.limit is not None:
            query = query.order_by(Message.created_at.desc()).limit(filters.limit)
            result = await self._session.execute(query)
            return list(reversed(result.scalars().all()))
        query = query.order_by(Message.created_at.asc())
        result = await self._session.execute(query)
        return list(result.scalars().all())

    async def create(self, data: MessageCreate) -> Message:
        message = Message(**data.model_dump())
        self._session.add(message)
        await self._session.commit()
        await self._session.refresh(message)
        return message
