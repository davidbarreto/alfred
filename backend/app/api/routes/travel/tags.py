from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.api.auth import require_auth
from app.dependencies import TravelTagServiceDep
from app.features.travel.tags.schemas import TravelTagRead, TravelTagUpdate, TravelTagUsage
from app.features.travel.tags.service import TravelTagNameTakenError

router = APIRouter(prefix="/travel/tags", tags=["travel"], dependencies=[Depends(require_auth)])


@router.get("", response_model=list[TravelTagUsage])
async def get_tags(service: TravelTagServiceDep) -> list[TravelTagUsage]:
    return await service.get_tags()


@router.patch("/{tag_id}", response_model=TravelTagRead)
async def rename_tag(tag_id: int, request: TravelTagUpdate, service: TravelTagServiceDep) -> TravelTagRead:
    try:
        tag = await service.rename_tag(tag_id, request)
    except TravelTagNameTakenError:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A tag with that name already exists")
    if tag is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tag not found")
    return tag


@router.delete("/{tag_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tag(tag_id: int, service: TravelTagServiceDep) -> Response:
    if not await service.delete_tag(tag_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tag not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
