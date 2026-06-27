"""Dump language chunks from the database to per-language YAML seed files.

Reads chunks for each requested language and writes (or overwrites)
language_chunks_<code>.yaml in this directory. Chunks are ordered by
frequency_rank (nulls last), then by creation date.

Usage (from the backend/ directory):
    python db/seeds/dump_language_chunks.py fr ru
    python db/seeds/dump_language_chunks.py fr        # single language
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sqlalchemy import select

from app.db.session import async_session
from app.features.language.chunks.tables import Chunk
from app.features.language.tracks.tables import Track

SEEDS_DIR = Path(__file__).parent


async def _dump(codes: list[str]) -> None:
    async with async_session() as session:
        for code in codes:
            result = await session.execute(select(Track).where(Track.code == code))
            track = result.scalars().first()
            if track is None:
                print(f"  [{code}] no track found — skipping")
                continue

            chunks_result = await session.execute(
                select(Chunk)
                .where(Chunk.track_id == track.id)
                .order_by(Chunk.frequency_rank.asc().nulls_last(), Chunk.created_at.asc())
            )
            chunks = chunks_result.scalars().all()

            entries = []
            for c in chunks:
                entry: dict = {
                    "text": c.text,
                    "translation": c.translation,
                    "type": c.chunk_type,
                }
                if c.example_sentence:
                    entry["example"] = c.example_sentence
                if c.example_translation:
                    entry["example_translation"] = c.example_translation
                if c.cefr_level:
                    entry["cefr_level"] = c.cefr_level
                if c.frequency_rank is not None:
                    entry["frequency_rank"] = c.frequency_rank
                entries.append(entry)

            out_path = SEEDS_DIR / f"language_chunks_{code}.yaml"
            with open(out_path, "w", encoding="utf-8") as f:
                yaml.dump(
                    {code: entries},
                    f,
                    allow_unicode=True,
                    sort_keys=False,
                    default_flow_style=False,
                )
            print(f"  [{code}] {track.name} ({track.level}): {len(entries)} chunks → {out_path.name}")


if __name__ == "__main__":
    codes = sys.argv[1:]
    if not codes:
        print("Usage: python db/seeds/dump_language_chunks.py <lang_code> [<lang_code> ...]")
        sys.exit(1)
    asyncio.run(_dump(codes))
