from datetime import date, datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.language.sessions.tables import LearningSession
from app.features.language.sessions.schemas import SessionFilters


class SessionRepository:

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_session(self, session_id: int) -> LearningSession | None:
        result = await self._session.execute(
            select(LearningSession).where(LearningSession.id == session_id)
        )
        return result.scalars().first()

    async def get_sessions(self, filters: SessionFilters) -> list[LearningSession]:
        query = select(LearningSession)
        if filters.track_id is not None:
            query = query.where(LearningSession.track_id == filters.track_id)
        if filters.chunk_id is not None:
            query = query.where(LearningSession.chunk_id == filters.chunk_id)
        if filters.session_type is not None:
            query = query.where(LearningSession.session_type == filters.session_type)
        query = query.order_by(LearningSession.created_at.desc()).limit(filters.limit).offset(filters.offset)
        result = await self._session.execute(query)
        return list(result.scalars().all())

    async def create_session(
        self,
        track_id: int,
        chunk_id: int | None,
        session_type: str,
        feeds_srs: bool,
        audio_ref: str | None = None,
        ai_feedback_json: dict | None = None,
        quality_score: float | None = None,
        transcript_or_notes: str | None = None,
    ) -> LearningSession:
        ls = LearningSession(
            track_id=track_id,
            chunk_id=chunk_id,
            session_type=session_type,
            feeds_srs=feeds_srs,
            audio_ref=audio_ref,
            ai_feedback_json=ai_feedback_json,
            quality_score=quality_score,
            transcript_or_notes=transcript_or_notes,
        )
        self._session.add(ls)
        await self._session.commit()
        await self._session.refresh(ls)
        return ls

    async def count_srs_reviews_today(self, track_id: int) -> int:
        today_start = datetime.combine(date.today(), datetime.min.time()).replace(tzinfo=timezone.utc)
        result = await self._session.execute(
            select(func.count(LearningSession.id)).where(
                LearningSession.track_id == track_id,
                LearningSession.feeds_srs.is_(True),
                LearningSession.created_at >= today_start,
            )
        )
        return result.scalar_one()
