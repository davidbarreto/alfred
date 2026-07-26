import json
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.core.working_memory.schemas import WorkingMemoryCreate, WorkingMemoryFilters
from app.features.core.working_memory.service import WorkingMemoryService
from app.features.language.sessions.repository import SessionRepository
from app.features.language.sessions.schemas import (
    DailyProgressRead,
    LoopAdvanceRead,
    LoopAdvanceRequest,
    NextPracticePrompt,
    ProductionSessionCreate,
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
_LANGUAGE_PENDING_KEY = "language:pending"


def format_feedback_summary(history: list[dict]) -> str:
    """Build a deterministic end-of-session summary from accumulated shadowing feedback."""
    scores = [entry["quality_score"] for entry in history if entry.get("quality_score") is not None]
    lines = [f"Shadowing session complete — {len(history)} rep(s)."]
    if scores:
        lines.append(f"Average score: {sum(scores) / len(scores):.0f}/100")
    for i, entry in enumerate(history, start=1):
        score = entry.get("quality_score")
        summary = entry.get("summary")
        score_part = f"{score:.0f}/100" if score is not None else "n/a"
        text_part = f" — {summary}" if summary else ""
        lines.append(f"{i}. {score_part}{text_part}")
    return "\n".join(lines)


class SessionService:

    def __init__(self, session: AsyncSession, working_memory_service: WorkingMemoryService) -> None:
        self._repo = SessionRepository(session)
        self._chunk_service = ChunkService(session)
        self._track_repo = TrackRepository(session)
        self._working_memory_service = working_memory_service

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
            ai_feedback_json=data.ai_feedback_json,
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

    async def record_production(self, data: ProductionSessionCreate) -> SessionRead:
        """Record a production attempt and update the chunk's production SRS state.
        Chunk-less attempts (chunk_id=None) are logged only; they never feed SRS."""
        feeds_srs = data.chunk_id is not None and data.quality_score is not None
        orm = await self._repo.create_session(
            track_id=data.track_id,
            chunk_id=data.chunk_id,
            session_type="production",
            feeds_srs=feeds_srs,
            task_type=data.task_type,
            prompt_text=data.prompt_text,
            audio_ref=data.audio_ref,
            ai_feedback_json=data.ai_feedback_json,
            quality_score=data.quality_score,
            transcript_or_notes=data.transcript_or_notes,
        )
        if data.chunk_id is not None and data.quality_score is not None:
            await self._chunk_service.apply_production_review(data.chunk_id, data.quality_score)
        logger.info(
            "Production attempt recorded: session_id=%d chunk_id=%s task=%s score=%s",
            orm.id, data.chunk_id, data.task_type, data.quality_score,
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
            ai_feedback_json=data.ai_feedback_json,
            quality_score=data.quality_score,
            transcript_or_notes=data.transcript_or_notes,
        )
        if feeds_srs and data.chunk_id is not None and data.quality_score is not None:
            await self._chunk_service.apply_srs_review(data.chunk_id, data.quality_score)
        logger.info("Session recorded: session_id=%d type=%r", orm.id, data.session_type)
        return SessionRead.model_validate(orm)

    async def advance_loop(self, data: LoopAdvanceRequest) -> LoopAdvanceRead:
        """Record one turn (review tap or shadowing attempt) and advance the practice/review
        loop deterministically, without going through chat/intent detection. Guards against
        duplicate taps: a request for a chunk_id that no longer matches the pending loop state
        is a stale no-op, since each real advance replaces the pending row with the next chunk."""
        pending = await self._working_memory_service.list(
            WorkingMemoryFilters(key=_LANGUAGE_PENDING_KEY, active_only=True)
        )
        pending_wm = pending[0] if pending else None
        if pending_wm is None:
            logger.debug("advance_loop: no pending loop, chunk_id=%d", data.chunk_id)
            return LoopAdvanceRead(status="stale")

        try:
            wm_data = json.loads(pending_wm.value)
        except (json.JSONDecodeError, TypeError):
            await self._working_memory_service.delete(pending_wm.id)
            return LoopAdvanceRead(status="stale")

        if wm_data.get("chunk_id") != data.chunk_id:
            logger.debug(
                "advance_loop: stale tap chunk_id=%d pending_chunk_id=%s",
                data.chunk_id, wm_data.get("chunk_id"),
            )
            return LoopAdvanceRead(status="stale")

        if data.quality_score is not None:
            await self.record_srs_review(SrsReviewCreate(
                track_id=wm_data.get("track_id"), chunk_id=data.chunk_id, quality_score=data.quality_score,
            ))

        mode = wm_data.get("mode", "practice")
        feedback_history = list(wm_data.get("feedback_history", []))
        if mode == "practice" and (data.feedback_score is not None or data.feedback_summary is not None):
            feedback_history.append({"quality_score": data.feedback_score, "summary": data.feedback_summary})

        remaining = int(wm_data.get("remaining", 1)) - 1
        forced_queue = list(wm_data.get("forced_queue", []))
        next_chunk: dict | None = None
        if remaining > 0:
            if forced_queue:
                next_chunk = forced_queue.pop(0)
            else:
                batches = await self._chunk_service.get_daily_batch(wm_data.get("track_id"))
                due = [c for batch in batches for c in batch.chunks if c.id != data.chunk_id]
                if due:
                    next_chunk = {"chunk_id": due[0].id, "text": due[0].text, "translation": due[0].translation}

        await self._working_memory_service.delete(pending_wm.id)

        if next_chunk is None:
            logger.info(
                "advance_loop: loop completed wm_id=%d mode=%s remaining=%d",
                pending_wm.id, mode, max(remaining, 0),
            )
            summary_text = format_feedback_summary(feedback_history) if feedback_history else None
            return LoopAdvanceRead(status="completed", summary_text=summary_text)

        new_wm_data = {
            **wm_data,
            "chunk_id": next_chunk["chunk_id"],
            "text": next_chunk["text"],
            "translation": next_chunk["translation"],
            "remaining": remaining,
            "forced_queue": forced_queue,
            "feedback_history": feedback_history,
        }
        await self._working_memory_service.create(WorkingMemoryCreate(
            key=_LANGUAGE_PENDING_KEY, value=json.dumps(new_wm_data), importance=1.0,
        ))
        logger.info(
            "advance_loop: loop advanced wm_id=%d next_chunk_id=%d remaining=%d",
            pending_wm.id, next_chunk["chunk_id"], remaining,
        )
        return LoopAdvanceRead(
            status="advanced",
            next_practice=NextPracticePrompt(
                mode=mode,
                track_id=wm_data["track_id"],
                track_code=wm_data.get("track_code", ""),
                chunk_id=next_chunk["chunk_id"],
                text=next_chunk["text"],
                translation=next_chunk["translation"],
                language_name=wm_data.get("language_name", ""),
                remaining=remaining,
            ),
        )

    async def get_daily_progress(self, track_id: int | None = None) -> list[DailyProgressRead]:
        """Return today's SRS completion progress per active track."""
        from app.features.language.tracks.schemas import TrackFilters
        tracks = await self._track_repo.get_tracks(TrackFilters(active_only=True))
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
