import datetime

from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.cs.study_plans.schemas import StudyPlanCreate
from app.features.cs.study_plans.tables import StudyPlan, StudyPlanItem


class StudyPlanRepository:

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_plan(self, plan_id: int) -> StudyPlan | None:
        result = await self._session.execute(
            select(StudyPlan).options(selectinload(StudyPlan.items)).where(StudyPlan.id == plan_id)
        )
        return result.scalars().first()

    async def get_active_plan(self, cadence: str) -> StudyPlan | None:
        result = await self._session.execute(
            select(StudyPlan)
            .options(selectinload(StudyPlan.items))
            .where(StudyPlan.cadence == cadence, StudyPlan.status == "active")
        )
        return result.scalars().first()

    async def create_plan(self, data: StudyPlanCreate) -> StudyPlan:
        existing_active = await self.get_active_plan(data.cadence)
        if existing_active is not None:
            existing_active.status = "superseded"

        plan = StudyPlan(cadence=data.cadence, period_start=data.period_start, rationale=data.rationale)
        plan.items = [
            StudyPlanItem(
                item_type=item.item_type,
                description=item.description,
                problem_id=item.problem_id,
                url=item.url,
                position=item.position,
            )
            for item in data.items
        ]
        self._session.add(plan)
        await self._session.commit()
        return await self.get_plan(plan.id)

    async def mark_item_done(self, item_id: int) -> StudyPlanItem | None:
        result = await self._session.execute(select(StudyPlanItem).where(StudyPlanItem.id == item_id))
        item = result.scalars().first()
        if item is None:
            return None
        item.is_done = True
        item.completed_at = datetime.datetime.now(datetime.timezone.utc)
        await self._session.commit()
        await self._session.refresh(item)
        return item

    async def auto_complete_items_for_problem(self, problem_id: int) -> int:
        result = await self._session.execute(
            select(StudyPlanItem).where(
                StudyPlanItem.problem_id == problem_id,
                StudyPlanItem.item_type == "problem",
                StudyPlanItem.is_done.is_(False),
            )
        )
        items = list(result.scalars().all())
        now = datetime.datetime.now(datetime.timezone.utc)
        for item in items:
            item.is_done = True
            item.completed_at = now
        if items:
            await self._session.commit()
        return len(items)
