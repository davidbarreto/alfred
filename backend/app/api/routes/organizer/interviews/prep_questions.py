from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from app.api.auth import require_auth
from app.dependencies import InterviewPrepQuestionServiceDep
from app.features.organizer.interviews.prep_questions.schemas import (
    InterviewPrepQuestionCreate,
    InterviewPrepQuestionRead,
    InterviewPrepQuestionUpdate,
    InterviewPrepQuestionWithStories,
    StoryLinkCreate,
    StoryLinkRead,
)

router = APIRouter(
    prefix="/organizer/interview-prep-questions",
    tags=["organizer"],
    dependencies=[Depends(require_auth)],
)


@router.get("", response_model=list[InterviewPrepQuestionRead])
async def get_questions(
    service: InterviewPrepQuestionServiceDep,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[InterviewPrepQuestionRead]:
    return await service.get_questions(limit=limit, offset=offset)


@router.get("/{question_id}", response_model=InterviewPrepQuestionWithStories)
async def get_question(question_id: int, service: InterviewPrepQuestionServiceDep) -> InterviewPrepQuestionWithStories:
    question = await service.get_question_with_stories(question_id)
    if question is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Question not found")
    return question


@router.post("", response_model=InterviewPrepQuestionRead, status_code=status.HTTP_201_CREATED)
async def create_question(
    request: InterviewPrepQuestionCreate, service: InterviewPrepQuestionServiceDep
) -> InterviewPrepQuestionRead:
    return await service.create_question(request)


@router.patch("/{question_id}", response_model=InterviewPrepQuestionRead)
async def update_question(
    question_id: int, request: InterviewPrepQuestionUpdate, service: InterviewPrepQuestionServiceDep
) -> InterviewPrepQuestionRead:
    question = await service.update_question(question_id, request)
    if question is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Question not found")
    return question


@router.delete("/{question_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_question(question_id: int, service: InterviewPrepQuestionServiceDep) -> Response:
    if not await service.delete_question(question_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Question not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("/{question_id}/stories/{story_id}", response_model=StoryLinkRead)
async def link_story(
    question_id: int, story_id: int, request: StoryLinkCreate, service: InterviewPrepQuestionServiceDep
) -> StoryLinkRead:
    link = await service.link_story(question_id, story_id, request.fit_score)
    if link is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Question or story not found")
    return link


@router.delete("/{question_id}/stories/{story_id}", status_code=status.HTTP_204_NO_CONTENT)
async def unlink_story(question_id: int, story_id: int, service: InterviewPrepQuestionServiceDep) -> Response:
    if not await service.unlink_story(question_id, story_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Link not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
