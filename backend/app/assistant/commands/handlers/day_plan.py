import json
import logging
from datetime import date
from typing import Any

from fastapi import HTTPException, status

from app.assistant.commands.handlers._utils import build_model, parse_int
from app.features.planning.saved_plans.schemas import DayPlansSave
from app.features.planning.saved_plans.service import (
    SavedPlanConflictError,
    SavedPlanNotFoundError,
    SavedPlanService,
    SavedPlanValidationError,
)
from app.features.planning.schemas import PlanningSettingsUpdate
from app.features.planning.service import MAX_DAYS, DayPlanService
from app.features.planning.settings_service import PlanningSettingsService

logger = logging.getLogger(__name__)

_PORTAL_SOURCES = {"web", "portal"}
_INT_SETTINGS = ("work_target_minutes", "office_days_per_week", "office_min_minutes")
_LIST_SETTINGS = ("preferred_work_windows", "workdays")
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
    for key in _LIST_SETTINGS:
        if key in arguments:
            raw = str(arguments[key] or "")
            fields[key] = [item.strip() for item in raw.split(",") if item.strip()] or None
    return fields


def _parse_days_json(raw: Any) -> dict[str, Any]:
    """The `days` argument of save: a JSON string (MCP params are strings) holding a list of day objects."""
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=f"days must be valid JSON: {exc.msg} (line {exc.lineno}, column {exc.colno})"
            )
    if not isinstance(raw, list):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='days must be a JSON list like [{"date": "2026-10-21", "items": [...], "notes": "..."}]',
        )
    return {"days": raw}


def _required_date(arguments: dict[str, Any], key: str) -> date:
    parsed = _parse_date(arguments.get(key))
    if parsed is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{key} is required (YYYY-MM-DD)")
    return parsed


async def handle_day_plan(
    command: str,
    arguments: dict[str, Any],
    day_plan_service: DayPlanService,
    settings_service: PlanningSettingsService,
    saved_plan_service: SavedPlanService,
    source: str | None = None,
) -> Any:
    logger.debug("handle_day_plan: command=%s args_keys=%s", command, list(arguments.keys()))
    try:
        return await _dispatch(command, arguments, day_plan_service, settings_service, saved_plan_service, source)
    except SavedPlanValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    except SavedPlanConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    except SavedPlanNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


async def _dispatch(
    command: str,
    arguments: dict[str, Any],
    day_plan_service: DayPlanService,
    settings_service: PlanningSettingsService,
    saved_plan_service: SavedPlanService,
    source: str | None,
) -> Any:
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

    if command == "save":
        payload = build_model(DayPlansSave, **_parse_days_json(arguments.get("days")))
        plans = await saved_plan_service.save(payload, "portal" if source in _PORTAL_SOURCES else "mcp")
        return [p.model_dump(mode="json") for p in plans]

    if command == "get_saved":
        start = _required_date(arguments, "from")
        end = _parse_date(arguments.get("to")) or start
        version = parse_int(arguments.get("version"), "version")
        plans = await saved_plan_service.get_saved(start, end, version)
        return [p.model_dump(mode="json") for p in plans]

    if command == "history":
        plans = await saved_plan_service.get_history(_required_date(arguments, "date"))
        return [p.model_dump(mode="json") for p in plans]

    if command in ("miss", "unmiss"):
        plan = await saved_plan_service.set_missed_on(
            _required_date(arguments, "date"),
            command == "miss",
            kind=str(arguments.get("kind") or "task"),
            ref_id=parse_int(arguments.get("ref_id"), "ref_id"),
            title=str(arguments["title"]) if arguments.get("title") else None,
            start=str(arguments["start"]) if arguments.get("start") else None,
        )
        return plan.model_dump(mode="json")

    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown day_plan command: {command}")
