import datetime

from sqlalchemy import case, func, select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.cs.problems.tables import CsTag, Problem, problems_tags
from app.features.cs.submissions.tables import Submission

_DIFFICULTY_ORDER = {"easy": 0, "medium": 1, "hard": 2}


class StatsRepository:

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_solved_dates(self) -> list[datetime.date]:
        query = (
            select(func.date(Submission.submitted_at))
            .where(Submission.verdict == "accepted")
            .distinct()
            .order_by(func.date(Submission.submitted_at))
        )
        result = await self._session.execute(query)
        return [row[0] for row in result.all()]

    async def get_total_solved(self) -> int:
        query = select(func.count(func.distinct(Submission.problem_id))).where(
            Submission.verdict == "accepted"
        )
        result = await self._session.execute(query)
        return result.scalar_one()

    async def get_tag_breakdown(self) -> list[tuple[str, int, int]]:
        solved_case = case((Submission.verdict == "accepted", Problem.id))
        query = (
            select(
                CsTag.name,
                func.count(func.distinct(Problem.id)),
                func.count(func.distinct(solved_case)),
            )
            .select_from(CsTag)
            .join(problems_tags, problems_tags.c.tag_id == CsTag.id)
            .join(Problem, Problem.id == problems_tags.c.problem_id)
            .join(Submission, Submission.problem_id == Problem.id)
            .group_by(CsTag.name)
            .order_by(CsTag.name)
        )
        result = await self._session.execute(query)
        return [(name, attempted, solved) for name, attempted, solved in result.all()]

    async def get_difficulty_breakdown(self) -> list[tuple[str, int, int]]:
        solved_case = case((Submission.verdict == "accepted", Problem.id))
        query = (
            select(
                Problem.difficulty,
                func.count(func.distinct(Problem.id)),
                func.count(func.distinct(solved_case)),
            )
            .select_from(Problem)
            .join(Submission, Submission.problem_id == Problem.id)
            .where(Problem.difficulty.is_not(None))
            .group_by(Problem.difficulty)
        )
        result = await self._session.execute(query)
        return [(difficulty, attempted, solved) for difficulty, attempted, solved in result.all()]

    async def get_language_breakdown(self) -> list[tuple[str, int]]:
        query = (
            select(Submission.language, func.count(func.distinct(Submission.problem_id)))
            .where(Submission.verdict == "accepted", Submission.language.is_not(None))
            .group_by(Submission.language)
            .order_by(Submission.language)
        )
        result = await self._session.execute(query)
        return [(language, solved) for language, solved in result.all()]

    async def get_unsolved_candidate_problems(
        self, tag_names: list[str] | None, limit: int
    ) -> list[Problem]:
        solved_problem_ids = select(Submission.problem_id).where(Submission.verdict == "accepted")
        query = select(Problem).options(selectinload(Problem.tags)).where(
            Problem.id.not_in(solved_problem_ids)
        )
        if tag_names:
            query = query.join(problems_tags, problems_tags.c.problem_id == Problem.id).join(
                CsTag, CsTag.id == problems_tags.c.tag_id
            ).where(CsTag.name.in_(tag_names)).distinct()
        result = await self._session.execute(query)
        problems = list(result.scalars().all())
        problems.sort(key=lambda p: _DIFFICULTY_ORDER.get(p.difficulty or "medium", 1))
        return problems[:limit]
