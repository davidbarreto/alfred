"""Seed intent examples into core.embeddings.

Each example in INTENT_EXAMPLES is embedded with all-MiniLM-L6-v2 and
upserted into core.embeddings with source_type='intent_example'. The
source_id is the static id defined on each IntentExample, so the script
is safe to re-run (idempotent).

Usage (from the backend/ directory):
    python db/seeds/seed_intents.py
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.assistant.intents.intent_examples import INTENT_EXAMPLES
from app.db.session import async_session
from app.features.core.embeddings.repository import EmbeddingRepository
from app.integrations.sentence_transformers.provider import (
    SentenceTransformerEmbeddingProvider,
)

SOURCE_TYPE = "intent_example"


async def _seed() -> None:
    provider = SentenceTransformerEmbeddingProvider()
    print(f"Model: {provider.model} ({provider.dimensions}d)")
    print(f"Seeding {len(INTENT_EXAMPLES)} examples…\n")

    async with async_session() as session:
        repo = EmbeddingRepository(session)
        total = len(INTENT_EXAMPLES)
        for i, example in enumerate(INTENT_EXAMPLES, 1):
            vector = await provider.embed(example.text)
            await repo.upsert(
                source_type=SOURCE_TYPE,
                source_id=example.id,
                content=example.text,
                vector=vector,
                model=provider.model,
                dimensions=provider.dimensions,
            )
            print(f"[{i:>3}/{total}] {example.intent:<35} {example.text[:55]}")

    print(f"\nDone — upserted {total} intent examples into core.embeddings.")


if __name__ == "__main__":
    asyncio.run(_seed())
