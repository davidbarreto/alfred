from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from app.api.auth import require_auth
from app.dependencies import InterviewCandidateQuestionServiceDep
from app.features.organizer.interviews.candidate_questions.schemas import (
    InterviewCandidateQuestionCreate,
    InterviewCandidateQuestionRead,
    InterviewCandidateQuestionUpdate,
)

router = APIRouter(
    prefix="/organizer/candidate-questions",
    tags=["organizer"],
    dependencies=[Depends(require_auth)],
)


@router.get("", response_model=list[InterviewCandidateQuestionRead])
async def get_questions(
    service: InterviewCandidateQuestionServiceDep,
    category: str | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[InterviewCandidateQuestionRead]:
    return await service.get_questions(category=category, limit=limit, offset=offset)


@router.get("/categories", response_model=list[str])
async def get_all_categories(service: InterviewCandidateQuestionServiceDep) -> list[str]:
    return await service.get_all_categories()


@router.get("/{question_id}", response_model=InterviewCandidateQuestionRead)
async def get_question(question_id: int, service: InterviewCandidateQuestionServiceDep) -> InterviewCandidateQuestionRead:
    question = await service.get_question(question_id)
    if question is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Question not found")
    return question


@router.post("", response_model=InterviewCandidateQuestionRead, status_code=status.HTTP_201_CREATED)
async def create_question(
    request: InterviewCandidateQuestionCreate, service: InterviewCandidateQuestionServiceDep
) -> InterviewCandidateQuestionRead:
    return await service.create_question(request)


@router.patch("/{question_id}", response_model=InterviewCandidateQuestionRead)
async def update_question(
    question_id: int, request: InterviewCandidateQuestionUpdate, service: InterviewCandidateQuestionServiceDep
) -> InterviewCandidateQuestionRead:
    question = await service.update_question(question_id, request)
    if question is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Question not found")
    return question


@router.delete("/{question_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_question(question_id: int, service: InterviewCandidateQuestionServiceDep) -> Response:
    if not await service.delete_question(question_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Question not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
