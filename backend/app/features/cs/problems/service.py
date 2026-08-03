import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.cs.problems.repository import ProblemRepository
from app.features.cs.problems.schemas import (
    AttemptedProblemFilters,
    AttemptedProblemRead,
    ProblemCreate,
    ProblemFilters,
    ProblemRead,
    ProblemUpdate,
)

logger = logging.getLogger(__name__)


class ProblemService:

    def __init__(self, session: AsyncSession) -> None:
        self._repo = ProblemRepository(session)

    async def get_problem(self, problem_id: int) -> ProblemRead | None:
        orm = await self._repo.get_problem(problem_id)
        return ProblemRead.model_validate(orm) if orm else None

    async def get_problems(self, filters: ProblemFilters) -> list[ProblemRead]:
        problems = await self._repo.get_problems(filters)
        return [ProblemRead.model_validate(p) for p in problems]

    async def get_all_tag_names(self) -> list[str]:
        return await self._repo.get_all_tag_names()

    async def get_problems_by_platform(self, platform_id: int) -> list[ProblemRead]:
        problems = await self._repo.get_problems_by_platform(platform_id)
        return [ProblemRead.model_validate(p) for p in problems]

    async def get_attempted_problems(self, filters: AttemptedProblemFilters) -> list[AttemptedProblemRead]:
        rows = await self._repo.get_attempted_problems(filters)
        return [
            AttemptedProblemRead(
                **ProblemRead.model_validate(problem).model_dump(),
                attempts=attempts,
                solved=solved,
                last_attempted_at=last_attempted_at,
            )
            for problem, attempts, solved, last_attempted_at in rows
        ]

    async def create_problem(self, data: ProblemCreate) -> ProblemRead:
        orm = await self._repo.create_problem(data)
        logger.info("Problem created: id=%d external_id=%r", orm.id, orm.external_id)
        return ProblemRead.model_validate(orm)

    async def update_problem(self, problem_id: int, data: ProblemUpdate) -> ProblemRead | None:
        orm = await self._repo.update_problem(problem_id, data)
        if orm is None:
            return None
        logger.info("Problem updated: id=%d fields=%s", problem_id, list(data.model_dump(exclude_unset=True).keys()))
        return ProblemRead.model_validate(orm)

    async def upsert_problem(self, data: ProblemCreate) -> ProblemRead:
        orm = await self._repo.upsert_problem(data)
        logger.debug("Problem upserted: platform_id=%d external_id=%r", data.platform_id, data.external_id)
        return ProblemRead.model_validate(orm)
