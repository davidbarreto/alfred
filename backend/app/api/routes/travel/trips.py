from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from app.api.auth import require_auth
from app.dependencies import TripRecapServiceDep, TripServiceDep
from app.features.travel.recap.schemas import TripRecap
from app.features.travel.trips.map_points import MapScope, TripMap
from app.features.travel.trips.today import TripToday
from app.features.travel.trips.schemas import TripCreate, TripDetail, TripFilters, TripRead, TripUpdate

router = APIRouter(prefix="/travel/trips", tags=["travel"], dependencies=[Depends(require_auth)])


@router.get("", response_model=list[TripRead])
async def get_trips(service: TripServiceDep, filters: Annotated[TripFilters, Depends()]) -> list[TripRead]:
    return await service.get_trips(filters)


@router.post("", response_model=TripRead, status_code=status.HTTP_201_CREATED)
async def create_trip(request: TripCreate, service: TripServiceDep) -> TripRead:
    return await service.create_trip(request)


@router.get("/{trip_id}/recap", response_model=TripRecap)
async def get_trip_recap(trip_id: int, service: TripRecapServiceDep) -> TripRecap:
    """What a finished trip came to: spend, places visited, and what is still to grade or write down."""
    recap = await service.get_recap(trip_id)
    if recap is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trip not found")
    return recap


@router.get("/{trip_id}/today", response_model=TripToday)
async def get_trip_today(trip_id: int, service: TripServiceDep) -> TripToday:
    """The next step with a countdown and today's visits, for use on the trip itself."""
    result = await service.get_today(trip_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trip not found")
    return result


@router.get("/{trip_id}/map", response_model=TripMap)
async def get_trip_map(
    trip_id: int,
    service: TripServiceDep,
    scope: Annotated[MapScope, Query(description="all: planned and visited; visited: only what already happened")] = "all",
) -> TripMap:
    """The trip's pins (stays, planned and visited places, airports) to import into a map such as Google My Maps."""
    result = await service.get_trip_map(trip_id, scope)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trip not found")
    return result


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
