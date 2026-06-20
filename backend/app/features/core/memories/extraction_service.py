from __future__ import annotations

import json
import logging
import time
from typing import Any

from app.db.session import async_session
from app.features.core.embeddings.schemas import EmbeddingCreate, EmbeddingSearchRequest
from app.features.core.embeddings.service import EmbeddingService
from app.features.core.memories.schemas import MemoryCreate, MemoryUpdate
from app.features.core.memories.service import MemoryService
from app.integrations.llm_calls.repository import create_llm_call
from app.shared.embedding import EmbeddingProvider
from app.shared.llm import LlmProvider

logger = logging.getLogger(__name__)

_DEDUP_THRESHOLD = 0.85
_IMPORTANCE_BUMP = 0.1

_EXTRACTION_PROMPT = """\
You are a memory extractor for a personal AI assistant.
Analyze the user message and extract personal facts, preferences, habits, goals, \
relationships, or skills worth remembering long-term.

Rules:
- Only extract information specifically about the user, not generic questions or commands
- Skip vague or one-off statements unlikely to be useful later
- Confidence: lower if information is implied rather than stated directly
- Importance: how useful this will be in future conversations

Return ONLY a valid JSON array with no explanation or markdown:
[{{"category": "fact|preference|habit|goal|relationship|skill", "content": "...", "importance": 0.0-1.0, "confidence": 0.0-1.0}}]

Return [] if nothing is worth remembering.

User message: {message}"""


class MemoryExtractionService:
    def __init__(self, llm_provider: LlmProvider, embedding_provider: EmbeddingProvider) -> None:
        self._llm_provider = llm_provider
        self._embedding_provider = embedding_provider

    async def extract_and_save(self, user_message: str, message_id: int) -> None:
        try:
            await self._do_extract(user_message, message_id)
        except Exception:
            logger.exception("Memory extraction failed for message_id=%d", message_id)

    async def _do_extract(self, user_message: str, message_id: int) -> None:
        prompt = _EXTRACTION_PROMPT.format(message=user_message)
        messages = [{"role": "user", "content": prompt}]
        t0 = time.monotonic()
        llm_response = await self._llm_provider.complete(messages)
        latency_ms = int((time.monotonic() - t0) * 1000)
        raw = llm_response.text.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

        try:
            candidates: list[dict[str, Any]] = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning(
                "Memory extraction: invalid JSON for message_id=%d: %r",
                message_id, raw[:200],
            )
            return

        if not candidates:
            return

        logger.info("Memory extraction: %d candidates for message_id=%d", len(candidates), message_id)

        async with async_session() as session:
            await create_llm_call(
                session,
                provider=self._llm_provider.provider,
                model=self._llm_provider.model,
                feature="memory_extraction",
                prompt=messages,
                response=llm_response.text,
                tokens_input=llm_response.tokens_input,
                tokens_output=llm_response.tokens_output,
                latency_ms=latency_ms,
            )
            memory_service = MemoryService(session)
            embedding_service = EmbeddingService(session, self._embedding_provider)
            for candidate in candidates:
                await self._upsert_memory(candidate, message_id, memory_service, embedding_service)

    async def _upsert_memory(
        self,
        candidate: dict[str, Any],
        message_id: int,
        memory_service: MemoryService,
        embedding_service: EmbeddingService,
    ) -> None:
        content = str(candidate.get("content", "")).strip()
        category = str(candidate.get("category", "fact"))
        importance = min(1.0, max(0.0, float(candidate.get("importance", 0.5))))
        confidence = min(1.0, max(0.0, float(candidate.get("confidence", 1.0))))

        if not content:
            return

        similar = await embedding_service.search(
            EmbeddingSearchRequest(
                query=content,
                source_types=["memory"],
                limit=1,
                threshold=_DEDUP_THRESHOLD,
            )
        )

        if similar:
            existing_id = similar[0].source_id
            existing = await memory_service.get(existing_id)
            if existing:
                new_importance = min(1.0, existing.importance + _IMPORTANCE_BUMP)
                await memory_service.update(existing_id, MemoryUpdate(importance=new_importance))
                logger.debug("Memory importance bumped: id=%d importance=%.2f", existing_id, new_importance)
                return

        memory = await memory_service.create(
            MemoryCreate(
                category=category,
                content=content,
                importance=importance,
                confidence=confidence,
                origin_message_id=message_id,
            )
        )
        await embedding_service.embed(
            EmbeddingCreate(source_type="memory", source_id=memory.id, content=content)
        )
        logger.debug("Memory created: id=%d category=%s", memory.id, category)
