"""Seed grammar scope entries from language_grammar_scopes_*.yaml files.

Inserts new scope rows and updates priority/status for existing ones.
Idempotent — safe to re-run after editing the YAML files.

Usage (from the backend/ directory):
    python db/seeds/seed_grammar_scopes.py
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sqlalchemy import select

from app.db.session import async_session
from app.features.language.grammar_scope.tables import GrammarScope
from app.features.language.tracks.tables import Track

SEEDS_DIR = Path(__file__).parent


def _load_all_scopes() -> dict[str, list[dict]]:
    merged: dict[str, list[dict]] = {}
    for path in sorted(SEEDS_DIR.glob("language_grammar_scopes_*.yaml")):
        data: dict = yaml.safe_load(path.read_text()) or {}
        for lang_code, entries in data.items():
            merged.setdefault(lang_code, []).extend(entries or [])
    return merged


async def _seed() -> None:
    all_scopes = _load_all_scopes()
    if not all_scopes:
        print("No language_grammar_scopes_*.yaml files found — nothing to seed.")
        return

    async with async_session() as session:
        result = await session.execute(select(Track))
        tracks_by_code: dict[str, Track] = {t.code: t for t in result.scalars()}

        total_inserted = 0
        total_updated = 0

        for lang_code, entries in all_scopes.items():
            track = tracks_by_code.get(lang_code)
            if track is None:
                print(f"  [{lang_code}] no track found — skipping")
                continue

            existing_result = await session.execute(
                select(GrammarScope).where(GrammarScope.track_id == track.id)
            )
            existing: dict[tuple[str, str], GrammarScope] = {
                (s.category, s.value): s for s in existing_result.scalars()
            }

            inserted = updated = 0
            for entry in entries:
                key = (str(entry["category"]), str(entry["value"]))
                if key in existing:
                    scope = existing[key]
                    new_priority = entry.get("priority", scope.priority)
                    new_status = entry.get("status", scope.status)
                    if scope.priority != new_priority or scope.status != new_status:
                        scope.priority = new_priority
                        scope.status = new_status
                        updated += 1
                else:
                    session.add(GrammarScope(
                        track_id=track.id,
                        category=str(entry["category"]),
                        value=str(entry["value"]),
                        priority=entry.get("priority", 0),
                        status=entry.get("status", "deferred"),
                    ))
                    inserted += 1

            await session.commit()
            total_inserted += inserted
            total_updated += updated
            print(f"  [{lang_code}] {track.name}: {inserted} inserted, {updated} updated")

    print(f"\nDone — {total_inserted} inserted, {total_updated} updated.")


if __name__ == "__main__":
    asyncio.run(_seed())
