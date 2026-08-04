import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.cs.study_plans.repository import StudyPlanRepository
from app.features.cs.study_plans.schemas import StudyPlanCreate, StudyPlanFilters, StudyPlanRead

logger = logging.getLogger(__name__)

_STATUS_COMPLETED = "completed"
_STATUS_ABANDONED = "abandoned"


class ActivePlanIncompleteError(Exception):
    """Raised when generating a new plan would replace an active plan that still has
    unfinished items -- the caller must confirm (force=True) before it's abandoned."""

    def __init__(self, plan: StudyPlanRead) -> None:
        self.plan = plan
        incomplete = sum(1 for item in plan.items if not item.is_done)
        super().__init__(f"Active plan {plan.id} has {incomplete} incomplete item(s)")


class StudyPlanService:

    def __init__(self, session: AsyncSession) -> None:
        self._repo = StudyPlanRepository(session)

    async def get_plan(self, plan_id: int) -> StudyPlanRead | None:
        orm = await self._repo.get_plan(plan_id)
        return StudyPlanRead.model_validate(orm) if orm else None

    async def get_active_plan(self, cadence: str) -> StudyPlanRead | None:
        orm = await self._repo.get_active_plan(cadence)
        return StudyPlanRead.model_validate(orm) if orm else None

    async def get_plans(self, filters: StudyPlanFilters) -> list[StudyPlanRead]:
        orms = await self._repo.get_plans(filters)
        return [StudyPlanRead.model_validate(orm) for orm in orms]

    async def create_plan(self, data: StudyPlanCreate, force: bool = False) -> StudyPlanRead:
        existing = await self._repo.get_active_plan(data.cadence)
        previous_status = _STATUS_COMPLETED
        if existing is not None and any(not item.is_done for item in existing.items):
            if not force:
                raise ActivePlanIncompleteError(StudyPlanRead.model_validate(existing))
            previous_status = _STATUS_ABANDONED

        orm = await self._repo.create_plan(data, previous_status=previous_status)
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
