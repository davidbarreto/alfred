import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.cs.study_plans.repository import StudyPlanRepository
from app.features.cs.study_plans.schemas import StudyPlanCreate, StudyPlanRead

logger = logging.getLogger(__name__)


class StudyPlanService:

    def __init__(self, session: AsyncSession) -> None:
        self._repo = StudyPlanRepository(session)

    async def get_plan(self, plan_id: int) -> StudyPlanRead | None:
        orm = await self._repo.get_plan(plan_id)
        return StudyPlanRead.model_validate(orm) if orm else None

    async def get_active_plan(self, cadence: str) -> StudyPlanRead | None:
        orm = await self._repo.get_active_plan(cadence)
        return StudyPlanRead.model_validate(orm) if orm else None

    async def create_plan(self, data: StudyPlanCreate) -> StudyPlanRead:
        orm = await self._repo.create_plan(data)
        logger.info(
            "Study plan created: id=%d cadence=%s items=%d", orm.id, orm.cadence, len(orm.items)
        )
        return StudyPlanRead.model_validate(orm)

    async def mark_item_done(self, item_id: int) -> bool:
        item = await self._repo.mark_item_done(item_id)
        if item is None:
            return False
        logger.info("Study plan item marked done: id=%d", item_id)
        return True

    async def auto_complete_items_for_problem(self, problem_id: int) -> None:
        completed = await self._repo.auto_complete_items_for_problem(problem_id)
        if completed:
            logger.info("Study plan items auto-completed: problem_id=%d count=%d", problem_id, completed)
