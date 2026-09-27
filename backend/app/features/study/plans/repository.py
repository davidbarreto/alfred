import datetime

from sqlalchemy import case, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.features.study.plans.schemas import StudyPlanCreate, StudyPlanFilters
from app.features.study.plans.tables import StudyPlan, StudyPlanItem
from app.features.study.tags.repository import StudyTagRepository

_OPEN_STATUSES = ("backlog", "active")
_CLOSED_STATUSES = ("completed", "abandoned")
_PRIORITY_RANK = case({"high": 0, "medium": 1, "low": 2}, value=StudyPlan.priority, else_=3)
_WITH_ITEMS_AND_TAGS = (selectinload(StudyPlan.items), selectinload(StudyPlan.tags))


class StudyPlanRepository:

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._tags = StudyTagRepository(session)

    async def get_plan(self, plan_id: int) -> StudyPlan | None:
        result = await self._session.execute(
            select(StudyPlan).options(*_WITH_ITEMS_AND_TAGS).where(StudyPlan.id == plan_id)
        )
        return result.scalars().first()

    async def get_plans(self, filters: StudyPlanFilters) -> list[StudyPlan]:
        stmt = select(StudyPlan).options(*_WITH_ITEMS_AND_TAGS)
        if filters.status:
            stmt = stmt.where(StudyPlan.status == filters.status)
        if filters.closed is True:
            stmt = stmt.where(StudyPlan.status.in_(_CLOSED_STATUSES))
        elif filters.closed is False:
            stmt = stmt.where(StudyPlan.status.in_(_OPEN_STATUSES))
        if filters.track_id is not None:
            stmt = stmt.where(StudyPlan.track_id == filters.track_id)
        stmt = (
            stmt.order_by(StudyPlan.created_at.desc(), StudyPlan.id.desc())
            .limit(filters.limit)
            .offset(filters.offset)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_active_plans(self) -> list[StudyPlan]:
        result = await self._session.execute(
            select(StudyPlan)
            .options(*_WITH_ITEMS_AND_TAGS)
            .where(StudyPlan.status == "active")
            .order_by(StudyPlan.activated_at, StudyPlan.id)
        )
        return list(result.scalars().all())

    async def get_backlog_plans(self) -> list[StudyPlan]:
        """Next-to-activate first: highest priority, then oldest."""
        result = await self._session.execute(
            select(StudyPlan)
            .options(*_WITH_ITEMS_AND_TAGS)
            .where(StudyPlan.status == "backlog")
            .order_by(_PRIORITY_RANK, StudyPlan.created_at, StudyPlan.id)
        )
        return list(result.scalars().all())

    async def count_active_plans(self) -> int:
        result = await self._session.execute(
            select(func.count()).select_from(StudyPlan).where(StudyPlan.status == "active")
        )
        return result.scalar_one()

    async def create_plan(self, data: StudyPlanCreate, status: str) -> StudyPlan:
        plan = StudyPlan(
            track_id=data.track_id,
            title=data.title,
            goal=data.goal,
            priority=data.priority,
            status=status,
            activated_at=datetime.datetime.now(datetime.timezone.utc) if status == "active" else None,
        )
        plan.tags = await self._tags.resolve_tags(data.tags)
        plan.items = [
            StudyPlanItem(
                description=item.description,
                url=item.url,
                position=item.position,
                source_type=item.source_type,
                source_id=item.source_id,
                reason=item.reason,
            )
            for item in data.items
        ]
        self._session.add(plan)
        await self._session.commit()
        return await self.get_plan(plan.id)

    async def set_status(self, plan: StudyPlan, status: str) -> StudyPlan:
        now = datetime.datetime.now(datetime.timezone.utc)
        plan.status = status
        if status == "active":
            plan.activated_at = now
        if status == "completed":
            plan.completed_at = now
        await self._session.commit()
        return await self.get_plan(plan.id)

    async def delete_plan(self, plan_id: int) -> bool:
        result = await self._session.execute(delete(StudyPlan).where(StudyPlan.id == plan_id))
        await self._session.commit()
        return result.rowcount > 0

    async def get_tag_names(self) -> list[str]:
        return [tag.name for tag in await self._tags.get_tags()]

    async def mark_item_done(self, item_id: int) -> StudyPlanItem | None:
        result = await self._session.execute(select(StudyPlanItem).where(StudyPlanItem.id == item_id))
        item = result.scalars().first()
        if item is None:
            return None
        item.is_done = True
        await self._session.commit()
        await self._session.refresh(item)
        return item
