"""Seed intent examples into core.embeddings.

Each example in INTENT_EXAMPLES is embedded with all-MiniLM-L6-v2 and
upserted into core.embeddings with source_type='intent_example'. The
source_id is a stable 32-bit signed integer derived from the intent and
text so the script is safe to re-run (idempotent).

Usage (from the backend/ directory):
    python db/seeds/seed_intents.py
"""
from __future__ import annotations

import asyncio
import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.db.session import async_session
from app.features.core.embeddings.repository import EmbeddingRepository
from app.assistant.intents.intent_examples import INTENT_EXAMPLES
from app.integrations.sentence_transformers.provider import (
    SentenceTransformerEmbeddingProvider,
)

SOURCE_TYPE = "intent_example"


def stable_source_id(intent: str, text: str) -> int:
    """Derive a stable 32-bit signed integer from intent + text."""
    digest = hashlib.md5(f"{intent}:{text}".encode()).digest()
    unsigned = int.from_bytes(digest[:4], "big")
    return unsigned - (1 << 31)


async def _seed() -> None:
    provider = SentenceTransformerEmbeddingProvider()
    print(f"Model: {provider.model} ({provider.dimensions}d)")
    print(f"Seeding {len(INTENT_EXAMPLES)} examples…\n")

    async with async_session() as session:
        repo = EmbeddingRepository(session)
        total = len(INTENT_EXAMPLES)
        for i, example in enumerate(INTENT_EXAMPLES, 1):
            source_id = stable_source_id(example.intent, example.text)
            vector = await provider.embed(example.text)
            await repo.upsert(
                source_type=SOURCE_TYPE,
                source_id=source_id,
                content=example.text,
                vector=vector,
                model=provider.model,
                dimensions=provider.dimensions,
            )
            print(f"[{i:>3}/{total}] {example.intent:<35} {example.text[:55]}")

    print(f"\nDone — upserted {total} intent examples into core.embeddings.")


if __name__ == "__main__":
    asyncio.run(_seed())
