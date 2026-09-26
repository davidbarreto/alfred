from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from app.api.auth import require_auth
from app.dependencies import InterviewStoryServiceDep
from app.features.organizer.interviews.stories.schemas import (
    InterviewStoryCreate,
    InterviewStoryRead,
    InterviewStoryUpdate,
    StoryStrengthAssessment,
)
from app.features.organizer.interviews.stories.service import StoryAssessmentError

router = APIRouter(
    prefix="/organizer/interview-stories",
    tags=["organizer"],
    dependencies=[Depends(require_auth)],
)


@router.get("", response_model=list[InterviewStoryRead])
async def get_stories(
    service: InterviewStoryServiceDep,
    tag: str | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[InterviewStoryRead]:
    return await service.get_stories(tag=tag, limit=limit, offset=offset)


@router.get("/tags", response_model=list[str])
async def get_all_tags(service: InterviewStoryServiceDep) -> list[str]:
    return await service.get_all_tags()


@router.get("/search", response_model=list[InterviewStoryRead])
async def search_stories(
    service: InterviewStoryServiceDep,
    q: Annotated[str, Query(min_length=1)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[InterviewStoryRead]:
    return await service.search_stories(q, limit=limit)


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
    if not await service.delete_story(story_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Story not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{story_id}/tags/{tag}", response_model=InterviewStoryRead)
async def add_tag(story_id: int, tag: str, service: InterviewStoryServiceDep) -> InterviewStoryRead:
    if not tag.strip() or len(tag.strip()) > 100:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Tag must be 1-100 characters")
    story = await service.add_tag(story_id, tag)
    if story is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Story not found")
    return story


@router.delete("/{story_id}/tags/{tag}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_tag(story_id: int, tag: str, service: InterviewStoryServiceDep) -> Response:
    if not await service.remove_tag(story_id, tag):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Story or tag not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{story_id}/assess-strength", response_model=StoryStrengthAssessment)
async def assess_strength(story_id: int, service: InterviewStoryServiceDep) -> StoryStrengthAssessment:
    try:
        assessment = await service.assess_strength(story_id)
    except StoryAssessmentError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))
    if assessment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Story not found")
    return assessment
