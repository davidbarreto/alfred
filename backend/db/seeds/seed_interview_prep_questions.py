"""Seed common behavioral interview prep questions from interview_prep_questions.yaml.

Insert-only and idempotent: a question whose text already exists is skipped.
Not run from entrypoint.sh, so questions you delete from the portal are not re-added on deploy.

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

from app.db.session import async_session
from app.features.organizer.interviews.prep_questions.tables import InterviewPrepQuestion

SEEDS_FILE = Path(__file__).parent / "interview_prep_questions.yaml"


def _load_questions() -> list[str]:
    data: dict[str, list[str]] = yaml.safe_load(SEEDS_FILE.read_text()) or {}
    return [text.strip() for group in data.values() for text in group or []]


async def _seed() -> None:
    questions = _load_questions()
    async with async_session() as session:
        result = await session.execute(select(InterviewPrepQuestion.text))
        existing = set(result.scalars())
        new = [q for q in dict.fromkeys(questions) if q not in existing]
        session.add_all(InterviewPrepQuestion(text=q) for q in new)
        await session.commit()
    print(f"Interview prep questions: {len(new)} inserted, {len(questions) - len(new)} skipped")


if __name__ == "__main__":
    asyncio.run(_seed())
