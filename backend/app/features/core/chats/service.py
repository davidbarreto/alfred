from __future__ import annotations

import asyncio
import json
import logging
import pathlib
import re
import time
from datetime import datetime, timezone
from typing import AsyncGenerator

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

from app.features.core.chats.context import build_daily_context
from app.features.core.chats.schemas import ChatRequest
from app.features.core.prompts import (
    CHAT_COMMAND_BOUNDARY_INSTRUCTIONS,
    CHAT_FOCUS_INSTRUCTIONS,
    CHAT_FORMATTING_INSTRUCTIONS,
    CHAT_LANGUAGE_INSTRUCTIONS,
    CONVERSATION_TURN_PROMPT,
)
from app.features.core.embeddings.schemas import EmbeddingSearchRequest, EmbeddingSearchResult
from app.features.core.embeddings.service import EmbeddingService
from app.features.core.memories.extraction_service import MemoryExtractionService
from app.features.core.messages.schemas import MessageCreate, MessageFilters, MessageRead
from app.features.core.messages.service import MessageService
from app.features.core.sessions.repository import SessionRepository
from app.features.core.sessions.service import SessionService
from app.features.core.sessions.summary_service import SessionSummaryService
from app.features.core.working_memory.schemas import WorkingMemoryCreate, WorkingMemoryFilters, WorkingMemoryRead
from app.features.core.working_memory.service import WorkingMemoryService
from app.features.language.chunks.pronunciation_service import PronunciationService
from app.features.language.chunks.service import ChunkService
from app.features.language.production.schemas import CHUNKLESS_TASK_TYPES, ProductionAttemptCreate
from app.features.language.production.service import ProductionService
from app.features.language.sessions.repository import SessionRepository as LanguageSessionRepository
from app.features.language.sessions.schemas import NextPracticePrompt
from app.features.language.sessions.schemas import SessionFilters as LanguageSessionFilters
from app.features.language.sessions.tables import LearningSession
from app.integrations.llm_calls.repository import create_llm_call
from app.shared.audio import AudioConversationProvider, AudioConverter
from app.shared.llm import LlmProvider, StreamMeta

_LANGUAGE_PENDING_KEY = "language:pending"

_PERSONA_PATH = pathlib.Path(__file__).parents[3] / "assistant" / "persona.md"
_HISTORY_LIMIT = 10
_MEMORY_LIMIT = 5
_MEMORY_THRESHOLD = 0.6


def _is_language_command(detected_intents: list[str] | None) -> bool:
    return bool(detected_intents) and any(intent.startswith("language.") for intent in detected_intents)


def _load_persona() -> str:
    try:
        return _PERSONA_PATH.read_text(encoding="utf-8")
    except FileNotFoundError:
        return "You are Alfred, a helpful personal AI assistant."



def _build_system_prompt(
    memories: list[EmbeddingSearchResult],
    detected_intents: list[str] | None = None,
    recent_summaries: list[tuple[datetime, str]] | None = None,
    daily_context: str = "",
    working_memories: list[WorkingMemoryRead] | None = None,
    language_session: LearningSession | None = None,
    production_section: str | None = None,
) -> str:
    now = datetime.now(tz=timezone.utc).strftime("%A, %B %d, %Y at %H:%M UTC")
    parts = []

    if detected_intents:
        intent_list = ", ".join(detected_intents)
        parts.append(
            f"## Parallel command pipeline\n"
            f"The system is already handling these commands automatically: {intent_list}.\n"
            f"For those commands: acknowledge in one short sentence only "
            f"(e.g. 'On it!' or 'Got it, I will get that added.'). "
            f"Do NOT generate content, descriptions, templates, or details for them — "
            f"a separate message will follow with the actual result. "
            f"If the message contains other conversational parts unrelated to those commands, respond to those normally."
        )

    parts += [
        _load_persona(),
        f"## Current date and time\nNow is {now}.",
        CHAT_FORMATTING_INSTRUCTIONS,
        CHAT_LANGUAGE_INSTRUCTIONS,
        CHAT_FOCUS_INSTRUCTIONS,
    ]

    if not detected_intents:
        parts.append(CHAT_COMMAND_BOUNDARY_INSTRUCTIONS)

    if daily_context:
        parts.append(daily_context)

    if recent_summaries:
        lines = "\n".join(
            f"{ts.strftime('%B %d, %Y')}: {summary}"
            for ts, summary in recent_summaries
        )
        parts.append(f"## Recent conversations\n{lines}")

    visible_memories = [wm for wm in (working_memories or []) if not wm.key.startswith("reminder:")]
    if visible_memories:
        lines = "\n".join(f"- {wm.key}: {wm.value}" for wm in visible_memories)
        section = f"## Active context\n{lines}"
        pending_wm = next((wm for wm in visible_memories if wm.key == _LANGUAGE_PENDING_KEY), None)
        if pending_wm:
            try:
                pending_data = json.loads(pending_wm.value)
                mode = pending_data.get("mode", "practice")
            except (json.JSONDecodeError, AttributeError):
                mode = "practice"

            if mode == "practice":
                if language_session and language_session.quality_score is not None:
                    fb = language_session.ai_feedback_json or {}
                    score_line = f"Score: {language_session.quality_score:.0f}/100"
                    detail_lines = [score_line]
                    if fb.get("summary"):
                        detail_lines.append(f"Summary: {fb['summary']}")
                    if fb.get("strengths"):
                        detail_lines.append(f"Strengths: {'; '.join(fb['strengths'])}")
                    if fb.get("issues"):
                        detail_lines.append(f"Issues: {'; '.join(fb['issues'])}")
                    if fb.get("tip"):
                        detail_lines.append(f"Tip: {fb['tip']}")
                    section += "\n\n## Practice result\n" + "\n".join(detail_lines)
                    section += "\n\nRespond as an encouraging coach. Keep it brief (2–3 sentences)."
                else:
                    section += (
                        "\n\nThe user just submitted a language practice attempt. "
                        "Their message is a transcription of what they said. "
                        "Respond briefly as an encouraging coach."
                    )
            elif mode == "review":
                section += (
                    "\n\nThe user is doing a vocabulary review. "
                    "The word was shown to them and they are responding with whether they know it. "
                    "Acknowledge their response briefly and encourage them to keep going."
                )
        parts.append(section)

    if production_section:
        parts.append(production_section)

    if memories:
        lines = "\n".join(f"- [{m.source_type}] {m.content}" for m in memories)
        parts.append(f"## Relevant context from memory\n{lines}")

    return "\n\n".join(parts)


_MD_PATTERNS = [
    (re.compile(r"\*\*(.+?)\*\*", re.DOTALL), r"\1"),   # **bold**
    (re.compile(r"\*(.+?)\*", re.DOTALL), r"\1"),        # *italic*
    (re.compile(r"__(.+?)__", re.DOTALL), r"\1"),        # __bold__
    (re.compile(r"_(.+?)_", re.DOTALL), r"\1"),          # _italic_
    (re.compile(r"```.*?```", re.DOTALL), r""),           # ```code block```
    (re.compile(r"`(.+?)`"), r"\1"),                      # `inline code`
    (re.compile(r"^#{1,6}\s+", re.MULTILINE), r""),      # ## headings
    (re.compile(r"^\s*[-*]\s+", re.MULTILINE), r"- "),   # normalise bullet points
]


def _strip_markdown(text: str) -> str:
    for pattern, replacement in _MD_PATTERNS:
        text = pattern.sub(replacement, text)
    return text.strip()


def _to_message_dicts(messages: list[MessageRead]) -> list[dict[str, str]]:
    return [{"role": msg.role, "content": msg.content} for msg in messages]


class ChatService:
    def __init__(
        self,
        session: AsyncSession,
        llm_provider: LlmProvider,
        embedding_service: EmbeddingService,
        message_service: MessageService,
        memory_extraction_service: MemoryExtractionService,
        session_summary_service: SessionSummaryService,
        working_memory_service: WorkingMemoryService,
        chunk_service: ChunkService,
        production_service: ProductionService,
        audio_converter: AudioConverter,
        conversation_provider: AudioConversationProvider,
        pronunciation_service: PronunciationService,
    ) -> None:
        self._session = session
        self._llm_provider = llm_provider
        self._embedding_service = embedding_service
        self._message_service = message_service
        self._memory_extraction_service = memory_extraction_service
        self._session_summary_service = session_summary_service
        self._working_memory_service = working_memory_service
        self._chunk_service = chunk_service
        self._production_service = production_service
        self._audio_converter = audio_converter
        self._conversation_provider = conversation_provider
        self._pronunciation_service = pronunciation_service

    async def _fetch_history(self, session_id: int) -> list[MessageRead]:
        session = await SessionRepository(self._session).get(session_id)
        if session and session.source and session.external_id:
            return await self._message_service.list(
                MessageFilters(source=session.source, external_id=session.external_id, limit=_HISTORY_LIMIT + 1)
            )
        return await self._message_service.list(
            MessageFilters(session_id=session_id, limit=_HISTORY_LIMIT + 1)
        )

    async def _advance_language_loop(self, pending_wm: WorkingMemoryRead) -> NextPracticePrompt | None:
        """Decrement the pending practice/review loop and either move it to the next due
        chunk or end it. Must run after the coaching reply is generated — the WM still has
        to point at the just-completed chunk while `chat()` builds that reply."""
        try:
            data = json.loads(pending_wm.value)
        except (json.JSONDecodeError, AttributeError):
            await self._working_memory_service.delete(pending_wm.id)
            return None

        remaining = int(data.get("remaining", 1)) - 1
        next_chunk = None
        if remaining > 0:
            batches = await self._chunk_service.get_daily_batch(data.get("track_id"))
            due = [c for batch in batches for c in batch.chunks if c.id != data.get("chunk_id")]
            if due:
                next_chunk = due[0]

        await self._working_memory_service.delete(pending_wm.id)

        if next_chunk is None:
            logger.info("Chat: language loop ended wm_id=%d remaining=%d", pending_wm.id, max(remaining, 0))
            return None

        new_data = {
            **data,
            "chunk_id": next_chunk.id,
            "text": next_chunk.text,
            "translation": next_chunk.translation,
            "remaining": remaining,
        }
        await self._working_memory_service.create(WorkingMemoryCreate(
            key=_LANGUAGE_PENDING_KEY, value=json.dumps(new_data), importance=1.0,
        ))
        logger.info(
            "Chat: language loop advanced wm_id=%d next_chunk_id=%d remaining=%d",
            pending_wm.id, next_chunk.id, remaining,
        )
        return NextPracticePrompt(
            mode=data.get("mode", "practice"),
            track_id=data["track_id"],
            track_code=data.get("track_code", ""),
            chunk_id=next_chunk.id,
            text=next_chunk.text,
            translation=next_chunk.translation,
            language_name=data.get("language_name", ""),
            remaining=remaining,
        )

    async def _handle_production_turn(
        self,
        pending_wm: WorkingMemoryRead,
        data: dict,
        user_text: str,
        advance: bool = True,
    ) -> str:
        """Grade a pending production attempt, advance the loop, and return the system-prompt
        section describing the result. Must run before the coaching reply is generated —
        the reply has to contain the grading feedback and, when the loop continues, the next
        exercise (the caller returns no next_practice for produce mode)."""
        try:
            attempt = await self._production_service.grade_attempt(ProductionAttemptCreate(
                track_id=data["track_id"],
                chunk_id=data.get("chunk_id"),
                task_type=data.get("task_type", "sentence"),
                prompt_text=data.get("prompt_text", ""),
                response_text=user_text,
            ))
        except (HTTPException, KeyError) as exc:
            logger.error("Chat: production grading failed wm_id=%d error=%s", pending_wm.id, exc)
            return (
                "## Production practice\nThe user submitted a production exercise answer but "
                "grading is temporarily unavailable. Apologize briefly and ask them to send "
                "their answer again."
            )

        next_task = None
        remaining = int(data.get("remaining", 1)) - 1
        if advance:
            if remaining > 0:
                # Chunk-less loops (journal, timed, speak, retell) keep their task type;
                # anchored loops keep rotating sentence/translate via the service default.
                loop_type = data.get("task_type")
                next_task = await self._production_service.get_next_task(
                    data["track_id"],
                    task_type=loop_type if loop_type in CHUNKLESS_TASK_TYPES else None,
                    exclude_chunk_id=data.get("chunk_id"),
                )
            await self._working_memory_service.delete(pending_wm.id)
            if next_task is not None:
                await self._working_memory_service.create(WorkingMemoryCreate(
                    key=_LANGUAGE_PENDING_KEY,
                    value=json.dumps({
                        "mode": "produce",
                        "chunk_id": next_task.chunk_id,
                        "track_id": next_task.track_id,
                        "track_code": next_task.track_code,
                        "language_name": next_task.language_name,
                        "text": next_task.text,
                        "translation": next_task.translation,
                        "task_type": next_task.task_type,
                        "prompt_text": next_task.prompt_text,
                        "time_limit_seconds": next_task.time_limit_seconds,
                        "remaining": remaining,
                    }),
                    importance=1.0,
                ))
                logger.info(
                    "Chat: production loop advanced wm_id=%d next_chunk_id=%s remaining=%d",
                    pending_wm.id, next_task.chunk_id, remaining,
                )
            else:
                logger.info("Chat: production loop ended wm_id=%d", pending_wm.id)

        grading = attempt.grading
        detail_lines = [f"Score: {grading.score:.0f}/100"]
        if grading.errors:
            detail_lines.append("Errors: " + "; ".join(grading.errors))
        if grading.corrected_text:
            detail_lines.append(f"Corrected version: {grading.corrected_text}")
        if grading.feedback:
            detail_lines.append(f"Feedback: {grading.feedback}")

        section = "## Production result\n" + "\n".join(detail_lines)
        section += (
            "\n\nRespond as an encouraging coach: give the score, the corrected version if it "
            "differs from their answer, and one short tip. Keep it brief (2-3 sentences)."
        )
        if next_task is not None:
            section += (
                f"\n\nThen present the next exercise exactly as written, on its own line "
                f"({remaining} left after this one is answered):\n{next_task.prompt_text}"
            )
        elif advance:
            section += "\n\nThat was the last exercise — close the session with one short encouraging line."
        return section

    async def chat(self, request: ChatRequest) -> tuple[str, NextPracticePrompt | None]:
        logger.info("Chat: session_id=%s", request.session_id)
        messages = await self._fetch_history(request.session_id)
        if not messages:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="No messages found in session. Call POST /core/messages first.",
            )

        current_message = messages[-1]
        history = _to_message_dicts(messages[:-1])

        working_memories = await self._working_memory_service.list(WorkingMemoryFilters(active_only=True))
        logger.debug("Chat: %d active working memory entries loaded", len(working_memories))

        language_session: LearningSession | None = None
        production_section: str | None = None
        pending_mode: str | None = None
        pending_wm = next((wm for wm in working_memories if wm.key == _LANGUAGE_PENDING_KEY), None)
        if pending_wm and _is_language_command(request.detected_intents):
            # The message is itself a language command (e.g. /stop, /produce) running through
            # the parallel command pipeline, not a free-text answer to the pending exercise —
            # grading/advancing the loop here would present a bogus extra exercise.
            logger.debug(
                "Chat: message is a language command (%s) — not treating as exercise answer",
                request.detected_intents,
            )
            pending_wm = None
        if pending_wm:
            logger.debug("Chat: language pending mode — skipping embeddings, summaries, daily context")
            memories, recent_summaries, daily_context = [], [], ""
            try:
                pending_data = json.loads(pending_wm.value)
                pending_mode = pending_data.get("mode", "practice")
                if pending_mode == "practice":
                    chunk_id = pending_data.get("chunk_id")
                    if chunk_id:
                        lang_sessions = await LanguageSessionRepository(self._session).get_sessions(
                            LanguageSessionFilters(chunk_id=chunk_id, session_type="shadowing", limit=1)
                        )
                        language_session = lang_sessions[0] if lang_sessions else None
                        if language_session:
                            logger.debug(
                                "Chat: practice session loaded: id=%d score=%s",
                                language_session.id, language_session.quality_score,
                            )
                elif pending_mode == "produce":
                    production_section = await self._handle_production_turn(
                        pending_wm, pending_data, current_message.content
                    )
            except (json.JSONDecodeError, KeyError):
                logger.warning("Chat: failed to parse pending WM value=%r", pending_wm.value)
        else:
            memories = await self._embedding_service.search(
                EmbeddingSearchRequest(
                    query=current_message.content,
                    source_types=["memory", "note", "task"],
                    limit=_MEMORY_LIMIT,
                    threshold=_MEMORY_THRESHOLD,
                )
            )
            logger.debug("Chat: %d memory items retrieved", len(memories))
            recent_summaries = await self._session_summary_service.get_recent_summaries(request.session_id)
            logger.debug("Chat: %d recent session summaries loaded", len(recent_summaries))
            daily_context = await build_daily_context(self._session)

        system_prompt = _build_system_prompt(memories, request.detected_intents, recent_summaries, daily_context, working_memories, language_session, production_section)
        messages = history + [{"role": "user", "content": current_message.content}]

        t0 = time.monotonic()
        try:
            llm_response = await self._llm_provider.complete(messages, system=system_prompt)
        except Exception as exc:
            logger.error("Chat: LLM call failed session_id=%s error=%s", request.session_id, exc)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="AI service temporarily unavailable. Please try again in a moment.",
            ) from exc
        latency_ms = int((time.monotonic() - t0) * 1000)

        response_text = _strip_markdown(llm_response.text)

        logger.info(
            "Chat: LLM response session_id=%s latency_ms=%d tokens_in=%s tokens_out=%s",
            request.session_id, latency_ms, llm_response.tokens_input, llm_response.tokens_output,
        )

        await create_llm_call(
            self._session,
            provider=self._llm_provider.provider,
            model=self._llm_provider.model,
            feature="chat",
            prompt=[{"role": "system", "content": system_prompt}] + messages,
            response=response_text,
            tokens_input=llm_response.tokens_input,
            tokens_output=llm_response.tokens_output,
            latency_ms=latency_ms,
            finish_reason=llm_response.finish_reason,
        )

        await self._message_service.create(
            MessageCreate(session_id=request.session_id, role="assistant", content=response_text)
        )

        next_practice: NextPracticePrompt | None = None
        if pending_wm and pending_mode != "produce":
            # Produce loops advance inside _handle_production_turn; the coaching reply
            # already carries the next exercise, so there is no next_practice to emit.
            next_practice = await self._advance_language_loop(pending_wm)

        if pending_wm is None:
            asyncio.create_task(
                self._memory_extraction_service.extract_and_save(
                    user_message=current_message.content,
                    message_id=current_message.id,
                )
            )
        else:
            # Exercise answers (practice/review/produce) are drill content, not facts
            # about the user — never mine them for memories.
            logger.debug("Chat: language pending mode — skipping memory extraction")

        return response_text, next_practice

    async def chat_with_audio(
        self, source: str, external_id: str, audio: bytes, mime_type: str
    ) -> tuple[str, bytes | None]:
        """Free-conversation turn (mode="conversation"): Gemini receives the user's raw
        audio directly instead of a transcript. Structurally this is normal chat — same
        session/messages/llm_calls(feature="chat") — just audio-native input."""
        logger.info("ChatAudio: source=%s external_id=%s", source, external_id)
        session, _ = await SessionService(self._session).get_or_create_active(source, external_id)

        working_memories = await self._working_memory_service.list(WorkingMemoryFilters(active_only=True))
        pending_wm = next((wm for wm in working_memories if wm.key == _LANGUAGE_PENDING_KEY), None)
        pending_data: dict = {}
        if pending_wm:
            try:
                pending_data = json.loads(pending_wm.value)
            except (json.JSONDecodeError, AttributeError):
                pending_data = {}
        if pending_data.get("mode") != "conversation":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No active free-conversation session",
            )

        history = _to_message_dicts(await self._fetch_history(session.id))
        ogg_audio = await self._audio_converter.to_ogg_opus(audio)

        language_name = pending_data.get("language_name") or "the target language"
        topic = pending_data.get("topic")
        topic_line = f"Talk about: {topic}." if topic else "Talk about whatever comes up naturally."
        system_prompt = CONVERSATION_TURN_PROMPT.format(language_name=language_name, topic_line=topic_line)

        t0 = time.monotonic()
        try:
            result = await self._conversation_provider.reply(history, ogg_audio, "audio/ogg", system_prompt)
        except Exception as exc:
            logger.error("ChatAudio: conversation LLM call failed session_id=%d error=%s", session.id, exc)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="AI service temporarily unavailable. Please try again in a moment.",
            ) from exc
        latency_ms = int((time.monotonic() - t0) * 1000)

        await create_llm_call(
            self._session,
            provider=self._conversation_provider.provider,
            model=self._conversation_provider.model,
            feature="chat",
            prompt=[{"role": "system", "content": system_prompt}] + history,
            response=result.raw_response,
            tokens_input=result.tokens_input,
            tokens_output=result.tokens_output,
            latency_ms=latency_ms,
            is_audio=True,
        )

        await self._message_service.create(
            MessageCreate(
                session_id=session.id, role="user", content=result.transcript, meta={"is_audio": True}
            )
        )
        await self._message_service.create(
            MessageCreate(session_id=session.id, role="assistant", content=result.reply)
        )
        logger.info(
            "ChatAudio: reply generated session_id=%d transcript_chars=%d",
            session.id, len(result.transcript),
        )

        reply_audio: bytes | None = None
        if pending_data.get("voice_reply"):
            track_code = pending_data.get("track_code") or "en"
            try:
                reply_audio, _ = await self._pronunciation_service.get_audio(
                    result.reply, track_code, audio_format="ogg"
                )
            except Exception:
                logger.error("ChatAudio: TTS synthesis failed session_id=%d", session.id, exc_info=True)

        return result.reply, reply_audio

    async def stream_chat(self, request: ChatRequest) -> AsyncGenerator[str, None]:
        logger.info("StreamChat: session_id=%s", request.session_id)
        messages = await self._fetch_history(request.session_id)
        if not messages:
            yield f"[error: No messages found in session. Call POST /core/messages first.]"
            return

        current_message = messages[-1]
        history = _to_message_dicts(messages[:-1])

        working_memories = await self._working_memory_service.list(WorkingMemoryFilters(active_only=True))

        language_session: LearningSession | None = None
        production_section: str | None = None
        pending_wm = next((wm for wm in working_memories if wm.key == _LANGUAGE_PENDING_KEY), None)
        if pending_wm and _is_language_command(request.detected_intents):
            logger.debug(
                "StreamChat: message is a language command (%s) — not treating as exercise answer",
                request.detected_intents,
            )
            pending_wm = None
        if pending_wm:
            memories, recent_summaries, daily_context = [], [], ""
            try:
                pending_data = json.loads(pending_wm.value)
                pending_mode = pending_data.get("mode", "practice")
                if pending_mode == "practice":
                    chunk_id = pending_data.get("chunk_id")
                    if chunk_id:
                        lang_sessions = await LanguageSessionRepository(self._session).get_sessions(
                            LanguageSessionFilters(chunk_id=chunk_id, session_type="shadowing", limit=1)
                        )
                        language_session = lang_sessions[0] if lang_sessions else None
                elif pending_mode == "produce":
                    # Streaming does not drive the loop (the pending WM is cleared below),
                    # so grade without advancing.
                    production_section = await self._handle_production_turn(
                        pending_wm, pending_data, current_message.content, advance=False
                    )
            except (json.JSONDecodeError, KeyError):
                logger.warning("StreamChat: failed to parse pending WM value=%r", pending_wm.value)
        else:
            memories = await self._embedding_service.search(
                EmbeddingSearchRequest(
                    query=current_message.content,
                    source_types=["memory", "note", "task"],
                    limit=_MEMORY_LIMIT,
                    threshold=_MEMORY_THRESHOLD,
                )
            )
            recent_summaries = await self._session_summary_service.get_recent_summaries(request.session_id)
            daily_context = await build_daily_context(self._session)

        system_prompt = _build_system_prompt(memories, request.detected_intents, recent_summaries, daily_context, working_memories, language_session, production_section)
        messages_list = history + [{"role": "user", "content": current_message.content}]

        t0 = time.monotonic()
        raw_text = ""
        meta = StreamMeta()
        try:
            async for chunk in self._llm_provider.stream(messages_list, system=system_prompt, meta=meta):
                raw_text += chunk
                yield chunk
        except Exception as exc:
            logger.error("StreamChat: LLM stream failed session_id=%s error=%s", request.session_id, exc)
            yield "[error: AI service temporarily unavailable.]"
            return

        if meta.truncated:
            logger.warning(
                "StreamChat: truncated response session_id=%s finish_reason=%s",
                request.session_id, meta.finish_reason,
            )
            notice = "\n\n[My response was cut short. Ask me to continue!]"
            raw_text += notice
            yield notice

        latency_ms = int((time.monotonic() - t0) * 1000)
        response_text = _strip_markdown(raw_text)

        logger.info(
            "StreamChat: done session_id=%s latency_ms=%d finish_reason=%s",
            request.session_id, latency_ms, meta.finish_reason,
        )

        await create_llm_call(
            self._session,
            provider=self._llm_provider.provider,
            model=self._llm_provider.model,
            feature="chat_stream",
            prompt=[{"role": "system", "content": system_prompt}] + messages_list,
            response=response_text,
            tokens_input=None,
            tokens_output=None,
            latency_ms=latency_ms,
            finish_reason=meta.finish_reason,
        )

        await self._message_service.create(
            MessageCreate(session_id=request.session_id, role="assistant", content=response_text)
        )

        for wm in working_memories:
            if wm.key == _LANGUAGE_PENDING_KEY:
                await self._working_memory_service.delete(wm.id)
                logger.info("StreamChat: cleared language pending WM id=%d", wm.id)

        if pending_wm is None:
            asyncio.create_task(
                self._memory_extraction_service.extract_and_save(
                    user_message=current_message.content,
                    message_id=current_message.id,
                )
            )
        else:
            # Exercise answers (practice/review/produce) are drill content, not facts
            # about the user — never mine them for memories.
            logger.debug("StreamChat: language pending mode — skipping memory extraction")
