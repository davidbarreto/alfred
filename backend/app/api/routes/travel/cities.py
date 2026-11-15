from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.auth import require_auth
from app.dependencies import CityServiceDep
from app.features.travel.cities.schemas import CityCreate, CityFilters, CityRead, CountryRef
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
