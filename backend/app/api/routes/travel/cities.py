from fastapi import APIRouter, Depends, HTTPException, status

from app.api.auth import require_auth
from app.dependencies import TravelCityServiceDep
from app.features.travel.cities.schemas import CityDetail, CountryDetail
from app.features.travel.transaction_links.schemas import ChargePart, LinkedTransactions

# Travel's read-only view of a city or country; they are created, edited and deleted under /location.
router = APIRouter(prefix="/travel", tags=["travel"], dependencies=[Depends(require_auth)])


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
