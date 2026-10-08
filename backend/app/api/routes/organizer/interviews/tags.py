from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.api.auth import require_auth
from app.dependencies import InterviewTagServiceDep
from app.features.organizer.interviews.tags.schemas import InterviewTagRead, InterviewTagUpdate, InterviewTagUsage
from app.features.organizer.interviews.tags.service import InterviewTagNameTakenError

router = APIRouter(
    prefix="/organizer/interview-tags",
    tags=["organizer"],
    dependencies=[Depends(require_auth)],
)


@router.get("", response_model=list[InterviewTagUsage])
async def get_tags(service: InterviewTagServiceDep) -> list[InterviewTagUsage]:
    return await service.get_tags()


@router.patch("/{tag_id}", response_model=InterviewTagRead)
async def rename_tag(tag_id: int, request: InterviewTagUpdate, service: InterviewTagServiceDep) -> InterviewTagRead:
    try:
        tag = await service.rename_tag(tag_id, request)
    except InterviewTagNameTakenError:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A tag with that name already exists")
    if tag is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tag not found")
    return tag


@router.delete("/{tag_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tag(tag_id: int, service: InterviewTagServiceDep) -> Response:
    if not await service.delete_tag(tag_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tag not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
