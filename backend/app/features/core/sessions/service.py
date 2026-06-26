import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.core.sessions.repository import SessionRepository
from app.features.core.sessions.schemas import SessionCreate, SessionFilters, SessionRead

logger = logging.getLogger(__name__)


class SessionService:
    def __init__(self, session: AsyncSession) -> None:
        self._repo = SessionRepository(session)

    async def get(self, session_id: int) -> SessionRead | None:
        obj = await self._repo.get(session_id)
        return SessionRead.model_validate(obj) if obj else None

    async def list(self, filters: SessionFilters) -> list[SessionRead]:
        items = await self._repo.list(filters)
        return [SessionRead.model_validate(i) for i in items]

    async def create(self, data: SessionCreate) -> SessionRead:
        obj = await self._repo.create(data)
        logger.info("Session created: id=%d source=%r external_id=%r", obj.id, data.source, data.external_id)
        return SessionRead.model_validate(obj)

    async def get_or_create_active(self, source: str, external_id: str) -> tuple[SessionRead, bool]:
        obj = await self._repo.get_active_by_source(source, external_id)
        if obj is not None:
            await self._repo.touch(obj.id)
            logger.debug("Session reused: id=%d source=%r external_id=%r", obj.id, source, external_id)
            return SessionRead.model_validate(obj), False
        obj = await self._repo.create(SessionCreate(source=source, external_id=external_id))
        logger.info("Session created (get_or_create): id=%d source=%r external_id=%r", obj.id, source, external_id)
        return SessionRead.model_validate(obj), True

    async def finish(self, session_id: int) -> SessionRead | None:
        obj = await self._repo.finish(session_id)
        if obj:
            logger.info("Session finished: id=%d", session_id)
        else:
            logger.debug("Session finish: id=%d not found", session_id)
        return SessionRead.model_validate(obj) if obj else None

    async def delete(self, session_id: int) -> bool:
        deleted = await self._repo.delete(session_id)
        if deleted:
            logger.info("Session deleted: id=%d", session_id)
        else:
            logger.debug("Session delete: id=%d not found", session_id)
        return deleted
