from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.auth import require_auth
from app.dependencies import MapServiceDep
from app.features.location.map.schemas import MapFilters, PlacesMap

# An unknown country or city (404) is mapped by main.py's location error handlers.
router = APIRouter(prefix="/location/map", tags=["location"], dependencies=[Depends(require_auth)])


@router.get("", response_model=PlacesMap)
async def get_map(service: MapServiceDep, filters: Annotated[MapFilters, Depends()]) -> PlacesMap:
    """Countries (with their ISO code and city count), cities and active places with coordinates; no pagination."""
    return await service.get_map(filters)
