from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.api.auth import require_auth
from app.dependencies import CountryServiceDep
from app.features.location.countries.schemas import CountryRead, CountryUpdate
from app.features.location.errors import LocationConflictError

router = APIRouter(prefix="/location/countries", tags=["location"], dependencies=[Depends(require_auth)])


@router.get("", response_model=list[CountryRead])
async def get_countries(service: CountryServiceDep) -> list[CountryRead]:
    return await service.get_countries()


@router.get("/{country_id}", response_model=CountryRead)
async def get_country(country_id: int, service: CountryServiceDep) -> CountryRead:
    country = await service.get_country(country_id)
    if country is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Country not found")
    return country


@router.patch("/{country_id}", response_model=CountryRead)
async def update_country(country_id: int, request: CountryUpdate, service: CountryServiceDep) -> CountryRead:
    try:
        country = await service.update_country(country_id, request)
    except LocationConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    if country is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Country not found")
    return country


@router.delete("/{country_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_country(country_id: int, service: CountryServiceDep) -> Response:
    try:
        deleted = await service.delete_country(country_id)
    except LocationConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Country not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
