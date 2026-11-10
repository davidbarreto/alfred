from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from app.api.auth import require_auth
from app.dependencies import TripServiceDep
from app.features.travel.trips.schemas import TripCreate, TripDetail, TripFilters, TripRead, TripUpdate

router = APIRouter(prefix="/travel/trips", tags=["travel"], dependencies=[Depends(require_auth)])


@router.get("", response_model=list[TripRead])
async def get_trips(service: TripServiceDep, filters: Annotated[TripFilters, Depends()]) -> list[TripRead]:
    return await service.get_trips(filters)


@router.post("", response_model=TripRead, status_code=status.HTTP_201_CREATED)
async def create_trip(request: TripCreate, service: TripServiceDep) -> TripRead:
    return await service.create_trip(request)


@router.get("/{trip_id}", response_model=TripDetail)
async def get_trip(
    trip_id: int,
    service: TripServiceDep,
    all_visits: Annotated[bool, Query(description="Include planned and missed visits of an ended trip")] = False,
) -> TripDetail:
    trip = await service.get_trip_detail(trip_id, include_all_visits=all_visits)
    if trip is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trip not found")
    return trip


@router.patch("/{trip_id}", response_model=TripRead)
async def update_trip(trip_id: int, request: TripUpdate, service: TripServiceDep) -> TripRead:
    try:
        trip = await service.update_trip(trip_id, request)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    if trip is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trip not found")
    return trip


@router.delete("/{trip_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_trip(trip_id: int, service: TripServiceDep) -> Response:
    if not await service.delete_trip(trip_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trip not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
