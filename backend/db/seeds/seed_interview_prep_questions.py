"""Seed behavioral interview prep questions (with tags) from interview_prep_questions.yaml.

Insert-only, so it is safe to run on every deploy:
- a question whose text is not in the DB is inserted with its tags;
- an existing question that has no tags yet gets the YAML tags;
- nothing is ever deleted, and a question that already has tags is left alone, so tags you
  change in the portal are not undone.
Tags are the shared interview tags (organizer.interview_tags) and are created when missing.
Questions you delete in the portal are re-added on the next run; remove them from the YAML too.

Usage (from the backend/ directory):
    python db/seeds/seed_interview_prep_questions.py
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db.session import async_session
from app.features.organizer.interviews.prep_questions.tables import InterviewPrepQuestion
from app.features.organizer.interviews.tags.repository import InterviewTagRepository
from app.features.organizer.interviews.tags.schemas import normalize_tags

SEEDS_FILE = Path(__file__).parent / "interview_prep_questions.yaml"


def _load_questions() -> list[tuple[str, list[str]]]:
    """(text, tags) pairs in file order; duplicate texts are dropped (first wins)."""
    entries: list[dict] = yaml.safe_load(SEEDS_FILE.read_text()) or []
    unique: dict[str, list[str]] = {}
    for entry in entries:
        unique.setdefault(entry["text"].strip(), normalize_tags(entry.get("tags") or []) or [])
    return list(unique.items())


async def _seed() -> None:
    questions = _load_questions()
    async with async_session() as session:
        tag_repo = InterviewTagRepository(session)
        result = await session.execute(
            select(InterviewPrepQuestion).options(selectinload(InterviewPrepQuestion.tags))
        )
        by_text = {q.text: q for q in result.scalars()}

        inserted = tagged = 0
        for text, tags in questions:
            question = by_text.get(text)
            if question is None:
                question = InterviewPrepQuestion(text=text, tags=[])
                session.add(question)
                inserted += 1
            if not question.tags and tags:
                question.tags = await tag_repo.get_or_create_tags(tags)
                tagged += 1
        await session.commit()
    print(
        f"Interview prep questions: {inserted} inserted, {len(questions) - inserted} existing, "
        f"{tagged} tagged"
    )


if __name__ == "__main__":
    asyncio.run(_seed())
