from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from app.api.auth import require_auth
from app.dependencies import TripForecastServiceDep, VisitServiceDep, TripRecapServiceDep, TripServiceDep, TripSnoozeServiceDep, WhileAwayServiceDep
from app.features.travel.other_events import OtherEvent
from app.features.travel.errors import TravelNotFoundError
from app.features.travel.visits.schemas import VisitMove, VisitMoveResult
from app.features.travel.trips.forecast import TripForecast
from app.features.travel.trips.while_away import WhileAway
from app.features.travel.recap.schemas import TripRecap
from app.features.travel.trips.map_points import MapScope, TripMap
from app.features.travel.trips.today import TripToday
from app.features.travel.trips.schemas import (
    TripCreate, TripDetail, TripFilters, TripListItem, TripLocations, TripRead, TripUpdate,
)

router = APIRouter(prefix="/travel/trips", tags=["travel"], dependencies=[Depends(require_auth)])


@router.get("", response_model=list[TripListItem])
async def get_trips(service: TripServiceDep, filters: Annotated[TripFilters, Depends()]) -> list[TripListItem]:
    return await service.get_trips(filters)


@router.get("/locations", response_model=TripLocations)
async def get_trip_locations(service: TripServiceDep) -> TripLocations:
    """Cities and countries of the places trips stay at or visit, for the filters' autocomplete."""
    return await service.get_locations()


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


@router.post("/{trip_id}/visits/move", response_model=VisitMoveResult)
async def move_visits(trip_id: int, request: VisitMove, service: VisitServiceDep) -> VisitMoveResult:
    """Move the planned visits of one day to another (optionally only those at places with a tag such as Outdoor)."""
    try:
        return await service.move_visits(trip_id, request)
    except TravelNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.get("/{trip_id}/while-away", response_model=WhileAway)
async def get_while_away(trip_id: int, service: WhileAwayServiceDep) -> WhileAway:
    """Contact birthdays, task due dates and recurring expenses that fall inside the trip's dates."""
    result = await service.get_while_away(trip_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trip not found")
    return result


@router.get("/{trip_id}/forecast", response_model=TripForecast)
async def get_trip_forecast(trip_id: int, service: TripForecastServiceDep) -> TripForecast:
    """Daily weather per stay city: the forecast within 14 days of the start, else last year's same dates."""
    result = await service.get_forecast(trip_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trip not found")
    return result


@router.get("/{trip_id}/other-events", response_model=list[OtherEvent])
async def get_other_events(trip_id: int, service: TripSnoozeServiceDep) -> list[OtherEvent]:
    """Calendar events inside the trip's dates that are not part of it, and whether their reminders are snoozed."""
    result = await service.get_other_events(trip_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trip not found")
    return result


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
