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
)
from app.features.core.embeddings.schemas import EmbeddingSearchRequest, EmbeddingSearchResult
from app.features.core.embeddings.service import EmbeddingService
from app.features.core.memories.extraction_service import MemoryExtractionService
from app.features.core.messages.schemas import MessageCreate, MessageFilters, MessageRead
from app.features.core.messages.service import MessageService
from app.features.core.sessions.repository import SessionRepository
from app.features.core.sessions.summary_service import SessionSummaryService
from app.features.core.working_memory.schemas import WorkingMemoryFilters, WorkingMemoryRead
from app.features.core.working_memory.service import WorkingMemoryService
from app.features.language.sessions.repository import SessionRepository as LanguageSessionRepository
from app.features.language.sessions.schemas import SessionFilters as LanguageSessionFilters
from app.features.language.sessions.tables import LearningSession
from app.integrations.llm_calls.repository import create_llm_call
from app.shared.llm import LlmProvider, StreamMeta

_PERSONA_PATH = pathlib.Path(__file__).parents[3] / "assistant" / "persona.md"
_HISTORY_LIMIT = 10
_MEMORY_LIMIT = 5
_MEMORY_THRESHOLD = 0.6


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

    if working_memories:
        lines = "\n".join(f"- {wm.key}: {wm.value}" for wm in working_memories)
        section = f"## Active context\n{lines}"
        if any(wm.key == "language:pending_practice" for wm in working_memories):
            if language_session and language_session.quality_score is not None:
                fb = language_session.gemini_feedback_json or {}
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
        parts.append(section)

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
    ) -> None:
        self._session = session
        self._llm_provider = llm_provider
        self._embedding_service = embedding_service
        self._message_service = message_service
        self._memory_extraction_service = memory_extraction_service
        self._session_summary_service = session_summary_service
        self._working_memory_service = working_memory_service

    async def _fetch_history(self, session_id: int) -> list[MessageRead]:
        session = await SessionRepository(self._session).get(session_id)
        if session and session.source and session.external_id:
            return await self._message_service.list(
                MessageFilters(source=session.source, external_id=session.external_id, limit=_HISTORY_LIMIT + 1)
            )
        return await self._message_service.list(
            MessageFilters(session_id=session_id, limit=_HISTORY_LIMIT + 1)
        )

    async def chat(self, request: ChatRequest) -> str:
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
        if any(wm.key == "language:pending_practice" for wm in working_memories):
            logger.debug("Chat: language practice mode — skipping embeddings, summaries, daily context")
            memories, recent_summaries, daily_context = [], [], ""
            practice_wm = next(wm for wm in working_memories if wm.key == "language:pending_practice")
            try:
                chunk_id = json.loads(practice_wm.value).get("chunk_id")
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
            except (json.JSONDecodeError, KeyError):
                logger.warning("Chat: failed to parse practice WM value=%r", practice_wm.value)
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

        system_prompt = _build_system_prompt(memories, request.detected_intents, recent_summaries, daily_context, working_memories, language_session)
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

        asyncio.create_task(
            self._memory_extraction_service.extract_and_save(
                user_message=current_message.content,
                message_id=current_message.id,
            )
        )

        return response_text

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
        if any(wm.key == "language:pending_practice" for wm in working_memories):
            memories, recent_summaries, daily_context = [], [], ""
            practice_wm = next(wm for wm in working_memories if wm.key == "language:pending_practice")
            try:
                chunk_id = json.loads(practice_wm.value).get("chunk_id")
                if chunk_id:
                    lang_sessions = await LanguageSessionRepository(self._session).get_sessions(
                        LanguageSessionFilters(chunk_id=chunk_id, session_type="shadowing", limit=1)
                    )
                    language_session = lang_sessions[0] if lang_sessions else None
            except (json.JSONDecodeError, KeyError):
                logger.warning("StreamChat: failed to parse practice WM value=%r", practice_wm.value)
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

        system_prompt = _build_system_prompt(memories, request.detected_intents, recent_summaries, daily_context, working_memories, language_session)
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

        asyncio.create_task(
            self._memory_extraction_service.extract_and_save(
                user_message=current_message.content,
                message_id=current_message.id,
            )
        )
