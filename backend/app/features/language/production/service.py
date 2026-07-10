import json
import logging
import random
import time
from uuid import uuid4

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.core.transcription.service import TranscriptionService
from app.features.language.chunks.repository import ChunkRepository
from app.features.language.chunks.schemas import ChunkCreate
from app.features.language.chunks.service import ChunkService
from app.features.language.production.prompts import (
    JOURNAL_TASK_TEMPLATE,
    JOURNAL_TOPICS,
    OPEN_ENDED_GRADING_PROMPT,
    PRODUCTION_GRADING_PROMPT,
    RETELL_PASSAGE_PROMPT,
    RETELL_TASK_TEMPLATE,
    RETELL_TOPICS,
    SENTENCE_TASK_TEMPLATE,
    SPEAK_TASK_TEMPLATE,
    SPEAK_TOPICS,
    SPOKEN_GRADING_PROMPT,
    SUGGESTION_LINE_TEMPLATE,
    TIMED_TASK_TEMPLATE,
    TIMED_TOPICS,
    TRANSLATE_TASK_TEMPLATE,
)
from app.features.language.production.schemas import (
    CHUNKLESS_TASK_TYPES,
    OPEN_ENDED_TASK_TYPES,
    PRODUCTION_TASK_TYPES,
    SPOKEN_TASK_TYPES,
    NewVocabularyCandidate,
    ProductionAttemptCreate,
    ProductionAttemptRead,
    ProductionGradingRead,
    ProductionMasteryRead,
    ProductionTaskRead,
    TrackMasteryStates,
)
from app.features.language.sessions.repository import SessionRepository
from app.features.language.sessions.schemas import ProductionSessionCreate
from app.features.language.sessions.service import SessionService
from app.features.language.srs import score_to_quality
from app.features.language.tracks.repository import TrackRepository
from app.features.language.tracks.schemas import TrackFilters
from app.integrations.llm_calls.repository import create_llm_call
from app.shared.audio import AudioConverter, FileStorage
from app.shared.llm import LlmProvider

logger = logging.getLogger(__name__)

_MAX_VOCABULARY_CANDIDATES = 3
_MAX_VOCABULARY_CANDIDATES_CHUNKLESS = 5
_MAX_SUGGESTED_CHUNKS = 3
_TIMED_TASK_SECONDS = 300


def _next_task_type(last_task_type: str | None) -> str:
    """Rotate through the task types, starting after the most recent one."""
    if last_task_type in PRODUCTION_TASK_TYPES:
        index = PRODUCTION_TASK_TYPES.index(last_task_type)
        return PRODUCTION_TASK_TYPES[(index + 1) % len(PRODUCTION_TASK_TYPES)]
    return PRODUCTION_TASK_TYPES[0]


def _build_prompt_text(task_type: str, language_name: str, chunk) -> str:
    if task_type == "translate":
        source_text = chunk.example_translation or chunk.translation
        return TRANSLATE_TASK_TEMPLATE.format(language_name=language_name, source_text=source_text)
    return SENTENCE_TASK_TEMPLATE.format(
        language_name=language_name, text=chunk.text, translation=chunk.translation
    )


def _build_open_ended_prompt(task_type: str, language_name: str, suggested_chunks: list) -> str:
    suggestion_line = ""
    if suggested_chunks:
        chunk_list = ", ".join(f'"{c.text}"' for c in suggested_chunks)
        suggestion_line = SUGGESTION_LINE_TEMPLATE.format(chunk_list=chunk_list)
    if task_type == "timed":
        return TIMED_TASK_TEMPLATE.format(
            minutes=_TIMED_TASK_SECONDS // 60,
            language_name=language_name,
            topic=random.choice(TIMED_TOPICS),
            suggestion_line=suggestion_line,
        )
    return JOURNAL_TASK_TEMPLATE.format(
        language_name=language_name,
        topic=random.choice(JOURNAL_TOPICS),
        suggestion_line=suggestion_line,
    )


def _build_speak_prompt(language_name: str, suggested_chunks: list) -> str:
    suggestion_line = ""
    if suggested_chunks:
        chunk_list = ", ".join(f'"{c.text}"' for c in suggested_chunks)
        suggestion_line = SUGGESTION_LINE_TEMPLATE.format(chunk_list=chunk_list)
    return SPEAK_TASK_TEMPLATE.format(
        language_name=language_name,
        topic=random.choice(SPEAK_TOPICS),
        suggestion_line=suggestion_line,
    )


def _parse_grading_json(raw: str) -> ProductionGradingRead:
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    data = json.loads(text)
    return ProductionGradingRead(
        score=float(data.get("score", 0)),
        errors=[str(e) for e in data.get("errors") or []],
        corrected_text=str(data.get("corrected_text") or ""),
        feedback=str(data.get("feedback") or ""),
        new_vocabulary=[
            NewVocabularyCandidate(text=str(v.get("text", "")), translation=str(v.get("translation", "")))
            for v in data.get("new_vocabulary") or []
            if isinstance(v, dict) and v.get("text")
        ],
    )


class ProductionService:

    def __init__(
        self,
        session: AsyncSession,
        llm_provider: LlmProvider,
        session_service: SessionService,
        chunk_service: ChunkService,
        chunk_repo: ChunkRepository,
        track_repo: TrackRepository,
        session_repo: SessionRepository,
        audio_storage: FileStorage | None = None,
        audio_converter: AudioConverter | None = None,
        transcription_service: TranscriptionService | None = None,
    ) -> None:
        self._session = session
        self._llm_provider = llm_provider
        self._session_service = session_service
        self._chunk_service = chunk_service
        self._chunk_repo = chunk_repo
        self._track_repo = track_repo
        self._session_repo = session_repo
        self._audio_storage = audio_storage
        self._audio_converter = audio_converter
        self._transcription_service = transcription_service

    async def get_next_task(
        self,
        track_id: int,
        task_type: str | None = None,
        exclude_chunk_id: int | None = None,
    ) -> ProductionTaskRead | None:
        """Pick the next production-due chunk and build the exercise for it.

        Chunk-less types (journal, timed, speak, retell) are not chunk-anchored: they
        are always available and only use due chunks as optional "try to use" suggestions."""
        track = await self._track_repo.get_track(track_id)
        if track is None:
            return None

        batches = await self._chunk_service.get_production_daily_batch(track_id)
        if task_type in SPOKEN_TASK_TYPES:
            return await self._build_spoken_task(track, task_type, batches)
        if task_type in OPEN_ENDED_TASK_TYPES:
            return self._build_open_ended_task(track, task_type, batches)
        if not batches:
            return None
        batch = batches[0]
        chunks = [c for c in batch.chunks if c.id != exclude_chunk_id]
        if not chunks:
            logger.debug("Production next task: no due chunks track_id=%d", track_id)
            return None
        chunk = chunks[0]

        if task_type not in PRODUCTION_TASK_TYPES:
            last = await self._session_repo.get_last_production_task_type(track_id)
            task_type = _next_task_type(last)

        prompt_text = _build_prompt_text(task_type, track.name, chunk)
        return ProductionTaskRead(
            track_id=track.id,
            track_code=track.code,
            language_name=track.name,
            chunk_id=chunk.id,
            task_type=task_type,
            prompt_text=prompt_text,
            text=chunk.text,
            translation=chunk.translation,
            cefr_level=chunk.cefr_level,
            total_due=batch.total_due,
        )

    def _build_open_ended_task(self, track, task_type: str, batches: list) -> ProductionTaskRead:
        suggested = batches[0].chunks[:_MAX_SUGGESTED_CHUNKS] if batches else []
        prompt_text = _build_open_ended_prompt(task_type, track.name, suggested)
        return ProductionTaskRead(
            track_id=track.id,
            track_code=track.code,
            language_name=track.name,
            chunk_id=None,
            task_type=task_type,
            prompt_text=prompt_text,
            text=None,
            translation=None,
            total_due=1,
            time_limit_seconds=_TIMED_TASK_SECONDS if task_type == "timed" else None,
        )

    async def _build_spoken_task(self, track, task_type: str, batches: list) -> ProductionTaskRead:
        passage_text = None
        if task_type == "retell":
            passage_text = await self._generate_retell_passage(track)
            prompt_text = RETELL_TASK_TEMPLATE.format(language_name=track.name, passage=passage_text)
        else:
            suggested = batches[0].chunks[:_MAX_SUGGESTED_CHUNKS] if batches else []
            prompt_text = _build_speak_prompt(track.name, suggested)
        return ProductionTaskRead(
            track_id=track.id,
            track_code=track.code,
            language_name=track.name,
            chunk_id=None,
            task_type=task_type,
            prompt_text=prompt_text,
            text=None,
            translation=None,
            total_due=1,
            passage_text=passage_text,
        )

    async def _generate_retell_passage(self, track) -> str:
        prompt = RETELL_PASSAGE_PROMPT.format(
            language_name=track.name,
            cefr_level=track.level,
            topic=random.choice(RETELL_TOPICS),
        )
        messages = [{"role": "user", "content": prompt}]
        t0 = time.monotonic()
        try:
            llm_response = await self._llm_provider.complete(messages)
        except Exception as exc:
            logger.error("Retell passage generation failed: track_id=%d error=%s", track.id, exc)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Could not generate the passage. Please try again in a moment.",
            ) from exc
        latency_ms = int((time.monotonic() - t0) * 1000)

        await create_llm_call(
            self._session,
            provider=self._llm_provider.provider,
            model=self._llm_provider.model,
            feature="production_task_generation",
            prompt=messages,
            response=llm_response.text,
            tokens_input=llm_response.tokens_input,
            tokens_output=llm_response.tokens_output,
            latency_ms=latency_ms,
        )
        return llm_response.text.strip().strip("`").strip()

    def _build_grading_prompt(self, data: ProductionAttemptCreate, track, chunk) -> str:
        if data.task_type in SPOKEN_TASK_TYPES:
            return SPOKEN_GRADING_PROMPT.format(
                language_name=track.name,
                cefr_level=track.level,
                task_type=data.task_type,
                prompt_text=data.prompt_text,
                response_text=data.response_text,
            )
        if data.task_type in OPEN_ENDED_TASK_TYPES:
            return OPEN_ENDED_GRADING_PROMPT.format(
                language_name=track.name,
                cefr_level=track.level,
                task_type=data.task_type,
                prompt_text=data.prompt_text,
                response_text=data.response_text,
            )
        reference_line = ""
        if data.task_type == "translate" and chunk.example_sentence:
            reference_line = f'Reference answer: "{chunk.example_sentence}"'
        return PRODUCTION_GRADING_PROMPT.format(
            language_name=track.name,
            cefr_level=chunk.cefr_level or track.level,
            task_type=data.task_type,
            text=chunk.text,
            translation=chunk.translation,
            prompt_text=data.prompt_text,
            reference_line=reference_line,
            response_text=data.response_text,
        )

    async def grade_attempt(
        self, data: ProductionAttemptCreate, audio_ref: str | None = None
    ) -> ProductionAttemptRead:
        """Grade a production attempt with the LLM, log it, and update production SRS.

        Chunk-less attempts (journal, timed, speak, retell) have no anchor chunk and
        never touch SRS. For spoken attempts submitted as audio, response_text is the
        transcript and audio_ref points at the stored recording."""
        chunk = None
        if data.task_type not in CHUNKLESS_TASK_TYPES:
            if data.chunk_id is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"chunk_id is required for {data.task_type!r} tasks",
                )
            chunk = await self._chunk_repo.get_chunk(data.chunk_id)
            if chunk is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chunk not found")
        track = await self._track_repo.get_track(data.track_id)
        if track is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Track not found")

        grading_prompt = self._build_grading_prompt(data, track, chunk)
        messages = [{"role": "user", "content": grading_prompt}]

        t0 = time.monotonic()
        try:
            llm_response = await self._llm_provider.complete(messages)
        except Exception as exc:
            logger.error("Production grading LLM call failed: chunk_id=%s error=%s", data.chunk_id, exc)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="AI grading temporarily unavailable. Please try again in a moment.",
            ) from exc
        latency_ms = int((time.monotonic() - t0) * 1000)

        await create_llm_call(
            self._session,
            provider=self._llm_provider.provider,
            model=self._llm_provider.model,
            feature="production_grading",
            prompt=messages,
            response=llm_response.text,
            tokens_input=llm_response.tokens_input,
            tokens_output=llm_response.tokens_output,
            latency_ms=latency_ms,
        )

        try:
            grading = _parse_grading_json(llm_response.text)
        except (json.JSONDecodeError, ValueError, TypeError) as exc:
            logger.error(
                "Production grading returned invalid JSON: chunk_id=%s error=%s", data.chunk_id, exc
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="AI grading returned an unreadable result. Please try again.",
            ) from exc

        quality_score = score_to_quality(grading.score)
        session_read = await self._session_service.record_production(
            ProductionSessionCreate(
                track_id=data.track_id,
                chunk_id=data.chunk_id,
                task_type=data.task_type,
                prompt_text=data.prompt_text,
                quality_score=quality_score,
                ai_feedback_json=grading.model_dump(),
                transcript_or_notes=data.response_text,
                audio_ref=audio_ref,
            )
        )

        max_vocabulary = (
            _MAX_VOCABULARY_CANDIDATES_CHUNKLESS
            if data.task_type in CHUNKLESS_TASK_TYPES
            else _MAX_VOCABULARY_CANDIDATES
        )
        await self._queue_new_vocabulary(data.track_id, grading.new_vocabulary, max_vocabulary)

        logger.info(
            "Production attempt graded: session_id=%d chunk_id=%s task=%s score=%.0f",
            session_read.id, data.chunk_id, data.task_type, grading.score,
        )
        return ProductionAttemptRead(
            session_id=session_read.id,
            track_id=data.track_id,
            chunk_id=data.chunk_id,
            task_type=data.task_type,
            quality_score=quality_score,
            grading=grading,
            transcript=data.response_text if audio_ref is not None else None,
        )

    async def grade_audio_attempt(
        self,
        track_id: int,
        task_type: str,
        prompt_text: str,
        audio: bytes,
    ) -> ProductionAttemptRead:
        """Store a spoken attempt's recording, transcribe it, and grade the transcript."""
        if task_type not in SPOKEN_TASK_TYPES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Audio attempts are only supported for {', '.join(SPOKEN_TASK_TYPES)} tasks",
            )
        if self._audio_storage is None or self._audio_converter is None or self._transcription_service is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Spoken production is not available",
            )

        ogg_audio = await self._audio_converter.to_ogg_opus(audio)
        audio_ref = f"production/{uuid4()}.ogg"
        await self._audio_storage.save(ogg_audio, audio_ref)

        try:
            transcription = await self._transcription_service.transcribe(ogg_audio, "audio/ogg")
        except Exception as exc:
            logger.error("Production transcription failed: track_id=%d error=%s", track_id, exc)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Could not transcribe your recording. Please try again.",
            ) from exc
        transcript = transcription.text.strip()
        if not transcript:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="We could not hear any speech in the recording. Please try again.",
            )

        logger.info(
            "Production audio attempt transcribed: track_id=%d task=%s audio_ref=%s chars=%d",
            track_id, task_type, audio_ref, len(transcript),
        )
        return await self.grade_attempt(
            ProductionAttemptCreate(
                track_id=track_id,
                chunk_id=None,
                task_type=task_type,
                prompt_text=prompt_text,
                response_text=transcript,
            ),
            audio_ref=audio_ref,
        )

    async def _queue_new_vocabulary(
        self,
        track_id: int,
        candidates: list[NewVocabularyCandidate],
        max_candidates: int = _MAX_VOCABULARY_CANDIDATES,
    ) -> None:
        """Push graded-out vocabulary into the existing triage/approval queue."""
        for candidate in candidates[:max_candidates]:
            if not candidate.text.strip() or not candidate.translation.strip():
                continue
            try:
                await self._chunk_service.create_chunk(ChunkCreate(
                    track_id=track_id,
                    chunk_type="word",
                    text=candidate.text.strip(),
                    translation=candidate.translation.strip(),
                    frequency_source="llm_suggested",
                    status="pending_triage",
                ))
            except Exception:
                logger.error(
                    "Failed to queue vocabulary candidate: track_id=%d text=%r",
                    track_id, candidate.text, exc_info=True,
                )

    async def get_mastery(self, track_id: int | None = None) -> list[ProductionMasteryRead]:
        """Recognition vs. production mastery split per active track."""
        tracks = await self._track_repo.get_tracks(TrackFilters(active_only=True))
        if track_id is not None:
            tracks = [t for t in tracks if t.id == track_id]

        result = []
        for track in tracks:
            recognition_states = await self._chunk_repo.count_by_state_for_track(track.id)
            production_states = await self._chunk_repo.count_by_state_for_track(track.id, production=True)
            locked = await self._chunk_repo.count_production_locked_for_track(track.id)
            recognition_due = await self._chunk_repo.count_due_for_track(track.id)
            production_due = await self._chunk_repo.count_production_due_for_track(track.id)

            recognition = TrackMasteryStates(
                **{k: v for k, v in recognition_states.items() if k in TrackMasteryStates.model_fields},
                due=recognition_due,
            )
            # Locked chunks sit in prod_state "new"; report only the unlocked portion as "new".
            production_new = max(0, production_states.get("new", 0) - locked)
            production = TrackMasteryStates(
                new=production_new,
                learning=production_states.get("learning", 0),
                review=production_states.get("review", 0),
                relearning=production_states.get("relearning", 0),
                due=production_due,
            )
            result.append(ProductionMasteryRead(
                track_id=track.id,
                track_code=track.code,
                total_active=sum(recognition_states.values()),
                recognition=recognition,
                production=production,
                production_locked=locked,
            ))
        return result
