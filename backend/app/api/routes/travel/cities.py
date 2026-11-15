from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.api.auth import require_auth
from app.dependencies import CityServiceDep
from app.features.travel.cities.schemas import (
    CityCreate, CityDetail, CityFilters, CityRead, CityUpdate, CountryDetail, CountryRef, CountryUpdate,
)
from app.features.travel.errors import TravelConflictError, TravelNotFoundError

router = APIRouter(prefix="/travel", tags=["travel"], dependencies=[Depends(require_auth)])


@router.get("/countries", response_model=list[CountryRef])
async def get_countries(service: CityServiceDep) -> list[CountryRef]:
    return await service.get_countries()


@router.get("/cities", response_model=list[CityRead])
async def get_cities(service: CityServiceDep, filters: Annotated[CityFilters, Depends()]) -> list[CityRead]:
    return await service.get_cities(filters)


@router.post("/cities", response_model=CityRead, status_code=status.HTTP_201_CREATED)
async def create_city(request: CityCreate, service: CityServiceDep) -> CityRead:
    try:
        return await service.create_city(request)
    except TravelNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except TravelConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))


@router.get("/cities/{city_id}", response_model=CityDetail)
async def get_city(city_id: int, service: CityServiceDep) -> CityDetail:
    city = await service.get_city_detail(city_id)
    if city is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="City not found")
    return city


@router.patch("/cities/{city_id}", response_model=CityRead)
async def update_city(city_id: int, request: CityUpdate, service: CityServiceDep) -> CityRead:
    try:
        city = await service.update_city(city_id, request)
    except TravelNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except TravelConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    if city is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="City not found")
    return city


@router.delete("/cities/{city_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_city(city_id: int, service: CityServiceDep) -> Response:
    try:
        deleted = await service.delete_city(city_id)
    except TravelConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="City not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/countries/{country_id}", response_model=CountryDetail)
async def get_country(country_id: int, service: CityServiceDep) -> CountryDetail:
    country = await service.get_country_detail(country_id)
    if country is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Country not found")
    return country


@router.patch("/countries/{country_id}", response_model=CountryRef)
async def update_country(country_id: int, request: CountryUpdate, service: CityServiceDep) -> CountryRef:
    try:
        country = await service.update_country(country_id, request)
    except TravelConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    if country is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Country not found")
    return country


@router.delete("/countries/{country_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_country(country_id: int, service: CityServiceDep) -> Response:
    try:
        deleted = await service.delete_country(country_id)
    except TravelConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Country not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
