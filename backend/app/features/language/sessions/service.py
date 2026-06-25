import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.language.sessions.repository import SessionRepository
from app.features.language.sessions.schemas import (
    DailyProgressRead,
    SessionCreate,
    SessionFilters,
    SessionRead,
    ShadowingSessionCreate,
    SrsReviewCreate,
)
from app.features.language.chunks.service import ChunkService
from app.features.language.tracks.repository import TrackRepository

logger = logging.getLogger(__name__)

_SRS_FEEDING_TYPES = {"srs_review", "shadowing"}


class SessionService:

    def __init__(self, session: AsyncSession) -> None:
        self._repo = SessionRepository(session)
        self._chunk_service = ChunkService(session)
        self._track_repo = TrackRepository(session)

    async def get_session(self, session_id: int) -> SessionRead | None:
        orm = await self._repo.get_session(session_id)
        return SessionRead.model_validate(orm) if orm else None

    async def get_sessions(self, filters: SessionFilters) -> list[SessionRead]:
        sessions = await self._repo.get_sessions(filters)
        return [SessionRead.model_validate(s) for s in sessions]

    async def record_srs_review(self, data: SrsReviewCreate) -> SessionRead:
        """Record a typed-recall review and update chunk FSRS state."""
        orm = await self._repo.create_session(
            track_id=data.track_id,
            chunk_id=data.chunk_id,
            session_type="srs_review",
            feeds_srs=True,
            quality_score=data.quality_score,
            transcript_or_notes=data.transcript_or_notes,
        )
        await self._chunk_service.apply_srs_review(data.chunk_id, data.quality_score)
        logger.info(
            "SRS review recorded: session_id=%d chunk_id=%d score=%.1f",
            orm.id, data.chunk_id, data.quality_score,
        )
        return SessionRead.model_validate(orm)

    async def record_shadowing(
        self,
        data: ShadowingSessionCreate,
        audio_ref: str | None = None,
    ) -> SessionRead:
        """Record a shadowing session. quality_score may come from Gemini (set externally)."""
        feeds_srs = data.quality_score is not None
        orm = await self._repo.create_session(
            track_id=data.track_id,
            chunk_id=data.chunk_id,
            session_type="shadowing",
            feeds_srs=feeds_srs,
            audio_ref=audio_ref,
            gemini_feedback_json=data.gemini_feedback_json,
            quality_score=data.quality_score,
            transcript_or_notes=data.transcript_or_notes,
        )
        if data.chunk_id is not None and data.quality_score is not None:
            await self._chunk_service.apply_srs_review(data.chunk_id, data.quality_score)
        logger.info(
            "Shadowing session recorded: session_id=%d chunk_id=%s score=%s",
            orm.id, data.chunk_id, data.quality_score,
        )
        return SessionRead.model_validate(orm)

    async def record_session(self, data: SessionCreate) -> SessionRead:
        """Generic session recording for conversation and correction types."""
        feeds_srs = data.session_type in _SRS_FEEDING_TYPES and data.quality_score is not None
        orm = await self._repo.create_session(
            track_id=data.track_id,
            chunk_id=data.chunk_id,
            session_type=data.session_type,
            feeds_srs=feeds_srs,
            audio_ref=data.audio_ref,
            gemini_feedback_json=data.gemini_feedback_json,
            quality_score=data.quality_score,
            transcript_or_notes=data.transcript_or_notes,
        )
        if feeds_srs and data.chunk_id is not None and data.quality_score is not None:
            await self._chunk_service.apply_srs_review(data.chunk_id, data.quality_score)
        logger.info("Session recorded: session_id=%d type=%r", orm.id, data.session_type)
        return SessionRead.model_validate(orm)

    async def get_daily_progress(self, track_id: int | None = None) -> list[DailyProgressRead]:
        """Return today's SRS completion progress per active track."""
        from app.features.language.tracks.schemas import TrackFilters as TF
        tracks = await self._track_repo.get_tracks(type("F", (), {"active_only": True})())
        if track_id is not None:
            tracks = [t for t in tracks if t.id == track_id]

        progress = []
        for track in tracks:
            completed = await self._repo.count_srs_reviews_today(track.id)
            progress.append(DailyProgressRead(
                track_id=track.id,
                track_code=track.code,
                daily_quota=track.daily_quota,
                completed_today=completed,
                quota_met=completed >= track.daily_quota,
            ))
        return progress
