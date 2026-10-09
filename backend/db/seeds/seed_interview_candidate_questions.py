"""Seed questions to ask interviewers (with categories) from interview_candidate_questions.yaml.

Insert-only, so it is safe to run on every deploy: a question whose text is not in the DB is
inserted; nothing is ever deleted or re-categorized. Questions you delete in the portal are
re-added on the next run; remove them from the YAML too.

Usage (from the backend/ directory):
    python db/seeds/seed_interview_candidate_questions.py
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sqlalchemy import select

from app.db.session import async_session
from app.features.organizer.interviews.candidate_questions.tables import InterviewCandidateQuestion

SEEDS_FILE = Path(__file__).parent / "interview_candidate_questions.yaml"


def _load_questions() -> list[tuple[str, str]]:
    """(text, category) pairs in file order; duplicate texts are dropped (first wins)."""
    entries: list[dict] = yaml.safe_load(SEEDS_FILE.read_text()) or []
    unique: dict[str, str] = {}
    for entry in entries:
        unique.setdefault(entry["text"].strip(), entry["category"].strip())
    return list(unique.items())


async def _seed() -> None:
    questions = _load_questions()
    async with async_session() as session:
        result = await session.execute(select(InterviewCandidateQuestion.text))
        existing = set(result.scalars())
        new = [
            InterviewCandidateQuestion(text=text, category=category)
            for text, category in questions
            if text not in existing
        ]
        session.add_all(new)
        await session.commit()
    print(f"Interview candidate questions: {len(new)} inserted, {len(questions) - len(new)} existing")


if __name__ == "__main__":
    asyncio.run(_seed())
