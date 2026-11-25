from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.api.auth import require_auth
from app.dependencies import EverydayPlaceServiceDep, TravelTimeServiceDep
from app.features.organizer.everyday_places.schemas import (
    EverydayPlaceCreate,
    EverydayPlaceFilters,
    EverydayPlaceRead,
    PlaceCategoriesUpdate,
    PlaceCategory,
)
from app.features.organizer.travel_times.schemas import TravelTimeRead, TravelTimeSet

# The everyday role of places. What a place is (name, hours, delete) is under /location/places.
# Conflicts (409) and validation (422) are mapped by main.py's location error handlers.
router = APIRouter(prefix="/organizer", tags=["organizer"], dependencies=[Depends(require_auth)])

_NOT_FOUND = "Place not found"


@router.get("/places", response_model=list[EverydayPlaceRead])
async def list_everyday_places(
    service: EverydayPlaceServiceDep, filters: Annotated[EverydayPlaceFilters, Depends()]
) -> list[EverydayPlaceRead]:
    """The everyday places: the members plus the Home place."""
    return await service.list(filters)


@router.post("/places", response_model=EverydayPlaceRead, status_code=status.HTTP_201_CREATED)
async def create_everyday_place(request: EverydayPlaceCreate, service: EverydayPlaceServiceDep) -> EverydayPlaceRead:
    """Create a place that is one of the everyday places from the start."""
    return await service.create(request)


@router.get("/places/{place_id}", response_model=EverydayPlaceRead)
async def get_everyday_place(place_id: int, service: EverydayPlaceServiceDep) -> EverydayPlaceRead:
    """Any place as the everyday role sees it (`everyday` is false when it is not one)."""
    place = await service.get(place_id)
    if place is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND)
    return place


@router.put("/places/{place_id}", response_model=EverydayPlaceRead)
async def add_everyday_place(place_id: int, service: EverydayPlaceServiceDep) -> EverydayPlaceRead:
    """Make an existing place one of the everyday places."""
    place = await service.add(place_id)
    if place is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND)
    return place


@router.delete("/places/{place_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_everyday_place(place_id: int, service: EverydayPlaceServiceDep) -> Response:
    """Take the place off the everyday list; the place itself stays."""
    if not await service.remove(place_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/places/{place_id}/categories", response_model=list[PlaceCategory])
async def get_place_categories(place_id: int, service: EverydayPlaceServiceDep) -> list[PlaceCategory]:
    categories = await service.get_categories(place_id)
    if categories is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND)
    return categories


@router.put("/places/{place_id}/categories", response_model=list[PlaceCategory])
async def set_place_categories(
    place_id: int, request: PlaceCategoriesUpdate, service: EverydayPlaceServiceDep
) -> list[PlaceCategory]:
    categories = await service.set_categories(place_id, request.category_ids)
    if categories is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND)
    return categories


@router.get("/places/{place_id}/travel-times", response_model=list[TravelTimeRead])
async def list_place_travel_times(place_id: int, service: TravelTimeServiceDep) -> list[TravelTimeRead]:
    travel_times = await service.list_for(place_id)
    if travel_times is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND)
    return travel_times


@router.put("/places/{place_id}/travel-times", response_model=TravelTimeRead)
async def set_place_travel_time(place_id: int, request: TravelTimeSet, service: TravelTimeServiceDep) -> TravelTimeRead:
    travel_time = await service.set(place_id, request)
    if travel_time is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND)
    return travel_time


@router.delete("/travel-times/{travel_time_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_travel_time(travel_time_id: int, service: TravelTimeServiceDep) -> Response:
    if not await service.delete(travel_time_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Travel time not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
