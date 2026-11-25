from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.auth import require_auth
from app.dependencies import TravelPlaceServiceDep
from app.features.travel.errors import TravelNotFoundError
from app.features.travel.places.detail import TravelPlaceDetail
from app.features.travel.places.schemas import (
    PlaceLocations,
    TravelPlaceCreate,
    TravelPlaceFilters,
    TravelPlaceRead,
    TravelPlaceUpdate,
)

# Travel's view of places (tags, grade, visits, stays). Deleting a place is DELETE /location/places/{id}.
router = APIRouter(prefix="/travel/places", tags=["travel"], dependencies=[Depends(require_auth)])


@router.get("", response_model=list[TravelPlaceRead])
async def get_places(
    service: TravelPlaceServiceDep, filters: Annotated[TravelPlaceFilters, Depends()]
) -> list[TravelPlaceRead]:
    return await service.get_places(filters)


@router.get("/locations", response_model=PlaceLocations)
async def get_place_locations(service: TravelPlaceServiceDep) -> PlaceLocations:
    """Cities and countries of all places, for the filters' autocomplete."""
    return await service.get_locations()


@router.post("", response_model=TravelPlaceRead, status_code=status.HTTP_201_CREATED)
async def create_place(request: TravelPlaceCreate, service: TravelPlaceServiceDep) -> TravelPlaceRead:
    """Create a place with its travel tags in one call, finding or creating its city by name."""
    try:
        return await service.create_place(request)
    except TravelNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.get("/{place_id}", response_model=TravelPlaceDetail)
async def get_place(place_id: int, service: TravelPlaceServiceDep) -> TravelPlaceDetail:
    place = await service.get_place_detail(place_id)
    if place is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Place not found")
    return place


@router.patch("/{place_id}", response_model=TravelPlaceRead)
async def update_place(place_id: int, request: TravelPlaceUpdate, service: TravelPlaceServiceDep) -> TravelPlaceRead:
    """Change the place and, when given, replace its travel tags."""
    try:
        place = await service.update_place(place_id, request)
    except TravelNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if place is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Place not found")
    return place
