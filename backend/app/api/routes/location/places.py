from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.api.auth import require_auth
from app.dependencies import PlaceServiceDep
from app.features.location.places.schemas import PlaceCreate, PlaceFilters, PlaceRead, PlaceUpdate

# Conflicts (409), validation (422) and unknown cities (404) are mapped by main.py's location error handlers.
router = APIRouter(prefix="/location/places", tags=["location"], dependencies=[Depends(require_auth)])

_NOT_FOUND = "Place not found"


@router.get("", response_model=list[PlaceRead])
async def list_places(service: PlaceServiceDep, filters: Annotated[PlaceFilters, Depends()]) -> list[PlaceRead]:
    return await service.list(filters)


@router.post("", response_model=PlaceRead, status_code=status.HTTP_201_CREATED)
async def create_place(request: PlaceCreate, service: PlaceServiceDep) -> PlaceRead:
    return await service.create(request)


@router.get("/{place_id}", response_model=PlaceRead)
async def get_place(place_id: int, service: PlaceServiceDep) -> PlaceRead:
    place = await service.get(place_id)
    if place is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND)
    return place


@router.patch("/{place_id}", response_model=PlaceRead)
async def update_place(place_id: int, request: PlaceUpdate, service: PlaceServiceDep) -> PlaceRead:
    place = await service.update(place_id, request)
    if place is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND)
    return place


@router.delete("/{place_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_place(place_id: int, service: PlaceServiceDep) -> Response:
    if not await service.delete(place_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
