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
from app.shared.timezone import local_timezone

logger = logging.getLogger(__name__)


class SavedPlanValidationError(ValueError):
    """The plan is well-formed JSON but breaks a rule, e.g. a missing ref_id (maps to 422)."""


class SavedPlanConflictError(ValueError):
    """Another save for the same date won the race (maps to 409)."""


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
