from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.auth import require_auth
from app.dependencies import TravelCityServiceDep
from app.features.travel.cities.schemas import (
    CityDetail,
    CountryDetail,
    LocationLeg,
    LocationPage,
    LocationStay,
    TravelCityRow,
    TravelCountryRow,
    TravelLocationFilters,
)
from app.features.travel.transaction_links.schemas import ChargePart, LinkedTransactions

# Travel's read-only view of a city or country; they are created, edited and deleted under /location.
router = APIRouter(prefix="/travel", tags=["travel"], dependencies=[Depends(require_auth)])


@router.get("/cities", response_model=list[TravelCityRow])
async def list_cities(service: TravelCityServiceDep, filters: Annotated[TravelLocationFilters, Depends()]) -> list[TravelCityRow]:
    """Cities with travel data (a stay, a visit, a leg end or a link): trips, nights so far, spend, last visit."""
    return await service.list_cities(filters)


@router.get("/countries", response_model=list[TravelCountryRow])
async def list_countries(service: TravelCityServiceDep, filters: Annotated[TravelLocationFilters, Depends()]) -> list[TravelCountryRow]:
    return await service.list_countries(filters)


@router.get("/cities/{city_id}", response_model=CityDetail)
async def get_city(city_id: int, service: TravelCityServiceDep) -> CityDetail:
    city = await service.get_city_detail(city_id)
    if city is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="City not found")
    return city


@router.get("/cities/{city_id}/charges", response_model=LinkedTransactions)
async def get_city_charges(city_id: int, service: TravelCityServiceDep, part: ChargePart = "overall") -> LinkedTransactions:
    """The transactions behind the city's spend figures."""
    found = await service.get_city_charges(city_id, part)
    if found is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="City not found")
    return found


@router.get("/countries/{country_id}", response_model=CountryDetail)
async def get_country(country_id: int, service: TravelCityServiceDep) -> CountryDetail:
    country = await service.get_country_detail(country_id)
    if country is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Country not found")
    return country


@router.get("/countries/{country_id}/charges", response_model=LinkedTransactions)
async def get_country_charges(country_id: int, service: TravelCityServiceDep, part: ChargePart = "overall") -> LinkedTransactions:
    found = await service.get_country_charges(country_id, part)
    if found is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Country not found")
    return found


@router.get("/cities/{city_id}/stays", response_model=list[LocationStay])
async def list_city_stays(city_id: int, service: TravelCityServiceDep, page: Annotated[LocationPage, Depends()]) -> list[LocationStay]:
    """Stays at the city's places, newest first: the rows behind its nights."""
    found = await service.list_city_stays(city_id, page)
    if found is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="City not found")
    return found


@router.get("/cities/{city_id}/legs", response_model=list[LocationLeg])
async def list_city_legs(city_id: int, service: TravelCityServiceDep, page: Annotated[LocationPage, Depends()]) -> list[LocationLeg]:
    """Legs that start or end in the city, newest first."""
    found = await service.list_city_legs(city_id, page)
    if found is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="City not found")
    return found


@router.get("/countries/{country_id}/stays", response_model=list[LocationStay])
async def list_country_stays(
    country_id: int, service: TravelCityServiceDep, page: Annotated[LocationPage, Depends()],
) -> list[LocationStay]:
    """Stays at places in the country's cities, newest first."""
    found = await service.list_country_stays(country_id, page)
    if found is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Country not found")
    return found
