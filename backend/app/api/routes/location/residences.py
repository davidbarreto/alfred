from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.api.auth import require_auth
from app.dependencies import ResidenceServiceDep
from app.features.location.residences.schemas import ResidenceCreate, ResidenceFilters, ResidenceRead, ResidenceUpdate

# Unknown city 404, clashes (a second birth or open row, an overlap) 409 and a bad merged period 422 come from the
# location error handlers in main.py.
router = APIRouter(prefix="/location/residences", tags=["location"], dependencies=[Depends(require_auth)])


@router.get("", response_model=list[ResidenceRead])
async def get_residences(service: ResidenceServiceDep, filters: Annotated[ResidenceFilters, Depends()]) -> list[ResidenceRead]:
    """Places lived, newest first (the birth row, with no start, last)."""
    return await service.list_residences(filters)


@router.post("", response_model=ResidenceRead, status_code=status.HTTP_201_CREATED)
async def create_residence(request: ResidenceCreate, service: ResidenceServiceDep) -> ResidenceRead:
    return await service.create_residence(request)


@router.post("/follow-home", response_model=ResidenceRead)
async def follow_home(service: ResidenceServiceDep) -> ResidenceRead:
    """Close the open row today and open one in the Home place's city."""
    return await service.follow_home()


@router.get("/{residence_id}", response_model=ResidenceRead)
async def get_residence(residence_id: int, service: ResidenceServiceDep) -> ResidenceRead:
    found = await service.get_residence(residence_id)
    if found is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Residence not found")
    return found


@router.patch("/{residence_id}", response_model=ResidenceRead)
async def update_residence(residence_id: int, request: ResidenceUpdate, service: ResidenceServiceDep) -> ResidenceRead:
    found = await service.update_residence(residence_id, request)
    if found is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Residence not found")
    return found


@router.delete("/{residence_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_residence(residence_id: int, service: ResidenceServiceDep) -> Response:
    if not await service.delete_residence(residence_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Residence not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
