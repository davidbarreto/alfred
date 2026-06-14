from __future__ import annotations

from typing import Literal

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.assistant.intents.intent_examples import INTENT_EXAMPLES
from app.features.core.embeddings.repository import EmbeddingRepository
from app.integrations.sentence_transformers.provider import (
    SentenceTransformerEmbeddingProvider,
)


class IntentResult(BaseModel):
    intent: str
    confidence: float
    source: Literal["intent_detection"] = "intent_detection"


# Lazy-loads the model on first call via @cached_property on the provider.
_provider = SentenceTransformerEmbeddingProvider()

# Map example.id → intent label for reverse-lookup after similarity search.
_INTENT_BY_ID: dict[int, str] = {ex.id: ex.intent for ex in INTENT_EXAMPLES}


async def detect_intent(text: str, session: AsyncSession) -> IntentResult:
    vector = await _provider.embed(text)
    repo = EmbeddingRepository(session)
    results = await repo.search(
        query_vector=vector,
        source_types=["intent_example"],
        limit=1,
        threshold=0.0,
    )
    if not results:
        return IntentResult(intent="unknown", confidence=0.0)
    embedding, similarity = results[0]
    intent = _INTENT_BY_ID.get(embedding.source_id, "unknown")
    return IntentResult(intent=intent, confidence=round(similarity, 4))
