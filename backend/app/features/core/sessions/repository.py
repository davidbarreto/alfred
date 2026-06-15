from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.core.sessions.schemas import SessionCreate, SessionFilters
from app.features.core.sessions.tables import Session

_SESSION_EXPIRY_HOURS = 1


class SessionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, session_id: int) -> Session | None:
        result = await self._session.execute(select(Session).where(Session.id == session_id))
        return result.scalars().first()

    async def list(self, filters: SessionFilters) -> list[Session]:
        query = select(Session)
        if filters.active_only:
            query = query.where(Session.finished_at.is_(None))
        query = query.order_by(Session.created_at.desc())
        result = await self._session.execute(query)
        return list(result.scalars().all())

    async def create(self, data: SessionCreate) -> Session:
        session_obj = Session(**data.model_dump())
        self._session.add(session_obj)
        await self._session.commit()
        await self._session.refresh(session_obj)
        return session_obj

    async def get_active_by_source(self, source: str, external_id: str) -> Session | None:
        expiry_cutoff = datetime.now(timezone.utc) - timedelta(hours=_SESSION_EXPIRY_HOURS)
        result = await self._session.execute(
            select(Session).where(
                Session.source == source,
                Session.external_id == external_id,
                Session.finished_at.is_(None),
                Session.last_interaction_at >= expiry_cutoff,
            )
        )
        return result.scalars().first()

    async def touch(self, session_id: int) -> None:
        session_obj = await self.get(session_id)
        if session_obj is not None:
            session_obj.last_interaction_at = datetime.now(timezone.utc)
            await self._session.commit()

    async def finish(self, session_id: int) -> Session | None:
        session_obj = await self.get(session_id)
        if session_obj is None:
            return None
        session_obj.finished_at = datetime.now(timezone.utc)
        await self._session.commit()
        await self._session.refresh(session_obj)
        return session_obj

    async def delete(self, session_id: int) -> bool:
        session_obj = await self.get(session_id)
        if session_obj is None:
            return False
        await self._session.delete(session_obj)
        await self._session.commit()
        return True
