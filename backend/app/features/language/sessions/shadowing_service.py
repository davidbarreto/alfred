import logging
import time
from dataclasses import asdict
from uuid import uuid4

from fastapi import BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import async_session
from app.features.core.working_memory.service import WorkingMemoryService
from app.features.language.chunks.repository import ChunkRepository
from app.features.language.sessions.schemas import SessionRead, ShadowingSessionCreate
from app.features.language.sessions.service import SessionService
from app.features.language.srs import score_to_quality
from app.features.language.tracks.repository import TrackRepository
from app.integrations.llm_calls.repository import create_llm_call
from app.shared.audio import AudioAnalysisProvider, AudioConverter, FileStorage

logger = logging.getLogger(__name__)


class ShadowingService:

    def __init__(
        self,
        session: AsyncSession,
        session_service: SessionService,
        audio_storage: FileStorage,
        audio_converter: AudioConverter,
        analysis_provider: AudioAnalysisProvider,
    ) -> None:
        self._session = session
        self._session_service = session_service
        self._audio_storage = audio_storage
        self._audio_converter = audio_converter
        self._analysis_provider = analysis_provider

    async def record_shadowing_with_audio(
        self, track_id: int, chunk_id: int | None, audio: bytes, background_tasks: BackgroundTasks
    ) -> SessionRead:
        """Save the audio and create the session row immediately; pronunciation grading (the
        slow Gemini call) runs afterwards in the background so the caller isn't blocked on it."""
        ogg_audio = await self._audio_converter.to_ogg_opus(audio)
        audio_ref = f"shadowing/{uuid4()}.ogg"
        await self._audio_storage.save(ogg_audio, audio_ref)

        result = await self._session_service.record_shadowing(
            ShadowingSessionCreate(track_id=track_id, chunk_id=chunk_id),
            audio_ref=audio_ref,
            grading_status="pending" if chunk_id is not None else "skipped",
        )
        logger.info(
            "Shadowing audio uploaded: session_id=%d chunk_id=%s audio_ref=%s",
            result.id, chunk_id, audio_ref,
        )
        if chunk_id is not None:
            background_tasks.add_task(
                self._grade_shadowing_in_background, result.id, chunk_id, track_id, ogg_audio,
            )
        return result

    async def _grade_shadowing_in_background(
        self, session_id: int, chunk_id: int, track_id: int, ogg_audio: bytes
    ) -> None:
        """Runs after the response has been sent; opens its own DB session since the
        request-scoped one is no longer valid by the time a background task executes."""
        async with async_session() as session:
            session_service = SessionService(session, WorkingMemoryService(session))
            chunk_repo = ChunkRepository(session)
            track_repo = TrackRepository(session)

            chunk = await chunk_repo.get_chunk(chunk_id)
            if chunk is None:
                logger.warning("Shadowing grading: chunk not found id=%d", chunk_id)
                await session_service.update_shadowing_grading(session_id, None, None, None, "failed")
                return

            track = await track_repo.get_track(chunk.track_id)
            language_name = track.name if track else str(track_id)
            prompt_summary = f'Shadowing analysis: text="{chunk.text}" language={language_name}'
            t0 = time.monotonic()
            try:
                call_result = await self._analysis_provider.analyze_pronunciation(
                    ogg_audio, "audio/ogg", chunk.text, chunk.translation, language_name,
                )
            except Exception:
                logger.error("Pronunciation analysis failed: chunk_id=%d", chunk_id, exc_info=True)
                await session_service.update_shadowing_grading(session_id, None, None, None, "failed")
                return

            latency_ms = int((time.monotonic() - t0) * 1000)
            analysis = call_result.analysis
            await create_llm_call(
                session,
                provider=self._analysis_provider.provider,
                model=self._analysis_provider.model,
                feature="pronunciation_analysis",
                prompt=[{"role": "user", "content": prompt_summary}],
                response=call_result.raw_response,
                tokens_input=call_result.tokens_input,
                tokens_output=call_result.tokens_output,
                finish_reason=call_result.finish_reason,
                latency_ms=latency_ms,
                is_audio=True,
            )
            await session_service.update_shadowing_grading(
                session_id,
                quality_score=score_to_quality(analysis.score),
                ai_feedback_json=asdict(analysis),
                transcript_or_notes=analysis.summary,
                grading_status="done",
            )
