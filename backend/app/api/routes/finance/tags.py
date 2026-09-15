from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.api.auth import require_auth
from app.dependencies import TagServiceDep
from app.features.finance.tags.schemas import TagCreate, TagRead, TagUpdate

router = APIRouter(prefix="/finance/tags", tags=["finance"], dependencies=[Depends(require_auth)])


@router.post("", response_model=TagRead, status_code=status.HTTP_201_CREATED)
async def create_tag(request: TagCreate, service: TagServiceDep):
    return await service.create(request)


@router.get("", response_model=list[TagRead])
async def list_tags(service: TagServiceDep):
    return await service.list()


@router.get("/{tag_id}", response_model=TagRead)
async def get_tag(tag_id: int, service: TagServiceDep):
    tag = await service.get(tag_id)
    if tag is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tag not found")
    return tag


@router.patch("/{tag_id}", response_model=TagRead)
async def update_tag(tag_id: int, request: TagUpdate, service: TagServiceDep):
    tag = await service.update(tag_id, request)
    if tag is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tag not found")
    return tag


@router.delete("/{tag_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tag(tag_id: int, service: TagServiceDep):
    deleted = await service.delete(tag_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tag not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
