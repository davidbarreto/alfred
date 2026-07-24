from __future__ import annotations

import base64
import logging
import time
from uuid import uuid4

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.core.messages.schemas import MessageCreate
from app.features.core.messages.service import MessageService
from app.features.language.chunks.pronunciation_service import PronunciationService
from app.features.language.conversation.prompts import (
    ROLEPLAY_OPENING_PROMPT,
    ROLEPLAY_SUMMARY_PROMPT,
    ROLEPLAY_TURN_PROMPT,
)
from app.features.language.conversation.repository import ConversationRepository
from app.features.language.conversation.schemas import (
    ConversationEndRead,
    ConversationStartRead,
    ConversationTurnResultRead,
)
from app.features.language.sessions.schemas import SessionCreate
from app.features.language.sessions.service import SessionService as LanguageSessionService
from app.features.language.tracks.repository import TrackRepository
from app.integrations.llm_calls.repository import create_llm_call
from app.shared.audio import AudioConversationProvider, AudioConverter, FileStorage
from app.shared.llm import LlmProvider

logger = logging.getLogger(__name__)


class ConversationService:
    """Roleplay conversation practice: scoped thread → turn-by-turn → wrap-up summary.

    Free conversation (mode="conversation") does NOT use this service — it rides the
    normal chat pipeline via ChatService.chat_with_audio instead (see chats/service.py)."""

    def __init__(
        self,
        session: AsyncSession,
        thread_repo: ConversationRepository,
        message_service: MessageService,
        language_session_service: LanguageSessionService,
        track_repo: TrackRepository,
        audio_storage: FileStorage,
        audio_converter: AudioConverter,
        conversation_provider: AudioConversationProvider,
        pronunciation_service: PronunciationService,
        llm_provider: LlmProvider,
    ) -> None:
        self._session = session
        self._thread_repo = thread_repo
        self._message_service = message_service
        self._language_session_service = language_session_service
        self._track_repo = track_repo
        self._audio_storage = audio_storage
        self._audio_converter = audio_converter
        self._conversation_provider = conversation_provider
        self._pronunciation_service = pronunciation_service
        self._llm_provider = llm_provider

    async def get_turn_audio_ref(self, turn_id: int) -> str | None:
        turn = await self._thread_repo.get_turn(turn_id)
        return turn.audio_ref if turn else None

    async def _synthesize_and_save(self, text: str, track_code: str) -> tuple[bytes, str]:
        audio, _ = await self._pronunciation_service.get_audio(text, track_code, audio_format="ogg")
        audio_ref = f"conversation/{uuid4()}.ogg"
        await self._audio_storage.save(audio, audio_ref)
        return audio, audio_ref

    async def start(
        self, track_id: int, message_id: int, scenario: str, voice_reply: bool
    ) -> ConversationStartRead:
        track = await self._track_repo.get_track(track_id)
        if track is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Track not found")

        origin_message = await self._message_service.get(message_id)
        if origin_message is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found")
        chat_session_id = origin_message.session_id

        thread = await self._thread_repo.create_thread(track_id, chat_session_id, scenario, voice_reply)

        prompt = ROLEPLAY_OPENING_PROMPT.format(language_name=track.name, scenario=scenario)
        messages = [{"role": "user", "content": prompt}]
        t0 = time.monotonic()
        try:
            llm_response = await self._llm_provider.complete(messages)
        except Exception as exc:
            logger.error("Conversation: roleplay opener failed track_id=%d error=%s", track_id, exc)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Could not start the roleplay. Please try again in a moment.",
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

        message = await self._message_service.create(
            MessageCreate(
                session_id=chat_session_id,
                role="assistant",
                content=opening_text,
                meta={"conversation_thread_id": thread.id},
            )
        )

        opening_audio_ref: str | None = None
        if voice_reply:
            _, opening_audio_ref = await self._synthesize_and_save(opening_text, track.code)

        await self._thread_repo.create_turn(
            thread_id=thread.id, message_id=message.id, is_audio=False, audio_ref=opening_audio_ref, tip=None
        )

        logger.info(
            "Conversation started: thread_id=%d track_id=%d scenario=%r", thread.id, track_id, scenario
        )
        return ConversationStartRead(
            thread_id=thread.id,
            track_code=track.code,
            language_name=track.name,
            opening_text=opening_text,
            opening_audio_ref=opening_audio_ref,
        )

    async def record_audio_turn(self, thread_id: int, audio: bytes) -> ConversationTurnResultRead:
        thread = await self._thread_repo.get_thread(thread_id)
        if thread is None or thread.ended_at is not None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No active roleplay session")

        track = await self._track_repo.get_track(thread.track_id)
        if track is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Track not found")

        turns = await self._thread_repo.get_turns_with_messages(thread_id)
        history = [{"role": message.role, "content": message.content} for _, message in turns]

        ogg_audio = await self._audio_converter.to_ogg_opus(audio)
        system_prompt = ROLEPLAY_TURN_PROMPT.format(language_name=track.name, scenario=thread.scenario)

        t0 = time.monotonic()
        try:
            result = await self._conversation_provider.reply(history, ogg_audio, "audio/ogg", system_prompt)
        except Exception as exc:
            logger.error("Conversation: roleplay turn failed thread_id=%d error=%s", thread_id, exc)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="AI service temporarily unavailable. Please try again in a moment.",
            ) from exc
        latency_ms = int((time.monotonic() - t0) * 1000)

        await create_llm_call(
            self._session,
            provider=self._conversation_provider.provider,
            model=self._conversation_provider.model,
            feature="conversation_roleplay",
            prompt=[{"role": "system", "content": system_prompt}] + history,
            response=result.raw_response,
            tokens_input=result.tokens_input,
            tokens_output=result.tokens_output,
            latency_ms=latency_ms,
            is_audio=True,
        )

        user_audio_ref = f"conversation/{uuid4()}.ogg"
        await self._audio_storage.save(ogg_audio, user_audio_ref)

        user_message = await self._message_service.create(
            MessageCreate(
                session_id=thread.chat_session_id,
                role="user",
                content=result.transcript,
                meta={"conversation_thread_id": thread_id, "is_audio": True},
            )
        )
        await self._thread_repo.create_turn(
            thread_id=thread_id,
            message_id=user_message.id,
            is_audio=True,
            audio_ref=user_audio_ref,
            tip=result.tip,
        )

        reply_audio: bytes | None = None
        reply_audio_ref: str | None = None
        if thread.voice_reply:
            reply_audio, reply_audio_ref = await self._synthesize_and_save(result.reply, track.code)

        assistant_message = await self._message_service.create(
            MessageCreate(
                session_id=thread.chat_session_id,
                role="assistant",
                content=result.reply,
                meta={"conversation_thread_id": thread_id},
            )
        )
        await self._thread_repo.create_turn(
            thread_id=thread_id,
            message_id=assistant_message.id,
            is_audio=bool(thread.voice_reply),
            audio_ref=reply_audio_ref,
            tip=None,
        )

        logger.info("Conversation turn recorded: thread_id=%d tip=%s", thread_id, bool(result.tip))
        return ConversationTurnResultRead(
            response=result.reply,
            reply_audio_base64=base64.b64encode(reply_audio).decode("ascii") if reply_audio else None,
            tip=result.tip,
        )

    async def end(self, thread_id: int) -> ConversationEndRead:
        thread = await self._thread_repo.get_thread(thread_id)
        if thread is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation thread not found")

        track = await self._track_repo.get_track(thread.track_id)
        language_name = track.name if track else "the target language"

        turns = await self._thread_repo.get_turns_with_messages(thread_id)
        transcript = "\n".join(f"{message.role}: {message.content}" for _, message in turns)
        tips = [turn.tip for turn, _ in turns if turn.tip]

        tip: str | None = None
        if turns:
            prompt = ROLEPLAY_SUMMARY_PROMPT.format(
                language_name=language_name,
                scenario=thread.scenario,
                transcript=transcript or "(no turns recorded)",
                tips="\n".join(f"- {t}" for t in tips) if tips else "(none)",
            )
            messages = [{"role": "user", "content": prompt}]
            t0 = time.monotonic()
            try:
                llm_response = await self._llm_provider.complete(messages)
                tip = llm_response.text.strip()
                latency_ms = int((time.monotonic() - t0) * 1000)
                await create_llm_call(
                    self._session,
                    provider=self._llm_provider.provider,
                    model=self._llm_provider.model,
                    feature="conversation_summary",
                    prompt=messages,
                    response=tip,
                    tokens_input=llm_response.tokens_input,
                    tokens_output=llm_response.tokens_output,
                    latency_ms=latency_ms,
                )
            except Exception:
                logger.error("Conversation: summary generation failed thread_id=%d", thread_id, exc_info=True)
                tip = None

        await self._thread_repo.end_thread(thread_id, tip)
        await self._language_session_service.record_session(
            SessionCreate(track_id=thread.track_id, session_type="correction", transcript_or_notes=tip)
        )

        logger.info("Conversation ended: thread_id=%d turns=%d has_tip=%s", thread_id, len(turns), bool(tip))
        return ConversationEndRead(tip=tip, turn_count=len(turns))
