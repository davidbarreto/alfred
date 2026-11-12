from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from app.api.auth import require_auth
from app.dependencies import VisitServiceDep
from app.features.travel.errors import TravelConflictError, TravelNotFoundError
from app.features.travel.visits.schemas import VisitCreate, VisitFilters, VisitRead, VisitUpdate

router = APIRouter(prefix="/travel/visits", tags=["travel"], dependencies=[Depends(require_auth)])


@router.get("", response_model=list[VisitRead])
async def get_visits(service: VisitServiceDep, filters: Annotated[VisitFilters, Depends()]) -> list[VisitRead]:
    return await service.get_visits(filters)


@router.post("", response_model=VisitRead, status_code=status.HTTP_201_CREATED)
async def create_visit(request: VisitCreate, service: VisitServiceDep) -> VisitRead:
    try:
        return await service.create_visit(request)
    except TravelNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except TravelConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))


@router.get("/{visit_id}", response_model=VisitRead)
async def get_visit(visit_id: int, service: VisitServiceDep) -> VisitRead:
    visit = await service.get_visit(visit_id)
    if visit is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Visit not found")
    return visit


@router.patch("/{visit_id}", response_model=VisitRead)
async def update_visit(visit_id: int, request: VisitUpdate, service: VisitServiceDep) -> VisitRead:
    try:
        visit = await service.update_visit(visit_id, request)
    except TravelNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except TravelConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    if visit is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Visit not found")
    return visit


@router.delete("/{visit_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_visit(
    visit_id: int, service: VisitServiceDep,
    delete_event: Annotated[bool, Query(description="Also delete the linked calendar event")] = False,
) -> Response:
    if not await service.delete_visit(visit_id, delete_event):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Visit not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
