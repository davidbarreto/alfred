import logging
from datetime import date

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.planning.saved_plans.repository import DayPlanRepository
from app.features.planning.saved_plans.schemas import (
    MAX_RANGE_DAYS,
    REF_KINDS,
    DayPlansSave,
    PlanBlock,
    SavedDayPlanRead,
)
from app.features.planning.timeline import iso_local
from app.shared.timezone import local_now, local_timezone

logger = logging.getLogger(__name__)


class SavedPlanValidationError(ValueError):
    """The plan is well-formed JSON but breaks a rule, e.g. a missing ref_id (maps to 422)."""


class SavedPlanConflictError(ValueError):
    """Another save for the same date won the race, or the plan is already in the requested state (maps to 409)."""


class SavedPlanNotFoundError(ValueError):
    """No saved plan with that id (maps to 404)."""


class SavedPlanService:

    def __init__(self, session: AsyncSession) -> None:
        self._repo = DayPlanRepository(session)

    async def save(self, data: DayPlansSave, source: str) -> list[SavedDayPlanRead]:
        dates = [day.date for day in data.days]
        duplicates = sorted({d for d in dates if dates.count(d) > 1})
        if duplicates:
            raise SavedPlanValidationError(
                "Each date can appear once per call; repeated: " + ", ".join(d.isoformat() for d in duplicates)
            )
        problems = _date_problems(data) + await self._ref_problems(data)
        if problems:
            raise SavedPlanValidationError("; ".join(problems))

        entries = [
            (day.date, [_block_dict(block) for block in sorted(day.items, key=lambda b: b.start)], day.notes)
            for day in data.days
        ]
        try:
            plans = await self._repo.save_days(entries, source)
        except IntegrityError as exc:
            raise SavedPlanConflictError("Another save for one of these dates ran at the same time; try again") from exc
        logger.info(
            "Day plans saved: dates=%s versions=%s source=%s",
            [p.plan_date.isoformat() for p in plans], [p.version for p in plans], source,
        )
        return [SavedDayPlanRead.model_validate(p) for p in plans]

    async def get_saved(self, start: date, end: date, version: int | None = None) -> list[SavedDayPlanRead]:
        if end < start:
            raise SavedPlanValidationError("'to' must not be before 'from'")
        if (end - start).days + 1 > MAX_RANGE_DAYS:
            raise SavedPlanValidationError(f"The range can cover at most {MAX_RANGE_DAYS} days")
        if version is None:
            plans = await self._repo.get_active_plans(start, end)
        else:
            plans = await self._repo.get_plans_by_version(start, end, version)
        logger.debug("Saved plans read: from=%s to=%s version=%s count=%d", start, end, version, len(plans))
        return [SavedDayPlanRead.model_validate(p) for p in plans]

    async def get_history(self, plan_date: date) -> list[SavedDayPlanRead]:
        return [SavedDayPlanRead.model_validate(p) for p in await self._repo.get_history(plan_date)]

    async def archive(self, plan_id: int) -> SavedDayPlanRead:
        plan = await self._get_or_raise(plan_id)
        if plan.archived_at is not None:
            raise SavedPlanConflictError("This version is already archived")
        plan = await self._repo.archive_plan(plan)
        logger.info("Day plan archived: id=%d date=%s version=%d", plan.id, plan.plan_date, plan.version)
        return SavedDayPlanRead.model_validate(plan)

    async def restore(self, plan_id: int) -> SavedDayPlanRead:
        plan = await self._get_or_raise(plan_id)
        if plan.archived_at is None:
            raise SavedPlanConflictError("This version is already the active plan")
        try:
            plan = await self._repo.restore_plan(plan)
        except IntegrityError as exc:
            raise SavedPlanConflictError("Another save for this date ran at the same time; try again") from exc
        logger.info("Day plan restored: id=%d date=%s version=%d", plan.id, plan.plan_date, plan.version)
        return SavedDayPlanRead.model_validate(plan)

    async def set_block_missed(self, plan_id: int, index: int, missed: bool) -> SavedDayPlanRead:
        """Record that a block was not done, or undo that. The plan stays as it was saved; only the block is flagged."""
        plan = await self._get_or_raise(plan_id)
        if not 0 <= index < len(plan.items):
            raise SavedPlanNotFoundError(f"Saved plan {plan_id} has no block {index}")
        plan = await self._repo.set_block_missed(plan, index, iso_local(local_now()) if missed else None)
        logger.info(
            "Day plan block %s: id=%d date=%s block=%d", "missed" if missed else "unmissed", plan.id, plan.plan_date, index
        )
        return SavedDayPlanRead.model_validate(plan)

    async def set_missed_on(
        self, plan_date: date, missed: bool, kind: str = "task", ref_id: int | None = None,
        title: str | None = None, start: str | None = None,
    ) -> SavedDayPlanRead:
        """Flag (or unflag) the block of the date's active plan that matches kind + ref_id, or a part of the title.

        `start` (HH:MM, local) picks one when the same thing is planned more than once that day.
        """
        if ref_id is None and not title:
            raise SavedPlanValidationError("Give the ref_id of the block, or part of its title")
        plans = await self._repo.get_active_plans(plan_date, plan_date)
        if not plans:
            raise SavedPlanNotFoundError(f"No active plan saved for {plan_date.isoformat()}")
        plan = plans[0]
        matches = [
            index for index, item in enumerate(plan.items)
            if _block_matches(item, kind, ref_id, title, start)
        ]
        if not matches:
            raise SavedPlanNotFoundError(f"No matching block in the plan of {plan_date.isoformat()}")
        if len(matches) > 1:
            times = ", ".join(plan.items[i]["start"][11:16] for i in matches)
            raise SavedPlanValidationError(f"{len(matches)} blocks match (starting at {times}); pass start as HH:MM to pick one")
        return await self.set_block_missed(plan.id, matches[0], missed)

    async def delete(self, plan_id: int) -> None:
        plan = await self._get_or_raise(plan_id)
        await self._repo.delete_plan(plan_id)
        logger.info("Day plan deleted: id=%d date=%s version=%d", plan.id, plan.plan_date, plan.version)

    async def _get_or_raise(self, plan_id: int):
        plan = await self._repo.get_plan(plan_id)
        if plan is None:
            logger.debug("Day plan not found: id=%d", plan_id)
            raise SavedPlanNotFoundError(f"Saved plan {plan_id} not found")
        return plan

    async def _ref_problems(self, data: DayPlansSave) -> list[str]:
        wanted: dict[str, set[int]] = {}
        for day in data.days:
            for block in day.items:
                if block.ref_id is not None and block.kind in REF_KINDS:
                    wanted.setdefault(block.kind, set()).add(block.ref_id)
        problems = []
        for kind, ids in sorted(wanted.items()):
            missing = sorted(ids - await self._repo.existing_ref_ids(kind, ids))
            if missing:
                problems.append(f"Unknown {kind} ref_id(s): {', '.join(str(i) for i in missing)}")
        return problems


def _block_matches(item: dict, kind: str, ref_id: int | None, title: str | None, start: str | None) -> bool:
    if ref_id is not None:
        if item["kind"] != kind or item["ref_id"] != ref_id:
            return False
    elif title.lower() not in item["title"].lower():
        return False
    return start is None or item["start"][11:16] == start


def _date_problems(data: DayPlansSave) -> list[str]:
    problems = []
    for day in data.days:
        for block in day.items:
            local_date = block.start.astimezone(local_timezone()).date()
            if local_date != day.date:
                problems.append(
                    f"Block '{block.title}' starts on {local_date.isoformat()}, not on {day.date.isoformat()}"
                )
    return problems


def _block_dict(block: PlanBlock) -> dict:
    return {
        "start": iso_local(block.start),
        "end": iso_local(block.end),
        "kind": block.kind,
        "ref_id": block.ref_id,
        "title": block.title,
        "note": block.note,
    }
