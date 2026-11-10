from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.api.auth import require_auth
from app.dependencies import StayServiceDep
from app.features.travel.errors import TravelConflictError, TravelNotFoundError
from app.features.travel.stays.schemas import StayCreate, StayRead, StayUpdate

router = APIRouter(prefix="/travel/stays", tags=["travel"], dependencies=[Depends(require_auth)])


@router.post("", response_model=StayRead, status_code=status.HTTP_201_CREATED)
async def create_stay(request: StayCreate, service: StayServiceDep) -> StayRead:
    try:
        return await service.create_stay(request)
    except TravelNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except TravelConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))


@router.get("/{stay_id}", response_model=StayRead)
async def get_stay(stay_id: int, service: StayServiceDep) -> StayRead:
    stay = await service.get_stay(stay_id)
    if stay is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Stay not found")
    return stay


@router.patch("/{stay_id}", response_model=StayRead)
async def update_stay(stay_id: int, request: StayUpdate, service: StayServiceDep) -> StayRead:
    try:
        stay = await service.update_stay(stay_id, request)
    except TravelNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    if stay is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Stay not found")
    return stay


@router.delete("/{stay_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_stay(stay_id: int, service: StayServiceDep) -> Response:
    if not await service.delete_stay(stay_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Stay not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
