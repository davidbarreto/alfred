from __future__ import annotations

import pathlib
import time

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.core.chats.schemas import ChatRequest
from app.features.core.embeddings.schemas import EmbeddingSearchRequest, EmbeddingSearchResult
from app.features.core.embeddings.service import EmbeddingService
from app.features.core.messages.schemas import MessageCreate, MessageFilters, MessageRead
from app.features.core.messages.service import MessageService
from app.integrations.llm_calls.repository import create_llm_call
from app.shared.llm import LlmProvider

_PERSONA_PATH = pathlib.Path(__file__).parents[4] / "assistant" / "persona.md"
_HISTORY_LIMIT = 10
_MEMORY_LIMIT = 5
_MEMORY_THRESHOLD = 0.6


def _load_persona() -> str:
    try:
        return _PERSONA_PATH.read_text(encoding="utf-8")
    except FileNotFoundError:
        return "You are Alfred, a helpful personal AI assistant."


def _build_system_prompt(memories: list[EmbeddingSearchResult]) -> str:
    parts = [_load_persona()]

    if memories:
        lines = "\n".join(f"- [{m.source_type}] {m.content}" for m in memories)
        parts.append(f"## Relevant context from memory\n{lines}")

    return "\n\n".join(parts)


def _to_message_dicts(messages: list[MessageRead]) -> list[dict[str, str]]:
    return [{"role": msg.role, "content": msg.content} for msg in messages]


class ChatService:
    def __init__(
        self,
        session: AsyncSession,
        llm_provider: LlmProvider,
        embedding_service: EmbeddingService,
        message_service: MessageService,
    ) -> None:
        self._session = session
        self._llm_provider = llm_provider
        self._embedding_service = embedding_service
        self._message_service = message_service

    async def chat(self, request: ChatRequest) -> str:
        all_messages = await self._message_service.list(
            MessageFilters(session_id=request.session_id)
        )
        if not all_messages:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="No messages found in session. Call POST /core/messages first.",
            )

        current_message = all_messages[-1]
        history = _to_message_dicts(all_messages[:-1][-_HISTORY_LIMIT:])

        memories = await self._embedding_service.search(
            EmbeddingSearchRequest(
                query=current_message.content,
                source_types=["memory", "note", "task"],
                limit=_MEMORY_LIMIT,
                threshold=_MEMORY_THRESHOLD,
            )
        )

        system_prompt = _build_system_prompt(memories)
        messages = history + [{"role": "user", "content": current_message.content}]

        t0 = time.monotonic()
        llm_response = await self._llm_provider.complete(messages, system=system_prompt)
        latency_ms = int((time.monotonic() - t0) * 1000)

        await create_llm_call(
            self._session,
            provider=self._llm_provider.provider,
            model=self._llm_provider.model,
            feature="chat",
            prompt=[{"role": "system", "content": system_prompt}] + messages,
            response=llm_response.text,
            tokens_input=llm_response.tokens_input,
            tokens_output=llm_response.tokens_output,
            latency_ms=latency_ms,
        )

        await self._message_service.create(
            MessageCreate(session_id=request.session_id, role="assistant", content=llm_response.text)
        )

        return llm_response.text
