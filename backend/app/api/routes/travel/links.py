from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.api.auth import require_auth
from app.dependencies import WebLinkServiceDep
from app.features.travel.errors import TravelConflictError, TravelNotFoundError
from app.features.travel.links.schemas import WebLinkCreate, WebLinkRead, WebLinkUpdate

router = APIRouter(prefix="/travel", tags=["travel"], dependencies=[Depends(require_auth)])


@router.get("/trips/{trip_id}/links", response_model=list[WebLinkRead])
async def get_trip_links(trip_id: int, service: WebLinkServiceDep) -> list[WebLinkRead]:
    try:
        return await service.get_trip_links(trip_id)
    except TravelNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.post("/trips/{trip_id}/links", response_model=WebLinkRead, status_code=status.HTTP_201_CREATED)
async def create_trip_link(trip_id: int, request: WebLinkCreate, service: WebLinkServiceDep) -> WebLinkRead:
    try:
        return await service.create_trip_link(trip_id, request)
    except TravelNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except TravelConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))


@router.get("/places/{place_id}/links", response_model=list[WebLinkRead])
async def get_place_links(place_id: int, service: WebLinkServiceDep) -> list[WebLinkRead]:
    try:
        return await service.get_place_links(place_id)
    except TravelNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.post("/places/{place_id}/links", response_model=WebLinkRead, status_code=status.HTTP_201_CREATED)
async def create_place_link(place_id: int, request: WebLinkCreate, service: WebLinkServiceDep) -> WebLinkRead:
    try:
        return await service.create_place_link(place_id, request)
    except TravelNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except TravelConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))


@router.get("/links/{link_id}", response_model=WebLinkRead)
async def get_link(link_id: int, service: WebLinkServiceDep) -> WebLinkRead:
    link = await service.get_link(link_id)
    if link is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Link not found")
    return link


@router.patch("/links/{link_id}", response_model=WebLinkRead)
async def update_link(link_id: int, request: WebLinkUpdate, service: WebLinkServiceDep) -> WebLinkRead:
    try:
        link = await service.update_link(link_id, request)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    except TravelConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    if link is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Link not found")
    return link


@router.delete("/links/{link_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_link(link_id: int, service: WebLinkServiceDep) -> Response:
    if not await service.delete_link(link_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Link not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
