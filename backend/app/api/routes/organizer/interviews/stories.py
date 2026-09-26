from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.api.auth import require_auth
from app.dependencies import InterviewStoryServiceDep
from app.features.organizer.interviews.stories.schemas import InterviewStoryCreate, InterviewStoryRead, InterviewStoryUpdate

router = APIRouter(
    prefix="/organizer/interview-stories",
    tags=["organizer"],
    dependencies=[Depends(require_auth)],
)


@router.get("", response_model=list[InterviewStoryRead])
async def get_stories(
    service: InterviewStoryServiceDep,
    tag: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[InterviewStoryRead]:
    if tag:
        return await service.get_stories_by_tag(tag, limit=limit, offset=offset)
    return await service.get_stories(limit=limit, offset=offset)


@router.get("/tags", response_model=list[str])
async def get_all_tags(service: InterviewStoryServiceDep) -> list[str]:
    return await service.get_all_tags()


@router.get("/{story_id}", response_model=InterviewStoryRead)
async def get_story(story_id: int, service: InterviewStoryServiceDep) -> InterviewStoryRead:
    story = await service.get_story(story_id)
    if story is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Story not found")
    return story


@router.post("", response_model=InterviewStoryRead, status_code=status.HTTP_201_CREATED)
async def create_story(request: InterviewStoryCreate, service: InterviewStoryServiceDep) -> InterviewStoryRead:
    return await service.create_story(request)


@router.patch("/{story_id}", response_model=InterviewStoryRead)
async def update_story(
    story_id: int, request: InterviewStoryUpdate, service: InterviewStoryServiceDep
) -> InterviewStoryRead:
    story = await service.update_story(story_id, request)
    if story is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Story not found")
    return story


@router.delete("/{story_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_story(story_id: int, service: InterviewStoryServiceDep) -> Response:
    success = await service.delete_story(story_id)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Story not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{story_id}/tags/{tag}", status_code=status.HTTP_201_CREATED)
async def add_tag(story_id: int, tag: str, service: InterviewStoryServiceDep) -> Response:
    success = await service.add_tag(story_id, tag)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Story not found")
    return Response(status_code=status.HTTP_201_CREATED)


@router.delete("/{story_id}/tags/{tag}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_tag(story_id: int, tag: str, service: InterviewStoryServiceDep) -> Response:
    success = await service.remove_tag(story_id, tag)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Story or tag not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


class AssessmentResponse:
    suggested_strength: int


@router.post("/{story_id}/assess-strength")
async def assess_strength(story_id: int, service: InterviewStoryServiceDep) -> dict[str, int | None]:
    score = await service.assess_strength(story_id)
    if score is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to assess story strength")
    return {"suggested_strength": score}
