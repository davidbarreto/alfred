from __future__ import annotations

import base64
import json
import logging
import time
from uuid import uuid4

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.core.messages.schemas import MessageCreate
from app.features.core.messages.service import MessageService
from app.features.language.chunks.pronunciation_service import PronunciationService
from app.features.language.chunks.schemas import NewVocabularyCandidate
from app.features.language.chunks.service import ChunkService
from app.features.language.conversation.prompts import (
    CONVERSATION_OPENING_PROMPT,
    CONVERSATION_SUMMARY_PROMPT,
    CONVERSATION_TURN_PROMPT,
    ROLEPLAY_OPENING_PROMPT,
    ROLEPLAY_SUMMARY_PROMPT,
    ROLEPLAY_TURN_PROMPT,
)
from app.features.language.conversation.repository import ConversationRepository
from app.features.language.conversation.schemas import (
    ConversationEndRead,
    ConversationStartRead,
    ConversationThreadFilters,
    ConversationThreadRead,
    ConversationTurnRead,
    ConversationTurnResultRead,
)
from app.features.language.level_guidance import level_guidance
from app.features.language.sessions.schemas import SessionCreate
from app.features.language.sessions.service import SessionService as LanguageSessionService
from app.features.language.tracks.repository import TrackRepository
from app.integrations.llm_calls.repository import create_llm_call
from app.shared.audio import AudioConverter, FileStorage, styled_for_tts
from app.shared.conversation import ConversationProvider, ConversationTurnResult
from app.shared.llm import LlmProvider

logger = logging.getLogger(__name__)

_MAX_VOCABULARY_CANDIDATES = 3
# Free conversation otherwise waits for David to speak first; at total-beginner level that
# leaves him with no scaffolding, so this is the one level that also gets an opening line.
_BEGINNER_LEVEL = "A0"


def _parse_summary_json(raw: str) -> tuple[str, list[NewVocabularyCandidate]]:
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    data = json.loads(text)
    summary = str(data.get("summary") or "").strip()
    candidates = [
        NewVocabularyCandidate(
            text=str(v.get("text", "")),
            translation=str(v.get("translation", "")),
            cefr_level=v.get("cefr_level") or None,
        )
        for v in data.get("new_vocabulary") or []
        if isinstance(v, dict) and v.get("text")
    ]
    return summary, candidates


class ConversationService:
    """Language practice chat: scoped thread → turn-by-turn → wrap-up summary.

    Covers both modes — "roleplay" (scripted scenario, opens in character) and
    "conversation" (free chat on an optional topic) — and both modalities. Audio turns
    go to the model natively so it can judge pronunciation; text turns skip that step.
    Either way a turn is recorded identically, carrying an optional coaching tip, and
    every session ends with generated feedback."""

    def __init__(
        self,
        session: AsyncSession,
        thread_repo: ConversationRepository,
        message_service: MessageService,
        language_session_service: LanguageSessionService,
        track_repo: TrackRepository,
        chunk_service: ChunkService,
        audio_storage: FileStorage,
        audio_converter: AudioConverter,
        conversation_provider: ConversationProvider,
        pronunciation_service: PronunciationService,
        llm_provider: LlmProvider,
    ) -> None:
        self._session = session
        self._thread_repo = thread_repo
        self._message_service = message_service
        self._language_session_service = language_session_service
        self._track_repo = track_repo
        self._chunk_service = chunk_service
        self._audio_storage = audio_storage
        self._audio_converter = audio_converter
        self._conversation_provider = conversation_provider
        self._pronunciation_service = pronunciation_service
        self._llm_provider = llm_provider

    async def get_turn_audio_ref(self, turn_id: int) -> str | None:
        turn = await self._thread_repo.get_turn(turn_id)
        return turn.audio_ref if turn else None

    async def get_threads(self, filters: ConversationThreadFilters) -> list[ConversationThreadRead]:
        threads = await self._thread_repo.get_threads(filters)
        logger.debug("Conversation: %d threads listed", len(threads))
        return [ConversationThreadRead.model_validate(t) for t in threads]

    async def get_thread_turns(self, thread_id: int) -> list[ConversationTurnRead]:
        thread = await self._thread_repo.get_thread(thread_id)
        if thread is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Conversation thread not found"
            )
        turns = await self._thread_repo.get_turns_with_messages(thread_id)
        return [
            ConversationTurnRead(
                id=turn.id,
                thread_id=turn.thread_id,
                message_id=turn.message_id,
                role=message.role,
                content=message.content,
                is_audio=turn.is_audio,
                audio_ref=turn.audio_ref,
                tip=turn.tip,
                created_at=turn.created_at,
            )
            for turn, message in turns
        ]

    async def _synthesize_and_save(
        self, text: str, track_code: str, tone: str | None = None
    ) -> tuple[bytes | None, str | None]:
        """Best-effort: voice replies are a nice-to-have on top of the text reply, which has
        already succeeded by the time this runs. A synthesis failure shouldn't take the whole
        turn down with it — fall back to text-only instead."""
        tts_text = styled_for_tts(text, tone)
        try:
            audio, _ = await self._pronunciation_service.get_audio(tts_text, track_code, audio_format="ogg")
        except Exception as exc:
            logger.error("Conversation: TTS synthesis failed track_code=%s error=%s", track_code, exc)
            return None, None
        audio_ref = f"conversation/{uuid4()}.ogg"
        await self._audio_storage.save(audio, audio_ref)
        return audio, audio_ref

    @staticmethod
    def _effective_level(override: str | None, track) -> str:
        return override or track.level

    async def start(
        self,
        track_id: int,
        message_id: int,
        mode: str,
        scenario: str | None,
        voice_reply: bool,
        level_override: str | None = None,
    ) -> ConversationStartRead:
        """Open a practice thread. Roleplay needs a scenario and gets an in-character
        opening line; free conversation takes an optional topic and normally waits for
        David to speak first, except at A0 where he has no scaffolding to draw on, so it
        gets an English-led opening line too. level_override is a punctual per-session
        CEFR override (e.g. "A0" for a total-beginner register); it falls back to the
        track's own level and is never written back to the track."""
        track = await self._track_repo.get_track(track_id)
        if track is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Track not found")

        origin_message = await self._message_service.get(message_id)
        if origin_message is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found")
        chat_session_id = origin_message.session_id

        thread = await self._thread_repo.create_thread(
            track_id, chat_session_id, mode, scenario, voice_reply, level_override
        )

        effective_level = self._effective_level(level_override, track)
        opening_text: str | None = None
        opening_audio_ref: str | None = None
        opening_audio_base64: str | None = None
        if mode == "roleplay":
            opening_text = await self._generate_opening(
                track_id, track.name, scenario or "", effective_level
            )
        elif effective_level == _BEGINNER_LEVEL:
            opening_text = await self._generate_beginner_opening(
                track_id, track.name, effective_level, scenario
            )

        if opening_text is not None:
            message = await self._message_service.create(
                MessageCreate(
                    session_id=chat_session_id,
                    role="assistant",
                    content=opening_text,
                    meta={"conversation_thread_id": thread.id},
                )
            )
            if voice_reply:
                opening_audio, opening_audio_ref = await self._synthesize_and_save(opening_text, track.code)
                if opening_audio is not None:
                    opening_audio_base64 = base64.b64encode(opening_audio).decode("ascii")
            await self._thread_repo.create_turn(
                thread_id=thread.id,
                message_id=message.id,
                is_audio=opening_audio_ref is not None,
                audio_ref=opening_audio_ref,
                tip=None,
            )

        logger.info(
            "Conversation started: thread_id=%d track_id=%d mode=%s scenario=%r",
            thread.id, track_id, mode, scenario,
        )
        return ConversationStartRead(
            thread_id=thread.id,
            track_code=track.code,
            language_name=track.name,
            opening_text=opening_text,
            opening_audio_ref=opening_audio_ref,
            opening_audio_base64=opening_audio_base64,
        )

    async def _generate_opening(self, track_id: int, language_name: str, scenario: str, cefr_level: str) -> str:
        prompt = ROLEPLAY_OPENING_PROMPT.format(
            language_name=language_name,
            scenario=scenario,
            cefr_level=cefr_level,
            level_guidance=level_guidance(cefr_level, language_name),
        )
        return await self._run_opening_prompt(track_id, prompt)

    async def _generate_beginner_opening(
        self, track_id: int, language_name: str, cefr_level: str, topic: str | None
    ) -> str:
        topic_line = f"Topic: {topic}." if topic else "No set topic — keep it open-ended."
        prompt = CONVERSATION_OPENING_PROMPT.format(
            language_name=language_name,
            topic_line=topic_line,
            cefr_level=cefr_level,
            level_guidance=level_guidance(cefr_level, language_name),
        )
        return await self._run_opening_prompt(track_id, prompt)

    async def _run_opening_prompt(self, track_id: int, prompt: str) -> str:
        messages = [{"role": "user", "content": prompt}]
        t0 = time.monotonic()
        try:
            llm_response = await self._llm_provider.complete(messages)
        except Exception as exc:
            logger.error("Conversation: opener failed track_id=%d error=%s", track_id, exc)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Could not start the session. Please try again in a moment.",
            ) from exc
        latency_ms = int((time.monotonic() - t0) * 1000)
        opening_text = llm_response.text.strip()

        await create_llm_call(
            self._session,
            provider=self._llm_provider.provider,
            model=self._llm_provider.model,
            feature="conversation_start",
            prompt=messages,
            response=opening_text,
            tokens_input=llm_response.tokens_input,
            tokens_output=llm_response.tokens_output,
            latency_ms=latency_ms,
        )
        return opening_text

    def _turn_system_prompt(self, thread, track) -> str:
        language_name = track.name
        cefr_level = self._effective_level(thread.level_override, track)
        guidance = level_guidance(cefr_level, language_name)
        if thread.mode == "roleplay":
            return ROLEPLAY_TURN_PROMPT.format(
                language_name=language_name, scenario=thread.scenario,
                cefr_level=cefr_level, level_guidance=guidance,
            )
        topic_line = (
            f"Talk about: {thread.scenario}." if thread.scenario else "Talk about whatever comes up naturally."
        )
        return CONVERSATION_TURN_PROMPT.format(
            language_name=language_name, topic_line=topic_line,
            cefr_level=cefr_level, level_guidance=guidance,
        )

    async def _load_active_thread(self, thread_id: int):
        thread = await self._thread_repo.get_thread(thread_id)
        if thread is None or thread.ended_at is not None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="No active conversation session"
            )
        track = await self._track_repo.get_track(thread.track_id)
        if track is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Track not found")
        return thread, track

    async def record_audio_turn(self, thread_id: int, audio: bytes) -> ConversationTurnResultRead:
        thread, track = await self._load_active_thread(thread_id)
        history, system_prompt = await self._turn_context(thread, track)

        ogg_audio = await self._audio_converter.to_ogg_opus(audio)
        result = await self._generate_turn(
            thread_id,
            lambda: self._conversation_provider.reply_audio(history, ogg_audio, "audio/ogg", system_prompt),
            thread.mode,
            history,
            system_prompt,
            is_audio=True,
        )

        user_audio_ref = f"conversation/{uuid4()}.ogg"
        await self._audio_storage.save(ogg_audio, user_audio_ref)
        return await self._persist_turn(thread, track, result, is_audio=True, user_audio_ref=user_audio_ref)

    async def record_text_turn(self, thread_id: int, text: str) -> ConversationTurnResultRead:
        thread, track = await self._load_active_thread(thread_id)
        history, system_prompt = await self._turn_context(thread, track)

        result = await self._generate_turn(
            thread_id,
            lambda: self._conversation_provider.reply_text(history, text, system_prompt),
            thread.mode,
            history,
            system_prompt,
            is_audio=False,
        )
        return await self._persist_turn(thread, track, result, is_audio=False, user_audio_ref=None)

    async def _turn_context(self, thread, track) -> tuple[list[dict[str, str]], str]:
        turns = await self._thread_repo.get_turns_with_messages(thread.id)
        history = [{"role": message.role, "content": message.content} for _, message in turns]
        return history, self._turn_system_prompt(thread, track)

    async def _generate_turn(
        self,
        thread_id: int,
        call,
        mode: str,
        history: list[dict[str, str]],
        system_prompt: str,
        is_audio: bool,
    ) -> ConversationTurnResult:
        t0 = time.monotonic()
        try:
            result = await call()
        except Exception as exc:
            logger.error("Conversation: turn failed thread_id=%d mode=%s error=%s", thread_id, mode, exc)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="AI service temporarily unavailable. Please try again in a moment.",
            ) from exc
        latency_ms = int((time.monotonic() - t0) * 1000)

        await create_llm_call(
            self._session,
            provider=self._conversation_provider.provider,
            model=self._conversation_provider.model,
            feature=f"conversation_{mode}",
            prompt=[{"role": "system", "content": system_prompt}] + history,
            response=result.raw_response,
            tokens_input=result.tokens_input,
            tokens_output=result.tokens_output,
            latency_ms=latency_ms,
            is_audio=is_audio,
        )
        return result

    async def _persist_turn(
        self,
        thread,
        track,
        result: ConversationTurnResult,
        is_audio: bool,
        user_audio_ref: str | None,
    ) -> ConversationTurnResultRead:
        user_message = await self._message_service.create(
            MessageCreate(
                session_id=thread.chat_session_id,
                role="user",
                content=result.transcript,
                meta={"conversation_thread_id": thread.id, "is_audio": is_audio},
            )
        )
        await self._thread_repo.create_turn(
            thread_id=thread.id,
            message_id=user_message.id,
            is_audio=is_audio,
            audio_ref=user_audio_ref,
            tip=result.tip,
        )

        reply_audio: bytes | None = None
        reply_audio_ref: str | None = None
        if thread.voice_reply:
            reply_audio, reply_audio_ref = await self._synthesize_and_save(
                result.reply, track.code, result.tone
            )

        assistant_message = await self._message_service.create(
            MessageCreate(
                session_id=thread.chat_session_id,
                role="assistant",
                content=result.reply,
                meta={"conversation_thread_id": thread.id},
            )
        )
        await self._thread_repo.create_turn(
            thread_id=thread.id,
            message_id=assistant_message.id,
            is_audio=reply_audio_ref is not None,
            audio_ref=reply_audio_ref,
            tip=None,
        )

        logger.info(
            "Conversation turn recorded: thread_id=%d mode=%s is_audio=%s tip=%s",
            thread.id, thread.mode, is_audio, bool(result.tip),
        )
        return ConversationTurnResultRead(
            response=result.reply,
            reply_audio_base64=base64.b64encode(reply_audio).decode("ascii") if reply_audio else None,
            tip=result.tip,
        )

    def _summary_prompt(self, thread, language_name: str, transcript: str, tips: list[str]) -> str:
        """End-of-session coaching feedback — generated for both modes."""
        common = {
            "language_name": language_name,
            "transcript": transcript or "(no turns recorded)",
            "tips": "\n".join(f"- {t}" for t in tips) if tips else "(none)",
        }
        if thread.mode == "roleplay":
            return ROLEPLAY_SUMMARY_PROMPT.format(scenario=thread.scenario, **common)
        topic_line = f"Topic: {thread.scenario}" if thread.scenario else "No set topic."
        return CONVERSATION_SUMMARY_PROMPT.format(topic_line=topic_line, **common)

    async def end(self, thread_id: int) -> ConversationEndRead:
        thread = await self._thread_repo.get_thread(thread_id)
        if thread is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation thread not found")

        track = await self._track_repo.get_track(thread.track_id)
        language_name = track.name if track else "the target language"

        # Every turn — text or audio, either mode — is a tracked ConversationTurn, so the
        # thread's own turns are the complete record of the session.
        turns = await self._thread_repo.get_turns_with_messages(thread_id)
        tips = [turn.tip for turn, _ in turns if turn.tip]
        transcript = "\n".join(f"{message.role}: {message.content}" for _, message in turns)
        turn_count = sum(1 for _, message in turns if message.role == "user")

        tip: str | None = None
        candidates: list[NewVocabularyCandidate] = []
        if turns:
            prompt = self._summary_prompt(thread, language_name, transcript, tips)
            messages = [{"role": "user", "content": prompt}]
            t0 = time.monotonic()
            try:
                llm_response = await self._llm_provider.complete(messages)
            except Exception:
                logger.error("Conversation: summary generation failed thread_id=%d", thread_id, exc_info=True)
            else:
                latency_ms = int((time.monotonic() - t0) * 1000)
                await create_llm_call(
                    self._session,
                    provider=self._llm_provider.provider,
                    model=self._llm_provider.model,
                    feature="conversation_summary",
                    prompt=messages,
                    response=llm_response.text,
                    tokens_input=llm_response.tokens_input,
                    tokens_output=llm_response.tokens_output,
                    latency_ms=latency_ms,
                )
                try:
                    tip, candidates = _parse_summary_json(llm_response.text)
                except (json.JSONDecodeError, ValueError, TypeError):
                    logger.error(
                        "Conversation: summary JSON unparseable thread_id=%d", thread_id, exc_info=True
                    )
                if not tip:
                    tip = llm_response.text.strip()

        await self._thread_repo.end_thread(thread_id, tip)
        await self._language_session_service.record_session(
            SessionCreate(track_id=thread.track_id, session_type="correction", transcript_or_notes=tip)
        )
        if candidates:
            await self._chunk_service.queue_vocabulary_candidates(
                thread.track_id, candidates, max_candidates=_MAX_VOCABULARY_CANDIDATES
            )

        logger.info(
            "Conversation ended: thread_id=%d turns=%d has_tip=%s vocab_candidates=%d",
            thread_id, turn_count, bool(tip), len(candidates),
        )
        return ConversationEndRead(tip=tip, turn_count=turn_count)
