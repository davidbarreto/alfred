import logging
from typing import Any

from fastapi import HTTPException, status

from app.assistant.commands.handlers._utils import build_model, parse_dt, parse_int, parse_tags
from app.features.organizer.activities.schemas import (
    ActivityCreate,
    ActivityFilters,
    ActivityLogCreate,
    ActivityUpdate,
)
from app.features.organizer.activities.service import ActivityService, ActivityStateError, ActivityValidationError

logger = logging.getLogger(__name__)

_TRUE_VALUES = {"true", "1", "yes", "y"}
_FALSE_VALUES = {"false", "0", "no", "n"}


def _required_id(arguments: dict[str, Any]) -> int:
    value = parse_int(arguments.get("id"), "id")
    if value is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="id is required")
    return value


def _flag(raw: Any, name: str) -> bool:
    value = str(raw).strip().lower()
    if value in _TRUE_VALUES:
        return True
    if value in _FALSE_VALUES:
        return False
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{name} must be true or false, got {raw!r}")


def _activity_fields(arguments: dict[str, Any]) -> dict[str, Any]:
    """Activity columns present in the arguments; an empty value clears an optional field."""
    fields: dict[str, Any] = {}
    if "title" in arguments:
        fields["title"] = str(arguments["title"] or "").strip() or None
    for argument, column in (("min_minutes", "min_minutes"), ("max_minutes", "max_minutes"), ("target_per_week", "target_per_week")):
        if argument in arguments:
            fields[column] = parse_int(arguments[argument], argument)
    if "context" in arguments:
        fields["context"] = str(arguments["context"] or "").strip().lower() or None
    if "tags" in arguments:
        fields["tags"] = parse_tags(arguments["tags"])
    return fields


async def handle_activity(command: str, arguments: dict[str, Any], service: ActivityService) -> Any:
    logger.debug("handle_activity: command=%s args_keys=%s", command, list(arguments.keys()))
    try:
        return await _dispatch(command, arguments, service)
    except ActivityValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    except ActivityStateError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))


async def _dispatch(command: str, arguments: dict[str, Any], service: ActivityService) -> Any:
    if command == "add":
        payload = build_model(ActivityCreate, **{"title": arguments.get("title", ""), **_activity_fields(arguments)})
        return (await service.create_activity(payload)).model_dump(mode="json")

    if command == "list":
        include_archived = _flag(arguments["archived"], "archived") if "archived" in arguments else False
        filters = ActivityFilters(
            include_archived=include_archived,
            tag=str(arguments["tag"]).strip() or None if "tag" in arguments else None,
            q=str(arguments["search"]).strip() or None if "search" in arguments else None,
            limit=parse_int(arguments.get("limit"), "limit") or 200,
        )
        return [a.model_dump(mode="json") for a in await service.get_activities(filters)]

    if command == "update":
        activity_id = _required_id(arguments)
        result = await service.update_activity(activity_id, build_model(ActivityUpdate, **_activity_fields(arguments)))
        if result is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Activity {activity_id} not found")
        return result.model_dump(mode="json")

    if command in ("archive", "unarchive"):
        activity_id = _required_id(arguments)
        action = service.archive if command == "archive" else service.unarchive
        result = await action(activity_id)
        if result is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Activity {activity_id} not found")
        return result.model_dump(mode="json")

    if command == "log":
        activity_id = _required_id(arguments)
        raw_at = arguments.get("done_at")
        done_at = parse_dt(raw_at)
        if raw_at and done_at is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"done_at must be an ISO datetime, got {raw_at!r}")
        payload = build_model(
            ActivityLogCreate,
            done_at=done_at,
            minutes=parse_int(arguments.get("minutes"), "minutes"),
            note=arguments.get("note") or None,
        )
        log = await service.log(activity_id, payload)
        if log is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Activity {activity_id} not found")
        return log.model_dump(mode="json")

    if command == "history":
        activity_id = _required_id(arguments)
        logs = await service.get_history(
            activity_id,
            parse_int(arguments.get("limit"), "limit") or 50,
            parse_int(arguments.get("offset"), "offset") or 0,
        )
        if logs is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Activity {activity_id} not found")
        return [log.model_dump(mode="json") for log in logs]

    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown activity command: {command}")
