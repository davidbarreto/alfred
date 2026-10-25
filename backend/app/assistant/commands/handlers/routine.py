import logging
from typing import Any

from fastapi import HTTPException, status

from app.assistant.commands.handlers._utils import build_model, parse_int
from app.features.organizer.routines.schemas import (
    RoutineCreate,
    RoutineStepCreate,
    RoutineStepUpdate,
    RoutineUpdate,
)
from app.features.organizer.routines.service import RoutineConflictError, RoutineService, RoutineValidationError

logger = logging.getLogger(__name__)

_TRUE_VALUES = {"true", "1", "yes", "y"}
_FALSE_VALUES = {"false", "0", "no", "n"}
# Step fields copied as plain strings; an empty value clears them.
_STEP_TEXT_FIELDS = ("title", "anchor", "window_start", "window_end", "context", "location")


def _required_id(arguments: dict[str, Any], key: str) -> int:
    value = parse_int(arguments.get(key), key)
    if value is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{key} is required")
    return value


def _parse_bool(raw: Any, name: str) -> bool:
    value = str(raw).strip().lower()
    if value in _TRUE_VALUES:
        return True
    if value in _FALSE_VALUES:
        return False
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{name} must be true or false, got {raw!r}")


def _routine_fields(arguments: dict[str, Any]) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    if "name" in arguments:
        fields["name"] = arguments["name"]
    if "description" in arguments:
        fields["description"] = arguments["description"] or None
    if "active" in arguments:
        fields["active"] = _parse_bool(arguments["active"], "active")
    if "recurrence_rule" in arguments:
        fields["recurrence_rule"] = str(arguments["recurrence_rule"] or "").strip() or None
    if "starts_on" in arguments:
        fields["starts_on"] = str(arguments["starts_on"] or "").strip() or None
    return fields


def _step_fields(arguments: dict[str, Any]) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    for key in _STEP_TEXT_FIELDS:
        if key in arguments:
            value = str(arguments[key] or "").strip()
            fields[key] = (value.lower() if key in ("anchor", "context") else value) or None
    for key in ("duration_minutes", "offset_minutes", "checklist_note_id", "position"):
        if key in arguments:
            fields[key] = parse_int(arguments[key], key)
    return fields


def _raise_http(exc: ValueError) -> HTTPException:
    code = status.HTTP_409_CONFLICT if isinstance(exc, RoutineConflictError) else status.HTTP_422_UNPROCESSABLE_ENTITY
    return HTTPException(status_code=code, detail=str(exc))


async def handle_routine(command: str, arguments: dict[str, Any], service: RoutineService) -> Any:
    logger.debug("handle_routine: command=%s args_keys=%s", command, list(arguments.keys()))
    try:
        return await _dispatch(command, arguments, service)
    except (RoutineValidationError, RoutineConflictError) as exc:
        raise _raise_http(exc)


async def _dispatch(command: str, arguments: dict[str, Any], service: RoutineService) -> Any:
    if command == "add":
        payload = build_model(RoutineCreate, **_routine_fields(arguments))
        result = await service.create_routine(payload)
        return result.model_dump(mode="json")

    if command == "list":
        active = _parse_bool(arguments["active"], "active") if "active" in arguments else None
        results = await service.get_routines(active)
        return [r.model_dump(mode="json") for r in results]

    if command == "get":
        routine_id = _required_id(arguments, "id")
        routine = await service.get_routine(routine_id)
        if routine is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Routine {routine_id} not found")
        return routine.model_dump(mode="json")

    if command == "update":
        routine_id = _required_id(arguments, "id")
        routine = await service.update_routine(routine_id, build_model(RoutineUpdate, **_routine_fields(arguments)))
        if routine is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Routine {routine_id} not found")
        return routine.model_dump(mode="json")

    if command == "delete":
        routine_id = _required_id(arguments, "id")
        if not await service.delete_routine(routine_id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Routine {routine_id} not found")
        return {"deleted": True, "id": routine_id}

    if command == "add_step":
        routine_id = _required_id(arguments, "routine_id")
        payload = build_model(RoutineStepCreate, **_step_fields(arguments))
        step = await service.add_step(routine_id, payload)
        if step is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Routine {routine_id} not found")
        return step.model_dump(mode="json")

    if command == "update_step":
        step_id = _required_id(arguments, "id")
        step = await service.update_step(step_id, build_model(RoutineStepUpdate, **_step_fields(arguments)))
        if step is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Routine step {step_id} not found")
        return step.model_dump(mode="json")

    if command == "delete_step":
        step_id = _required_id(arguments, "id")
        if not await service.delete_step(step_id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Routine step {step_id} not found")
        return {"deleted": True, "id": step_id}

    if command == "attach":
        routine_id = _required_id(arguments, "id")
        event_id = _required_id(arguments, "event_id")
        routine = await service.attach(routine_id, event_id)
        if routine is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Routine {routine_id} not found")
        return routine.model_dump(mode="json")

    if command == "detach":
        event_id = _required_id(arguments, "event_id")
        if not await service.detach(event_id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Event {event_id} not found")
        return {"detached": True, "event_id": event_id}

    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown routine command: {command}")
