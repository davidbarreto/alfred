from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.api.auth import require_auth
from app.dependencies import LegServiceDep
from app.features.travel.errors import TravelNotFoundError
from app.features.travel.legs.schemas import LegCreate, LegRead, LegUpdate

router = APIRouter(prefix="/travel/legs", tags=["travel"], dependencies=[Depends(require_auth)])


@router.post("", response_model=LegRead, status_code=status.HTTP_201_CREATED)
async def create_leg(request: LegCreate, service: LegServiceDep) -> LegRead:
    try:
        return await service.create_leg(request)
    except TravelNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.get("/{leg_id}", response_model=LegRead)
async def get_leg(leg_id: int, service: LegServiceDep) -> LegRead:
    leg = await service.get_leg(leg_id)
    if leg is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Leg not found")
    return leg


@router.patch("/{leg_id}", response_model=LegRead)
async def update_leg(leg_id: int, request: LegUpdate, service: LegServiceDep) -> LegRead:
    try:
        leg = await service.update_leg(leg_id, request)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    if leg is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Leg not found")
    return leg


@router.delete("/{leg_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_leg(leg_id: int, service: LegServiceDep) -> Response:
    if not await service.delete_leg(leg_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Leg not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
