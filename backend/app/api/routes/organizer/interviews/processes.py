from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel

from app.api.auth import require_auth
from app.dependencies import InterviewProcessServiceDep, JdExtractionServiceDep
from app.features.organizer.interviews.processes.jd_extraction_service import JobPostingExtraction
from app.features.organizer.interviews.processes.schemas import (
    InterviewProcessCreate,
    InterviewProcessCreateWithFirstStage,
    InterviewProcessFilters,
    InterviewProcessRead,
    InterviewProcessUpdate,
)

router = APIRouter(
    prefix="/organizer/interview-processes",
    tags=["organizer"],
    dependencies=[Depends(require_auth)],
)


class ExtractFromUrlRequest(BaseModel):
    url: str


@router.get("", response_model=list[InterviewProcessRead])
async def get_processes(
    service: InterviewProcessServiceDep,
    filters: InterviewProcessFilters = Depends(),
) -> list[InterviewProcessRead]:
    return await service.get_processes(filters)


@router.get("/{process_id}", response_model=InterviewProcessRead)
async def get_process(process_id: int, service: InterviewProcessServiceDep) -> InterviewProcessRead:
    process = await service.get_process(process_id)
    if process is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Interview process not found")
    return process


@router.post("", response_model=InterviewProcessRead, status_code=status.HTTP_201_CREATED)
async def create_process(
    request: InterviewProcessCreateWithFirstStage, service: InterviewProcessServiceDep
) -> InterviewProcessRead:
    return await service.create_process_with_optional_first_stage(request.process, request.first_stage)


@router.post("/extract-from-url", response_model=JobPostingExtraction)
async def extract_from_url(
    request: ExtractFromUrlRequest, service: JdExtractionServiceDep
) -> JobPostingExtraction:
    return await service.extract_from_url(request.url)


@router.patch("/{process_id}", response_model=InterviewProcessRead)
async def update_process(
    process_id: int, request: InterviewProcessUpdate, service: InterviewProcessServiceDep
) -> InterviewProcessRead:
    process = await service.update_process(process_id, request)
    if process is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Interview process not found")
    return process


@router.delete("/{process_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_process(process_id: int, service: InterviewProcessServiceDep) -> Response:
    await service.delete_process(process_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
