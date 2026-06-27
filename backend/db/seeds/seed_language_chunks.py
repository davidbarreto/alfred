"""Seed language vocabulary chunks from language_chunks_*.yaml files.

Reads all per-language YAML files in this directory and inserts any chunk
that does not already exist for the given track (matched by track code + text).
Existing rows are left untouched so SRS state (stability, difficulty,
repetitions) is preserved across redeployments.

Also syncs grammar_scope_id for existing chunks when the YAML has a
grammar_scope field set. Run seed_grammar_scopes.py first so the scope
rows exist.

Usage (from the backend/ directory):
    python db/seeds/seed_language_chunks.py
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sqlalchemy import select, update as sa_update

from app.db.session import async_session
from app.features.language.chunks.tables import Chunk
from app.features.language.grammar_scope.tables import GrammarScope
from app.features.language.tracks.tables import Track

SEEDS_DIR = Path(__file__).parent


def _load_all_chunks() -> dict[str, list[dict]]:
    """Merge all language_chunks*.yaml files into a single {code: [entries]} dict."""
    merged: dict[str, list[dict]] = {}
    for path in sorted(SEEDS_DIR.glob("language_chunks*.yaml")):
        data: dict = yaml.safe_load(path.read_text()) or {}
        for lang_code, entries in data.items():
            merged.setdefault(lang_code, []).extend(entries or [])
    return merged


async def _seed() -> None:
    all_chunks = _load_all_chunks()
    if not all_chunks:
        print("No language_chunks*.yaml files found — nothing to seed.")
        return

    async with async_session() as session:
        result = await session.execute(select(Track).where(Track.active == True))
        tracks_by_code: dict[str, Track] = {t.code: t for t in result.scalars()}

        total_inserted = 0
        total_scoped = 0

        for lang_code, entries in all_chunks.items():
            track = tracks_by_code.get(lang_code)
            if track is None:
                print(f"  [{lang_code}] no active track found — skipping")
                continue

            # Build scope lookup: value → id
            scope_result = await session.execute(
                select(GrammarScope.id, GrammarScope.value)
                .where(GrammarScope.track_id == track.id)
            )
            scope_by_value: dict[str, int] = {v: i for i, v in scope_result}

            # Load existing chunk texts and IDs
            existing_result = await session.execute(
                select(Chunk.id, Chunk.text).where(Chunk.track_id == track.id)
            )
            existing_rows = list(existing_result)
            existing_texts: set[str] = {text for _, text in existing_rows}
            chunk_id_by_text: dict[str, int] = {text: cid for cid, text in existing_rows}

            inserted = scoped = 0

            for entry in entries:
                text = str(entry["text"])
                gs_val = entry.get("grammar_scope")
                scope_id = scope_by_value.get(gs_val) if isinstance(gs_val, str) else None

                if text not in existing_texts:
                    example_translation = entry.get("example_translation")
                    if example_translation in (None, "null"):
                        example_translation = None
                    session.add(
                        Chunk(
                            track_id=track.id,
                            chunk_type=str(entry["type"]),
                            text=text,
                            translation=str(entry["translation"]),
                            example_sentence=entry.get("example"),
                            example_translation=example_translation,
                            cefr_level=entry.get("cefr_level"),
                            frequency_rank=entry.get("frequency_rank"),
                            frequency_source="pareto_list",
                            grammar_scope_id=scope_id,
                            status="active",
                        )
                    )
                    existing_texts.add(text)
                    inserted += 1
                elif scope_id and text in chunk_id_by_text:
                    # Sync grammar_scope_id on existing chunk (preserves all SRS state).
                    await session.execute(
                        sa_update(Chunk)
                        .where(Chunk.id == chunk_id_by_text[text])
                        .values(grammar_scope_id=scope_id)
                    )
                    scoped += 1

            await session.commit()
            total_inserted += inserted
            total_scoped += scoped
            print(
                f"  [{lang_code}] {track.name} ({track.level}): "
                f"{inserted} inserted, {scoped} grammar scopes synced, "
                f"{len(existing_texts) - inserted} already existed"
            )

    print(f"\nDone — {total_inserted} new chunks seeded, {total_scoped} grammar scopes synced.")


if __name__ == "__main__":
    asyncio.run(_seed())
