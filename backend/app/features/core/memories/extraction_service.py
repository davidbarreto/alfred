from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any, cast, get_args

from app.db.session import async_session
from app.features.core.embeddings.schemas import EmbeddingCreate, EmbeddingSearchRequest
from app.features.core.embeddings.service import EmbeddingService
from app.features.core.memories.schemas import MemoryCategory, MemoryCreate, MemoryUpdate
from app.features.core.memories.service import MemoryService
from app.features.core.prompts import MEMORY_EXTRACTION_PROMPT
from app.features.core.working_memory.repository import WorkingMemoryRepository
from app.features.core.working_memory.schemas import WorkingMemoryCreate
from app.integrations.llm_calls.repository import create_llm_call
from app.shared.embedding import EmbeddingProvider
from app.shared.llm import LlmProvider

logger = logging.getLogger(__name__)

_DEDUP_THRESHOLD = 0.85
_IMPORTANCE_BUMP = 0.1
_VALID_CATEGORIES: frozenset[str] = frozenset(get_args(MemoryCategory))
_TRANSIENT_TTL_DAYS = 3


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
        prompt = MEMORY_EXTRACTION_PROMPT.format(message=user_message)
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
        raw_category = str(candidate.get("category", "fact"))
        category = cast(MemoryCategory, raw_category if raw_category in _VALID_CATEGORIES else "fact")
        importance = min(1.0, max(0.0, float(candidate.get("importance", 0.5))))
        confidence = min(1.0, max(0.0, float(candidate.get("confidence", 1.0))))

        if not content:
            return

        if category == "transient":
            await self._save_transient(content, message_id)
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

    async def _save_transient(self, content: str, message_id: int) -> None:
        expires_at = datetime.now(timezone.utc) + timedelta(days=_TRANSIENT_TTL_DAYS)
        async with async_session() as session:
            repo = WorkingMemoryRepository(session)
            wm = await repo.create(
                WorkingMemoryCreate(
                    key=f"transient:{message_id}",
                    value=content,
                    expires_at=expires_at,
                )
            )
        logger.debug("Transient memory saved as working memory: id=%d expires_at=%s", wm.id, expires_at.date())
