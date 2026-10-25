import logging
from datetime import date
from typing import Any

from fastapi import HTTPException, status

from app.assistant.commands.handlers._utils import build_model, parse_int
from app.features.planning.schemas import PlanningSettingsUpdate
from app.features.planning.service import MAX_DAYS, DayPlanService
from app.features.planning.settings_service import PlanningSettingsService

logger = logging.getLogger(__name__)

_INT_SETTINGS = ("work_target_minutes", "office_days_per_week", "office_min_minutes")
_TEXT_SETTINGS = ("wake_time", "sleep_time", "work_tag", "office_tag")


def _parse_date(raw: Any) -> date | None:
    if raw is None or str(raw).strip() == "":
        return None
    try:
        return date.fromisoformat(str(raw).strip()[:10])
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"date must be YYYY-MM-DD, got {raw!r}")


def _settings_fields(arguments: dict[str, Any]) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    for key in _TEXT_SETTINGS:
        if key in arguments:
            fields[key] = str(arguments[key] or "").strip() or None
    for key in _INT_SETTINGS:
        if key in arguments:
            fields[key] = parse_int(arguments[key], key)
    if "preferred_work_windows" in arguments:
        raw = str(arguments["preferred_work_windows"] or "")
        fields["preferred_work_windows"] = [w.strip() for w in raw.split(",") if w.strip()] or None
    return fields


async def handle_day_plan(
    command: str,
    arguments: dict[str, Any],
    day_plan_service: DayPlanService,
    settings_service: PlanningSettingsService,
) -> Any:
    logger.debug("handle_day_plan: command=%s args_keys=%s", command, list(arguments.keys()))
    if command == "get":
        days = parse_int(arguments.get("days"), "days")
        if days is None:
            days = 1
        if not 1 <= days <= MAX_DAYS:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"days must be between 1 and {MAX_DAYS}")
        work_minutes = parse_int(arguments.get("work_minutes"), "work_minutes")
        if work_minutes is not None and not 0 <= work_minutes <= 1440:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="work_minutes must be between 0 and 1440")
        plan = await day_plan_service.get_plan(_parse_date(arguments.get("date")), days, work_minutes)
        return plan.model_dump(mode="json", exclude_none=True)

    if command == "settings":
        return (await settings_service.get()).model_dump(mode="json")

    if command == "set_settings":
        update = build_model(PlanningSettingsUpdate, **_settings_fields(arguments))
        if not update.model_fields_set:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No planning setting given")
        return (await settings_service.update(update)).model_dump(mode="json")

    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown day_plan command: {command}")
