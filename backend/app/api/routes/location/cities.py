from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.api.auth import require_auth
from app.dependencies import CityServiceDep
from app.features.location.cities.schemas import CityCreate, CityFilters, CityRead, CityUpdate
from app.features.location.errors import LocationConflictError, LocationNotFoundError

router = APIRouter(prefix="/location/cities", tags=["location"], dependencies=[Depends(require_auth)])


@router.get("", response_model=list[CityRead])
async def get_cities(service: CityServiceDep, filters: Annotated[CityFilters, Depends()]) -> list[CityRead]:
    return await service.get_cities(filters)


@router.post("", response_model=CityRead, status_code=status.HTTP_201_CREATED)
async def create_city(request: CityCreate, service: CityServiceDep) -> CityRead:
    try:
        return await service.create_city(request)
    except LocationNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except LocationConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))


@router.get("/{city_id}", response_model=CityRead)
async def get_city(city_id: int, service: CityServiceDep) -> CityRead:
    city = await service.get_city(city_id)
    if city is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="City not found")
    return city


@router.patch("/{city_id}", response_model=CityRead)
async def update_city(city_id: int, request: CityUpdate, service: CityServiceDep) -> CityRead:
    try:
        city = await service.update_city(city_id, request)
    except LocationNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except LocationConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    if city is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="City not found")
    return city


@router.delete("/{city_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_city(city_id: int, service: CityServiceDep) -> Response:
    try:
        deleted = await service.delete_city(city_id)
    except LocationConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="City not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
