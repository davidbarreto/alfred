from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.api.auth import require_auth
from app.dependencies import PlaceServiceDep
from app.features.travel.places.schemas import PlaceCreate, PlaceFilters, PlaceRead, PlaceUpdate
from app.features.travel.places.service import PlaceInUseError

router = APIRouter(prefix="/travel/places", tags=["travel"], dependencies=[Depends(require_auth)])


@router.get("", response_model=list[PlaceRead])
async def get_places(service: PlaceServiceDep, filters: Annotated[PlaceFilters, Depends()]) -> list[PlaceRead]:
    return await service.get_places(filters)


@router.post("", response_model=PlaceRead, status_code=status.HTTP_201_CREATED)
async def create_place(request: PlaceCreate, service: PlaceServiceDep) -> PlaceRead:
    return await service.create_place(request)


@router.get("/{place_id}", response_model=PlaceRead)
async def get_place(place_id: int, service: PlaceServiceDep) -> PlaceRead:
    place = await service.get_place(place_id)
    if place is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Place not found")
    return place


@router.patch("/{place_id}", response_model=PlaceRead)
async def update_place(place_id: int, request: PlaceUpdate, service: PlaceServiceDep) -> PlaceRead:
    try:
        place = await service.update_place(place_id, request)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    if place is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Place not found")
    return place


@router.delete("/{place_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_place(place_id: int, service: PlaceServiceDep) -> Response:
    try:
        deleted = await service.delete_place(place_id)
    except PlaceInUseError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Place has visits or stays and can't be deleted"
        )
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Place not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
