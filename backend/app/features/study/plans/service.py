import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.study.plans.repository import StudyPlanRepository
from app.features.study.plans.schemas import StudyPlanCreate, StudyPlanFilters, StudyPlanRead, StudyPlansOverview
from app.features.study.settings.service import StudySettingsService

logger = logging.getLogger(__name__)

# Which statuses each action may start from.
_ALLOWED_TRANSITIONS = {
    "activate": {"backlog"},
    "complete": {"active"},
    "abandon": {"active", "backlog"},
}


class ActivePlanCapReachedError(Exception):
    """Raised when activating a plan would exceed the global max_active_plans cap."""

    def __init__(self, max_active_plans: int) -> None:
        self.max_active_plans = max_active_plans
        super().__init__(f"Already at the limit of {max_active_plans} active study plan(s)")


class InvalidPlanTransitionError(Exception):
    """Raised when a plan action doesn't apply to the plan's current status."""

    def __init__(self, plan_id: int, status: str, action: str) -> None:
        self.plan_id = plan_id
        self.status = status
        self.action = action
        super().__init__(f"Cannot {action} plan {plan_id}: it is {status}")


class StudyPlanService:

    def __init__(self, session: AsyncSession) -> None:
        self._repo = StudyPlanRepository(session)
        self._settings = StudySettingsService(session)

    async def get_plan(self, plan_id: int) -> StudyPlanRead | None:
        orm = await self._repo.get_plan(plan_id)
        return StudyPlanRead.model_validate(orm) if orm else None

    async def get_plans(self, filters: StudyPlanFilters) -> list[StudyPlanRead]:
        orms = await self._repo.get_plans(filters)
        return [StudyPlanRead.model_validate(orm) for orm in orms]

    async def get_active_plans(self) -> list[StudyPlanRead]:
        orms = await self._repo.get_active_plans()
        return [StudyPlanRead.model_validate(orm) for orm in orms]

    async def get_tag_names(self) -> list[str]:
        return await self._repo.get_tag_names()

    async def get_overview(self) -> StudyPlansOverview:
        active = await self._repo.get_active_plans()
        backlog = await self._repo.get_backlog_plans()
        return StudyPlansOverview(
            active=[StudyPlanRead.model_validate(orm) for orm in active],
            backlog=[StudyPlanRead.model_validate(orm) for orm in backlog],
            max_active_plans=await self._settings.get_max_active_plans(),
        )

    async def create_plan(self, data: StudyPlanCreate) -> StudyPlanRead:
        """New plans go straight to active while under the cap, otherwise to the backlog."""
        max_active = await self._settings.get_max_active_plans()
        active_count = await self._repo.count_active_plans()
        status = "active" if active_count < max_active else "backlog"
        orm = await self._repo.create_plan(data, status=status)
        logger.info(
            "Study plan created: id=%d title=%r status=%s items=%d", orm.id, orm.title, orm.status, len(orm.items)
        )
        return StudyPlanRead.model_validate(orm)

    async def activate_plan(self, plan_id: int) -> StudyPlanRead | None:
        orm = await self._get_for_action(plan_id, "activate")
        if orm is None:
            return None
        max_active = await self._settings.get_max_active_plans()
        if await self._repo.count_active_plans() >= max_active:
            raise ActivePlanCapReachedError(max_active)
        orm = await self._repo.set_status(orm, "active")
        logger.info("Study plan activated: id=%d title=%r", orm.id, orm.title)
        return StudyPlanRead.model_validate(orm)

    async def complete_plan(self, plan_id: int) -> StudyPlanRead | None:
        orm = await self._get_for_action(plan_id, "complete")
        if orm is None:
            return None
        orm = await self._repo.set_status(orm, "completed")
        logger.info("Study plan completed: id=%d title=%r", orm.id, orm.title)
        return StudyPlanRead.model_validate(orm)

    async def abandon_plan(self, plan_id: int) -> StudyPlanRead | None:
        orm = await self._get_for_action(plan_id, "abandon")
        if orm is None:
            return None
        orm = await self._repo.set_status(orm, "abandoned")
        logger.info("Study plan abandoned: id=%d title=%r", orm.id, orm.title)
        return StudyPlanRead.model_validate(orm)

    async def delete_plan(self, plan_id: int) -> bool:
        deleted = await self._repo.delete_plan(plan_id)
        if deleted:
            logger.info("Study plan deleted: id=%d", plan_id)
        else:
            logger.debug("Study plan delete: id=%d not found", plan_id)
        return deleted

    async def mark_item_done(self, item_id: int) -> bool:
        item = await self._repo.mark_item_done(item_id)
        if item is None:
            logger.debug("Study plan item complete: id=%d not found", item_id)
            return False
        logger.info("Study plan item marked done: id=%d plan_id=%d", item_id, item.plan_id)
        return True

    async def _get_for_action(self, plan_id: int, action: str):
        orm = await self._repo.get_plan(plan_id)
        if orm is None:
            logger.debug("Study plan %s: id=%d not found", action, plan_id)
            return None
        if orm.status not in _ALLOWED_TRANSITIONS[action]:
            raise InvalidPlanTransitionError(plan_id, orm.status, action)
        return orm
