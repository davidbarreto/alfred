from __future__ import annotations

import pathlib

from pydantic_ai import Agent
from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart, UserPromptPart
from pydantic_ai.models.google import GoogleModel
from pydantic_ai.providers.google import GoogleProvider

from app.config import get_settings
from app.features.core.chats.schemas import ChatRequest, ExecutedCommandResult
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


def _build_system_prompt(
    memories: list[EmbeddingSearchResult],
    executed_commands: list[ExecutedCommandResult],
) -> str:
    parts = [_load_persona()]

    if memories:
        lines = "\n".join(f"- [{m.source_type}] {m.content}" for m in memories)
        parts.append(f"## Relevant context from memory\n{lines}")

    if executed_commands:
        lines = "\n".join(
            f"- {cmd.type}.{cmd.command}: {cmd.result if cmd.result is not None else 'no result'}"
            for cmd in executed_commands
        )
        parts.append(f"## Commands executed this turn\n{lines}")

    return "\n\n".join(parts)


def _to_message_history(messages: list[MessageRead]) -> list:
    history: list = []
    for msg in messages:
        history.append(ModelRequest(parts=[UserPromptPart(content=msg.input)]))
        if msg.response:
            history.append(ModelResponse(parts=[TextPart(content=msg.response)]))
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
        history: list = []
        if request.session_id is not None:
            all_messages = await self._message_service.list(
                MessageFilters(session_id=request.session_id)
            )
            history = _to_message_history(all_messages[-_HISTORY_LIMIT:])

        memories = await self._embedding_service.search(
            EmbeddingSearchRequest(
                query=request.text,
                source_types=["memory", "note", "task"],
                limit=_MEMORY_LIMIT,
                threshold=_MEMORY_THRESHOLD,
            )
        )

        system_prompt = _build_system_prompt(memories, request.executed_commands)

        agent = _create_agent(system_prompt)
        result = await agent.run(request.text, message_history=history)
        response_text: str = result.output

        if request.session_id is not None:
            await self._message_service.create(
                MessageCreate(
                    session_id=request.session_id,
                    source=request.source,
                    input=request.text,
                    response=response_text,
                )
            )

        return response_text
