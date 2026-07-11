"""Seed language tracks from the _TRACKS list below.

Inserts any track that doesn't exist yet. Tracks that already exist are left
untouched — name, level, daily_quota, review_mode and active are all
user-editable via PATCH /language/tracks/{id}, so re-running this on every
deploy must not clobber those edits.

Usage (from the backend/ directory):
    python db/seeds/seed_language_tracks.py
"""
from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.db.session import async_session
from app.features.language.tracks.tables import Track

_TRACKS = [
    ("fr", "French",  "A2"),
    ("ru", "Russian", "A1"),
    ("es", "Spanish", "A1"),
    ("it", "Italian", "A1"),
    ("en", "English", "B2"),
    ("de", "German",  "A1"),
]


async def _seed() -> None:
    now = datetime.now(timezone.utc)
    async with async_session() as session:
        for code, name, level in _TRACKS:
            stmt = (
                pg_insert(Track)
                .values(
                    code=code,
                    name=name,
                    level=level,
                    daily_quota=10,
                    review_mode="balanced",
                    active=True,
                    created_at=now,
                    updated_at=now,
                )
                .on_conflict_do_nothing(index_elements=["code"])
            )
            result = await session.execute(stmt)
            if result.rowcount:
                print(f"  [{code}] {name} ({level}) — inserted")
            else:
                print(f"  [{code}] {name} — already exists, left untouched")
        await session.commit()

    print(f"\nDone — {len(_TRACKS)} tracks checked.")


if __name__ == "__main__":
    asyncio.run(_seed())
