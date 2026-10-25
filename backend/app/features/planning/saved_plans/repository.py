from datetime import date
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.organizer.calendar_events.tables import CalendarEvent
from app.features.organizer.routines.tables import RoutineStep
from app.features.organizer.tasks.tables import Task
from app.features.planning.saved_plans.tables import DayPlan
from app.features.study.plans.tables import StudyPlanItem


class DayPlanRepository:

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_active_plans(self, start: date, end: date) -> list[DayPlan]:
        result = await self._session.execute(
            select(DayPlan)
            .where(DayPlan.plan_date >= start, DayPlan.plan_date <= end, DayPlan.archived_at.is_(None))
            .order_by(DayPlan.plan_date)
        )
        return list(result.scalars().all())

    async def get_plans_by_version(self, start: date, end: date, version: int) -> list[DayPlan]:
        result = await self._session.execute(
            select(DayPlan)
            .where(DayPlan.plan_date >= start, DayPlan.plan_date <= end, DayPlan.version == version)
            .order_by(DayPlan.plan_date)
        )
        return list(result.scalars().all())

    async def get_history(self, plan_date: date) -> list[DayPlan]:
        result = await self._session.execute(
            select(DayPlan).where(DayPlan.plan_date == plan_date).order_by(DayPlan.version.desc())
        )
        return list(result.scalars().all())

    async def save_days(self, entries: list[tuple[date, list[dict[str, Any]], str | None]], source: str) -> list[DayPlan]:
        """Archive each date's active plan and insert the next version, all in one transaction."""
        saved = []
        try:
            for plan_date, items, notes in entries:
                await self._session.execute(
                    update(DayPlan)
                    .where(DayPlan.plan_date == plan_date, DayPlan.archived_at.is_(None))
                    .values(archived_at=func.now())
                )
                highest = (
                    await self._session.execute(select(func.max(DayPlan.version)).where(DayPlan.plan_date == plan_date))
                ).scalar()
                plan = DayPlan(
                    plan_date=plan_date, version=(highest or 0) + 1, items=items, notes=notes, source=source
                )
                self._session.add(plan)
                saved.append(plan)
                await self._session.flush()
            await self._session.commit()
        except Exception:
            await self._session.rollback()
            raise
        return saved

    async def existing_ref_ids(self, kind: str, ids: set[int]) -> set[int]:
        """Which of `ids` exist in the table that `kind` points at (activities are checked by a later phase)."""
        if not ids:
            return set()
        column = _REF_COLUMNS.get(kind)
        if column is None:
            return set(ids)
        query = select(column).where(column.in_(ids))
        if kind == "task":
            query = query.where(Task.deleted_at.is_(None))
        result = await self._session.execute(query)
        return set(result.scalars().all())


_REF_COLUMNS = {
    "event": CalendarEvent.id,
    "task": Task.id,
    "study_item": StudyPlanItem.id,
    "routine_step": RoutineStep.id,
    "routine_block": RoutineStep.id,
}
