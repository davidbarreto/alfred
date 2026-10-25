import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.organizer.routines.expansion import parse_recurrence
from app.features.organizer.routines.repository import RoutineRepository
from app.features.organizer.routines.schemas import (
    ChecklistNote,
    RoutineCreate,
    RoutineDetail,
    RoutineRead,
    RoutineStepBase,
    RoutineStepCreate,
    RoutineStepDetail,
    RoutineStepRead,
    RoutineStepUpdate,
    RoutineUpdate,
)
from app.features.organizer.routines.tables import Routine, RoutineStep

logger = logging.getLogger(__name__)

_RELATIVE_FIELDS = ("anchor", "offset_minutes")
_WINDOW_FIELDS = ("window_start", "window_end")


class RoutineValidationError(ValueError):
    """The request is well-formed but breaks a routine rule (maps to 422)."""


class RoutineConflictError(ValueError):
    """The request conflicts with existing data, e.g. a taken step position (maps to 409)."""


def _is_scheduled(routine: Routine) -> bool:
    return routine.recurrence_rule is not None


def _step_is_relative(step: RoutineStep) -> bool:
    return step.anchor is not None


def _validate_rule(recurrence_rule: str | None, starts_on) -> None:
    if recurrence_rule is None:
        return
    try:
        parse_recurrence(recurrence_rule, starts_on)
    except (ValueError, TypeError) as exc:
        raise RoutineValidationError(f"Invalid recurrence_rule {recurrence_rule!r}: {exc}") from exc


class RoutineService:

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = RoutineRepository(session)

    async def get_routines(self, active: bool | None = None) -> list[RoutineRead]:
        routines = await self._repo.get_routines(active)
        event_ids = await self._repo.get_event_ids_by_routine([r.id for r in routines])
        return [self._read(r, event_ids.get(r.id, [])) for r in routines]

    async def get_routine(self, routine_id: int) -> RoutineDetail | None:
        routine = await self._repo.get_routine(routine_id)
        if routine is None:
            return None
        event_ids = await self._repo.get_event_ids_by_routine([routine_id])
        notes = await self._repo.get_notes([s.checklist_note_id for s in routine.steps if s.checklist_note_id])
        steps = [
            RoutineStepDetail(
                **RoutineStepRead.model_validate(step).model_dump(),
                checklist_note=(
                    ChecklistNote(id=note.id, title=note.title, content=note.content)
                    if (note := notes.get(step.checklist_note_id)) is not None
                    else None
                ),
            )
            for step in routine.steps
        ]
        base = self._read(routine, event_ids.get(routine_id, []))
        return RoutineDetail(**{**base.model_dump(), "steps": steps})

    async def create_routine(self, data: RoutineCreate) -> RoutineRead:
        _validate_rule(data.recurrence_rule, data.starts_on)
        routine = await self._repo.create_routine(data)
        logger.info("Routine created: id=%d name=%r scheduled=%s", routine.id, routine.name, _is_scheduled(routine))
        return self._read(routine, [])

    async def update_routine(self, routine_id: int, data: RoutineUpdate) -> RoutineRead | None:
        routine = await self._repo.get_routine(routine_id)
        if routine is None:
            logger.debug("Routine update: id=%d not found", routine_id)
            return None
        changes = data.model_dump(exclude_unset=True)
        rule = changes.get("recurrence_rule", routine.recurrence_rule)
        starts_on = changes.get("starts_on", routine.starts_on)
        if (rule is None) != (starts_on is None):
            raise RoutineValidationError("recurrence_rule and starts_on must be set together (or both cleared)")
        _validate_rule(rule, starts_on)
        event_ids = (await self._repo.get_event_ids_by_routine([routine_id])).get(routine_id, [])
        if (rule is not None) != _is_scheduled(routine):
            self._check_kind_change(routine, scheduled=rule is not None, event_ids=event_ids)
        updated = await self._repo.update_routine(routine_id, data)
        logger.info("Routine updated: id=%d fields=%s", routine_id, list(changes.keys()))
        return self._read(updated, event_ids)

    async def delete_routine(self, routine_id: int) -> bool:
        if await self._repo.get_routine(routine_id) is None:
            logger.debug("Routine delete: id=%d not found", routine_id)
            return False
        await self._repo.delete_routine(routine_id)
        logger.info("Routine deleted: id=%d", routine_id)
        return True

    async def add_step(self, routine_id: int, data: RoutineStepCreate) -> RoutineStepRead | None:
        routine = await self._repo.get_routine(routine_id)
        if routine is None:
            logger.debug("Routine step add: routine_id=%d not found", routine_id)
            return None
        self._check_step_matches_kind(routine, data)
        await self._check_note(data.checklist_note_id)
        if data.position is None:
            position = await self._repo.next_position(routine_id)
        elif await self._repo.position_taken(routine_id, data.position):
            raise RoutineConflictError(f"Position {data.position} is already used in routine {routine_id}")
        else:
            position = data.position
        step = await self._repo.create_step(routine_id, position, RoutineStepBase(**data.model_dump(exclude={"position"})))
        logger.info("Routine step added: id=%d routine_id=%d title=%r", step.id, routine_id, step.title)
        return RoutineStepRead.model_validate(step)

    async def update_step(self, step_id: int, data: RoutineStepUpdate) -> RoutineStepRead | None:
        step = await self._repo.get_step(step_id)
        if step is None:
            logger.debug("Routine step update: id=%d not found", step_id)
            return None
        routine = await self._repo.get_routine(step.routine_id)
        changes = data.model_dump(exclude_unset=True)
        merged = self._merge_step(step, changes)
        try:
            validated = RoutineStepBase(**merged)
        except ValueError as exc:
            raise RoutineValidationError(str(exc)) from exc
        self._check_step_matches_kind(routine, validated)
        if "checklist_note_id" in changes:
            await self._check_note(validated.checklist_note_id)
        position = changes.get("position", step.position)
        if position is None:
            position = step.position
        if position != step.position and await self._repo.position_taken(step.routine_id, position, step_id):
            raise RoutineConflictError(f"Position {position} is already used in routine {step.routine_id}")
        updated = await self._repo.update_step(step, position, validated)
        logger.info("Routine step updated: id=%d fields=%s", step_id, list(changes.keys()))
        return RoutineStepRead.model_validate(updated)

    async def delete_step(self, step_id: int) -> bool:
        if await self._repo.get_step(step_id) is None:
            logger.debug("Routine step delete: id=%d not found", step_id)
            return False
        await self._repo.delete_step(step_id)
        logger.info("Routine step deleted: id=%d", step_id)
        return True

    async def attach(self, routine_id: int, event_id: int) -> RoutineRead | None:
        routine = await self._repo.get_routine(routine_id)
        if routine is None:
            logger.debug("Routine attach: routine_id=%d not found", routine_id)
            return None
        if _is_scheduled(routine):
            raise RoutineValidationError(
                "A scheduled routine runs on its own recurrence rule and cannot be attached to events"
            )
        if not await self._repo.event_exists(event_id):
            raise RoutineValidationError(f"Event {event_id} not found")
        await self._repo.set_event_routine(event_id, routine_id)
        logger.info("Routine attached: routine_id=%d event_id=%d", routine_id, event_id)
        event_ids = (await self._repo.get_event_ids_by_routine([routine_id])).get(routine_id, [])
        return self._read(routine, event_ids)

    async def detach(self, event_id: int) -> bool:
        if not await self._repo.event_exists(event_id):
            return False
        await self._repo.set_event_routine(event_id, None)
        logger.info("Routine detached: event_id=%d", event_id)
        return True

    def _read(self, routine: Routine, event_ids: list[int]) -> RoutineRead:
        base = RoutineRead.model_validate(routine)
        return base.model_copy(update={"event_ids": event_ids})

    @staticmethod
    def _merge_step(step: RoutineStep, changes: dict[str, Any]) -> dict[str, Any]:
        merged = {
            field: getattr(step, field)
            for field in (
                "title", "duration_minutes", "anchor", "offset_minutes", "window_start", "window_end",
                "context", "location", "checklist_note_id",
            )
        }
        merged.update({k: v for k, v in changes.items() if k != "position"})
        # Switching timing form: setting one form clears the other unless that one is also being set.
        if any(f in changes for f in _RELATIVE_FIELDS) and not any(f in changes for f in _WINDOW_FIELDS):
            merged.update(window_start=None, window_end=None)
        if any(f in changes for f in _WINDOW_FIELDS) and not any(f in changes for f in _RELATIVE_FIELDS):
            merged.update(anchor=None, offset_minutes=None)
        if merged.get("title") is None:
            raise RoutineValidationError("title cannot be null")
        if merged.get("duration_minutes") is None:
            merged["duration_minutes"] = 0
        return merged

    @staticmethod
    def _check_step_matches_kind(routine: Routine, step: RoutineStepBase) -> None:
        relative = step.anchor is not None
        if _is_scheduled(routine) and relative:
            raise RoutineValidationError(
                "Steps of a scheduled routine need window_start and window_end (it has a recurrence rule)"
            )
        if not _is_scheduled(routine) and not relative:
            raise RoutineValidationError(
                "Steps of an event-attached routine need anchor (start/end) and offset_minutes"
            )

    @staticmethod
    def _check_kind_change(routine: Routine, scheduled: bool, event_ids: list[int]) -> None:
        if scheduled and event_ids:
            raise RoutineValidationError(
                f"Routine {routine.id} is attached to events {event_ids}; detach them before adding a recurrence rule"
            )
        wrong_form = [s.id for s in routine.steps if _step_is_relative(s) == scheduled]
        if wrong_form:
            wanted = "window_start/window_end" if scheduled else "anchor/offset_minutes"
            raise RoutineValidationError(
                f"Steps {wrong_form} must use {wanted} before the routine can change kind"
            )

    async def _check_note(self, note_id: int | None) -> None:
        if note_id is not None and not await self._repo.note_exists(note_id):
            raise RoutineValidationError(f"Checklist note {note_id} not found")
