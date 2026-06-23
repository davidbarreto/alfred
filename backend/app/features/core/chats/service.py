from __future__ import annotations

import asyncio
import logging
import pathlib
import re
import time
from datetime import datetime, timezone
from typing import AsyncGenerator

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

from app.features.core.chats.schemas import ChatRequest
from app.features.core.embeddings.schemas import EmbeddingSearchRequest, EmbeddingSearchResult
from app.features.core.embeddings.service import EmbeddingService
from app.features.core.memories.extraction_service import MemoryExtractionService
from app.features.core.messages.schemas import MessageCreate, MessageFilters, MessageRead
from app.features.core.messages.service import MessageService
from app.features.core.sessions.summary_service import SessionSummaryService
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


_FORMATTING_INSTRUCTIONS = (
    "## Output format\n"
    "Messages are delivered through Telegram. "
    "Use only plain text — no markdown, no asterisks for bold, no underscores for italic, no backtick code blocks. "
    "Use line breaks and simple punctuation for structure instead."
)

_FOCUS_INSTRUCTIONS = (
    "## Focus\n"
    "Respond only to David's current message. "
    "Do not proactively resume, continue, or elaborate on tasks mentioned in previous messages — "
    "wait until David explicitly asks you to."
)

_COMMAND_BOUNDARY_INSTRUCTIONS = (
    "## Commands\n"
    "You do not execute write operations directly. "
    "Tasks, notes, events, and transactions are handled by a separate command pipeline, not by you in conversation. "
    "Never say you have added, created, saved, or completed something unless a command result is explicitly shown to you. "
    "Never offer to create, add, or save anything — that is not your role. "
    "If a message looks like a task or note request but no pipeline result is provided, "
    "tell David you did not catch it as a command and suggest he rephrase or use a slash command (e.g. /task buy beans)."
)

_LANGUAGE_INSTRUCTIONS = (
    "## Language\n"
    "Always reply in English by default. "
    "Switch to Portuguese only if David's current message is written in Portuguese. "
    "You may use occasional Portuguese words or expressions naturally, but the reply must be in English unless David is writing in Portuguese."
)


def _build_system_prompt(
    memories: list[EmbeddingSearchResult],
    detected_intents: list[str] | None = None,
    recent_summaries: list[tuple[datetime, str]] | None = None,
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
        _FORMATTING_INSTRUCTIONS,
        _LANGUAGE_INSTRUCTIONS,
        _FOCUS_INSTRUCTIONS,
    ]

    if not detected_intents:
        parts.append(_COMMAND_BOUNDARY_INSTRUCTIONS)

    if recent_summaries:
        lines = "\n".join(
            f"{ts.strftime('%B %d, %Y')}: {summary}"
            for ts, summary in recent_summaries
        )
        parts.append(f"## Recent conversations\n{lines}")

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
    ) -> None:
        self._session = session
        self._llm_provider = llm_provider
        self._embedding_service = embedding_service
        self._message_service = message_service
        self._memory_extraction_service = memory_extraction_service
        self._session_summary_service = session_summary_service

    async def chat(self, request: ChatRequest) -> str:
        logger.info("Chat: session_id=%s", request.session_id)
        messages = await self._message_service.list(
            MessageFilters(session_id=request.session_id, limit=_HISTORY_LIMIT + 1)
        )
        if not messages:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="No messages found in session. Call POST /core/messages first.",
            )

        current_message = messages[-1]
        history = _to_message_dicts(messages[:-1])

        logger.debug("Chat: %d history messages, searching memory for context", len(history))
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

        system_prompt = _build_system_prompt(memories, request.detected_intents, recent_summaries)
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
        messages = await self._message_service.list(
            MessageFilters(session_id=request.session_id, limit=_HISTORY_LIMIT + 1)
        )
        if not messages:
            yield f"[error: No messages found in session. Call POST /core/messages first.]"
            return

        current_message = messages[-1]
        history = _to_message_dicts(messages[:-1])

        memories = await self._embedding_service.search(
            EmbeddingSearchRequest(
                query=current_message.content,
                source_types=["memory", "note", "task"],
                limit=_MEMORY_LIMIT,
                threshold=_MEMORY_THRESHOLD,
            )
        )
        recent_summaries = await self._session_summary_service.get_recent_summaries(request.session_id)
        system_prompt = _build_system_prompt(memories, request.detected_intents, recent_summaries)
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
