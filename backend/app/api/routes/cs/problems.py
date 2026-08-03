from fastapi import APIRouter, Depends, HTTPException, status

from app.api.auth import require_auth
from app.dependencies import CsProblemServiceDep
from app.features.cs.problems.schemas import (
    AttemptedProblemFilters,
    AttemptedProblemRead,
    ProblemCreate,
    ProblemFilters,
    ProblemRead,
)

router = APIRouter(prefix="/cs/problems", tags=["cs"], dependencies=[Depends(require_auth)])


@router.post("", response_model=ProblemRead, status_code=status.HTTP_201_CREATED)
async def upsert_problem(request: ProblemCreate, service: CsProblemServiceDep):
    """Manual import path — creates or updates a problem by (platform_id, external_id)."""
    return await service.upsert_problem(request)


@router.get("", response_model=list[ProblemRead])
async def get_problems(service: CsProblemServiceDep, filters: ProblemFilters = Depends()):
    return await service.get_problems(filters)


@router.get("/attempted", response_model=list[AttemptedProblemRead])
async def get_attempted_problems(service: CsProblemServiceDep, filters: AttemptedProblemFilters = Depends()):
    return await service.get_attempted_problems(filters)


@router.get("/{problem_id}", response_model=ProblemRead)
async def get_problem(problem_id: int, service: CsProblemServiceDep):
    problem = await service.get_problem(problem_id)
    if problem is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Problem not found")
    return problem
