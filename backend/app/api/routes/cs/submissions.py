from fastapi import APIRouter, Depends, HTTPException, status

from app.api.auth import require_auth
from app.dependencies import CsSubmissionServiceDep
from app.features.cs.submissions.schemas import SubmissionCreate, SubmissionFilters, SubmissionRead

router = APIRouter(prefix="/cs/submissions", tags=["cs"], dependencies=[Depends(require_auth)])


@router.post("", response_model=SubmissionRead, status_code=status.HTTP_201_CREATED)
async def create_submission(request: SubmissionCreate, service: CsSubmissionServiceDep):
    """Manual import path for platforms with no live sync (HackerRank, UVA, pre-sync LeetCode history)."""
    return await service.create_submission(request)


@router.get("", response_model=list[SubmissionRead])
async def get_submissions(service: CsSubmissionServiceDep, filters: SubmissionFilters = Depends()):
    return await service.get_submissions(filters)


@router.get("/{submission_id}", response_model=SubmissionRead)
async def get_submission(submission_id: int, service: CsSubmissionServiceDep):
    submission = await service.get_submission(submission_id)
    if submission is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Submission not found")
    return submission
