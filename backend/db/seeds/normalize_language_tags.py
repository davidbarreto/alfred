"""One-off cleanup: merge duplicate/synonym language.tags rows into a single
canonical tag per cluster.

Vocabulary chunks accumulated tags from two sources over time: the fixed
taxonomy applied via language_chunks_*.yaml (seed_language_chunks.py), and
ad-hoc tags created earlier through the app's LLM tag-suggestion feature
(suggest_tags_for_untagged). The latter produced near-duplicates of the
former (e.g. "Food & Drink" next to "Food", "Transport"/"Travel" next to
"Transportation") plus a long tail of one-off tags that don't belong to any
recurring theme.

This script re-links every chunk tagged with an old name to the canonical
tag (creating it if needed), then deletes the old tag row. Idempotent —
tags already merged or never present are silently skipped. Safe to re-run.

Usage (from the backend/ directory):
    python db/seeds/normalize_language_tags.py
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.db.session import async_session
from app.features.language.chunks.tables import LanguageTag, chunks_tags

# old tag name -> canonical tag name it should be merged into.
MERGE_MAP: dict[str, str] = {
    # Travel/transportation cluster — collapsed to one label per user request.
    "Travel": "Travel & Transport",
    "Transportation": "Travel & Transport",
    "Transport": "Travel & Transport",
    "Food & Drink": "Food",
    "Feelings": "Emotions",
    "Abilities": "Grammar",
    "Basic Concepts": "Education",
    "Basic Needs": "Body",
    "Basic Phrases": "Communication",
    "Future": "Time",
    "Hobbies & Leisure": "Entertainment",
    "Language": "Communication",
    "Languages": "Communication",
    "Learning": "Education",
    "Location": "Directions",
    "Memory": "Opinions",
    "Permission": "Politeness",
    "Personal Care": "Daily Routine",
    "Possession": "Grammar",
    "Preferences": "Opinions",
    "Questions": "Grammar",
    "Social Interaction": "Communication",
    "Thoughts": "Opinions",
    "Conversations": "Communication",
    "Daily Life": "Daily Routine",
    "Descriptions": "Opinions",
    "Expressions": "Opinions",
    "Greetings & Social": "Greetings",
    "Household Chores": "Home",
    "Leisure": "Entertainment",
}


async def _normalize() -> None:
    async with async_session() as session:
        tag_result = await session.execute(select(LanguageTag))
        tags_by_name: dict[str, LanguageTag] = {t.name: t for t in tag_result.scalars()}

        merged = 0
        for old_name, canonical_name in MERGE_MAP.items():
            old_tag = tags_by_name.get(old_name)
            if old_tag is None:
                continue

            canonical_tag = tags_by_name.get(canonical_name)
            if canonical_tag is None:
                canonical_tag = LanguageTag(name=canonical_name)
                session.add(canonical_tag)
                await session.flush()
                tags_by_name[canonical_name] = canonical_tag

            chunk_ids_result = await session.execute(
                select(chunks_tags.c.chunk_id).where(chunks_tags.c.tag_id == old_tag.id)
            )
            chunk_ids = [row[0] for row in chunk_ids_result]

            if chunk_ids:
                stmt = pg_insert(chunks_tags).values(
                    [{"chunk_id": cid, "tag_id": canonical_tag.id} for cid in chunk_ids]
                )
                stmt = stmt.on_conflict_do_nothing(index_elements=["chunk_id", "tag_id"])
                await session.execute(stmt)

            await session.execute(delete(chunks_tags).where(chunks_tags.c.tag_id == old_tag.id))
            await session.execute(delete(LanguageTag).where(LanguageTag.id == old_tag.id))
            del tags_by_name[old_name]

            print(f"  {old_name!r} -> {canonical_name!r}: {len(chunk_ids)} chunks re-linked")
            merged += 1

        await session.commit()
        print(f"\nDone — {merged} tag(s) merged.")


if __name__ == "__main__":
    asyncio.run(_normalize())
