from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.cs.normalization import normalize_tag_name
from app.features.cs.problems.schemas import ProblemCreate, ProblemFilters, ProblemUpdate
from app.features.cs.problems.tables import CsTag, Problem

_PROBLEM_EXCLUDE = {"tags"}


class ProblemRepository:

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_problem(self, problem_id: int) -> Problem | None:
        result = await self._session.execute(
            select(Problem).options(selectinload(Problem.tags)).where(Problem.id == problem_id)
        )
        return result.scalars().first()

    async def get_problem_by_external_id(self, platform_id: int, external_id: str) -> Problem | None:
        result = await self._session.execute(
            select(Problem)
            .options(selectinload(Problem.tags))
            .where(Problem.platform_id == platform_id, Problem.external_id == external_id)
        )
        return result.scalars().first()

    async def get_problems(self, filters: ProblemFilters) -> list[Problem]:
        query = select(Problem).options(selectinload(Problem.tags))
        if filters.platform_id is not None:
            query = query.where(Problem.platform_id == filters.platform_id)
        if filters.difficulty is not None:
            query = query.where(Problem.difficulty == filters.difficulty)
        if filters.tag is not None:
            query = query.where(Problem.tags.any(CsTag.name == normalize_tag_name(filters.tag)))
        query = query.order_by(Problem.id)
        result = await self._session.execute(query)
        return list(result.scalars().all())

    async def _resolve_tags(self, tag_names: list[str]) -> list[CsTag]:
        tags = []
        for raw_name in tag_names:
            name = normalize_tag_name(raw_name)
            result = await self._session.execute(select(CsTag).where(CsTag.name == name))
            tag = result.scalars().first()
            if tag is None:
                tag = CsTag(name=name)
                self._session.add(tag)
            tags.append(tag)
        return tags

    async def create_problem(self, data: ProblemCreate) -> Problem:
        problem = Problem(**data.model_dump(exclude=_PROBLEM_EXCLUDE))
        problem.tags = await self._resolve_tags(data.tags)
        self._session.add(problem)
        await self._session.commit()
        return await self.get_problem(problem.id)

    async def update_problem(self, problem_id: int, data: ProblemUpdate) -> Problem | None:
        problem = await self.get_problem(problem_id)
        if problem is None:
            return None
        update_data = data.model_dump(exclude_unset=True)
        if "tags" in update_data:
            problem.tags = await self._resolve_tags(update_data.pop("tags"))
        for field, value in update_data.items():
            setattr(problem, field, value)
        await self._session.commit()
        return await self.get_problem(problem_id)

    async def upsert_problem(self, data: ProblemCreate) -> Problem:
        existing = await self.get_problem_by_external_id(data.platform_id, data.external_id)
        if existing is None:
            return await self.create_problem(data)
        return await self.update_problem(
            existing.id,
            ProblemUpdate(
                name=data.name,
                url=data.url,
                difficulty_raw=data.difficulty_raw,
                difficulty=data.difficulty,
                tags_raw=data.tags_raw,
                tags=data.tags,
            ),
        )
