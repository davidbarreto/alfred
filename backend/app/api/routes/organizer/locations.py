from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.api.auth import require_auth
from app.dependencies import LocationServiceDep, LocationTravelTimeServiceDep
from app.features.organizer.locations.schemas import (
    LocationCategoriesUpdate,
    LocationCategory,
    LocationCreate,
    LocationFilters,
    LocationRead,
    LocationTravelTimeRead,
    LocationTravelTimeSet,
    LocationUpdate,
)

router = APIRouter(prefix="/organizer/locations", tags=["organizer"], dependencies=[Depends(require_auth)])

_NOT_FOUND = "Location not found"


@router.get("", response_model=list[LocationRead])
async def list_locations(service: LocationServiceDep, filters: LocationFilters = Depends()):
    return await service.list(filters)


@router.delete("/travel-times/{travel_time_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_location_travel_time(travel_time_id: int, service: LocationTravelTimeServiceDep):
    if not await service.delete(travel_time_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Travel time not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("", response_model=LocationRead, status_code=status.HTTP_201_CREATED)
async def create_location(request: LocationCreate, service: LocationServiceDep):
    return await service.create(request)


@router.get("/{location_id}", response_model=LocationRead)
async def get_location(location_id: int, service: LocationServiceDep):
    location = await service.get(location_id)
    if location is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND)
    return location


@router.patch("/{location_id}", response_model=LocationRead)
async def update_location(location_id: int, request: LocationUpdate, service: LocationServiceDep):
    location = await service.update(location_id, request)
    if location is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND)
    return location


@router.delete("/{location_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_location(location_id: int, service: LocationServiceDep):
    if not await service.delete(location_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{location_id}/categories", response_model=list[LocationCategory])
async def get_location_categories(location_id: int, service: LocationServiceDep):
    categories = await service.get_categories(location_id)
    if categories is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND)
    return categories


@router.put("/{location_id}/categories", response_model=list[LocationCategory])
async def set_location_categories(location_id: int, request: LocationCategoriesUpdate, service: LocationServiceDep):
    categories = await service.set_categories(location_id, request.category_ids)
    if categories is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND)
    return categories


@router.get("/{location_id}/travel-times", response_model=list[LocationTravelTimeRead])
async def list_location_travel_times(location_id: int, service: LocationTravelTimeServiceDep):
    travel_times = await service.list_for(location_id)
    if travel_times is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND)
    return travel_times


@router.put("/{location_id}/travel-times", response_model=LocationTravelTimeRead)
async def set_location_travel_time(
    location_id: int, request: LocationTravelTimeSet, service: LocationTravelTimeServiceDep
):
    travel_time = await service.set(location_id, request)
    if travel_time is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND)
    return travel_time
