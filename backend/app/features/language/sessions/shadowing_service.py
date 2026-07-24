import logging
import time
from dataclasses import asdict
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

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
        chunk_repo: ChunkRepository,
        track_repo: TrackRepository,
        audio_storage: FileStorage,
        audio_converter: AudioConverter,
        analysis_provider: AudioAnalysisProvider,
    ) -> None:
        self._session = session
        self._session_service = session_service
        self._chunk_repo = chunk_repo
        self._track_repo = track_repo
        self._audio_storage = audio_storage
        self._audio_converter = audio_converter
        self._analysis_provider = analysis_provider

    async def record_shadowing_with_audio(
        self, track_id: int, chunk_id: int | None, audio: bytes
    ) -> SessionRead:
        ogg_audio = await self._audio_converter.to_ogg_opus(audio)
        audio_ref = f"shadowing/{uuid4()}.ogg"
        await self._audio_storage.save(ogg_audio, audio_ref)

        analysis = None
        if chunk_id is not None:
            chunk = await self._chunk_repo.get_chunk(chunk_id)
            if chunk is not None:
                track = await self._track_repo.get_track(chunk.track_id)
                language_name = track.name if track else str(track_id)
                prompt_summary = f'Shadowing analysis: text="{chunk.text}" language={language_name}'
                t0 = time.monotonic()
                try:
                    call_result = await self._analysis_provider.analyze_pronunciation(
                        ogg_audio, "audio/ogg", chunk.text, chunk.translation, language_name,
                    )
                except Exception:
                    logger.error("Pronunciation analysis failed: chunk_id=%d", chunk_id, exc_info=True)
                else:
                    latency_ms = int((time.monotonic() - t0) * 1000)
                    analysis = call_result.analysis
                    await create_llm_call(
                        self._session,
                        provider=self._analysis_provider.provider,
                        model=self._analysis_provider.model,
                        feature="pronunciation_analysis",
                        prompt=[{"role": "user", "content": prompt_summary}],
                        response=call_result.raw_response,
                        tokens_input=call_result.tokens_input,
                        tokens_output=call_result.tokens_output,
                        latency_ms=latency_ms,
                        is_audio=True,
                    )

        result = await self._session_service.record_shadowing(
            ShadowingSessionCreate(
                track_id=track_id,
                chunk_id=chunk_id,
                quality_score=score_to_quality(analysis.score) if analysis else None,
                ai_feedback_json=asdict(analysis) if analysis else None,
                transcript_or_notes=analysis.summary if analysis else None,
            ),
            audio_ref=audio_ref,
        )
        logger.info(
            "Shadowing audio uploaded: session_id=%d chunk_id=%s audio_ref=%s analyzed=%s",
            result.id, chunk_id, audio_ref, analysis is not None,
        )
        return result
