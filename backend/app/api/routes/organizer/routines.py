from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.api.auth import require_auth
from app.dependencies import RoutineServiceDep
from app.features.organizer.routines.schemas import (
    RoutineCreate,
    RoutineDetail,
    RoutineFilters,
    RoutineRead,
    RoutineStepCreate,
    RoutineStepRead,
    RoutineStepUpdate,
    RoutineUpdate,
)
from app.features.organizer.routines.service import RoutineConflictError, RoutineValidationError

router = APIRouter(prefix="/organizer/routines", tags=["organizer"], dependencies=[Depends(require_auth)])

_NOT_FOUND = HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Routine not found")
_STEP_NOT_FOUND = HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Routine step not found")


def _http_error(exc: ValueError) -> HTTPException:
    code = status.HTTP_409_CONFLICT if isinstance(exc, RoutineConflictError) else status.HTTP_422_UNPROCESSABLE_ENTITY
    return HTTPException(status_code=code, detail=str(exc))


@router.get("", response_model=list[RoutineRead])
async def get_routines(service: RoutineServiceDep, filters: RoutineFilters = Depends()):
    return await service.get_routines(filters.active)


@router.post("", response_model=RoutineRead, status_code=status.HTTP_201_CREATED)
async def create_routine(request: RoutineCreate, service: RoutineServiceDep):
    try:
        return await service.create_routine(request)
    except RoutineValidationError as exc:
        raise _http_error(exc)


@router.patch("/steps/{step_id}", response_model=RoutineStepRead)
async def update_step(step_id: int, request: RoutineStepUpdate, service: RoutineServiceDep):
    try:
        step = await service.update_step(step_id, request)
    except (RoutineValidationError, RoutineConflictError) as exc:
        raise _http_error(exc)
    if step is None:
        raise _STEP_NOT_FOUND
    return step


@router.delete("/steps/{step_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_step(step_id: int, service: RoutineServiceDep):
    if not await service.delete_step(step_id):
        raise _STEP_NOT_FOUND
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/events/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
async def detach_event(event_id: int, service: RoutineServiceDep):
    if not await service.detach(event_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{routine_id}", response_model=RoutineDetail)
async def get_routine(routine_id: int, service: RoutineServiceDep):
    routine = await service.get_routine(routine_id)
    if routine is None:
        raise _NOT_FOUND
    return routine


@router.patch("/{routine_id}", response_model=RoutineRead)
async def update_routine(routine_id: int, request: RoutineUpdate, service: RoutineServiceDep):
    try:
        routine = await service.update_routine(routine_id, request)
    except RoutineValidationError as exc:
        raise _http_error(exc)
    if routine is None:
        raise _NOT_FOUND
    return routine


@router.delete("/{routine_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_routine(routine_id: int, service: RoutineServiceDep):
    if not await service.delete_routine(routine_id):
        raise _NOT_FOUND
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{routine_id}/steps", response_model=RoutineStepRead, status_code=status.HTTP_201_CREATED)
async def add_step(routine_id: int, request: RoutineStepCreate, service: RoutineServiceDep):
    try:
        step = await service.add_step(routine_id, request)
    except (RoutineValidationError, RoutineConflictError) as exc:
        raise _http_error(exc)
    if step is None:
        raise _NOT_FOUND
    return step


@router.post("/{routine_id}/events/{event_id}", response_model=RoutineRead)
async def attach_event(routine_id: int, event_id: int, service: RoutineServiceDep):
    try:
        routine = await service.attach(routine_id, event_id)
    except RoutineValidationError as exc:
        raise _http_error(exc)
    if routine is None:
        raise _NOT_FOUND
    return routine
