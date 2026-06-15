from __future__ import annotations

import pathlib

from fastapi import HTTPException, status
from pydantic_ai import Agent
from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart, UserPromptPart
from pydantic_ai.models.google import GoogleModel
from pydantic_ai.providers.google import GoogleProvider

from app.config import get_settings
from app.features.core.chats.schemas import ChatRequest
from app.features.core.embeddings.schemas import EmbeddingSearchRequest, EmbeddingSearchResult
from app.features.core.embeddings.service import EmbeddingService
from app.features.core.messages.schemas import MessageCreate, MessageFilters, MessageRead
from app.features.core.messages.service import MessageService

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


def _to_message_history(messages: list[MessageRead]) -> list:
    history: list = []
    for msg in messages:
        if msg.role == "user":
            history.append(ModelRequest(parts=[UserPromptPart(content=msg.content)]))
        else:
            history.append(ModelResponse(parts=[TextPart(content=msg.content)]))
    return history


def _create_agent(system_prompt: str) -> Agent:
    settings = get_settings()
    model = GoogleModel(
        settings.llm_model,
        provider=GoogleProvider(api_key=settings.google_api_key),
    )
    return Agent(model, output_type=str, system_prompt=system_prompt)


class ChatService:
    def __init__(self, embedding_service: EmbeddingService, message_service: MessageService) -> None:
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
        history = _to_message_history(all_messages[:-1][-_HISTORY_LIMIT:])

        memories = await self._embedding_service.search(
            EmbeddingSearchRequest(
                query=current_message.content,
                source_types=["memory", "note", "task"],
                limit=_MEMORY_LIMIT,
                threshold=_MEMORY_THRESHOLD,
            )
        )

        system_prompt = _build_system_prompt(memories)
        agent = _create_agent(system_prompt)
        result = await agent.run(current_message.content, message_history=history)
        response_text: str = result.output

        await self._message_service.create(
            MessageCreate(session_id=request.session_id, role="assistant", content=response_text)
        )

        return response_text
