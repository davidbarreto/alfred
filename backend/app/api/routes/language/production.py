from fastapi import APIRouter, Depends, HTTPException, status

from app.api.auth import require_auth
from app.dependencies import ProductionServiceDep
from app.features.language.production.schemas import (
    NextTaskFilters,
    ProductionAttemptCreate,
    ProductionAttemptRead,
    ProductionMasteryRead,
    ProductionTaskRead,
)

router = APIRouter(prefix="/language/production", tags=["language"], dependencies=[Depends(require_auth)])


@router.get("/next-task", response_model=ProductionTaskRead)
async def get_next_task(service: ProductionServiceDep, filters: NextTaskFilters = Depends()):
    task = await service.get_next_task(filters.track_id, filters.task_type)
    if task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No chunks due for production practice",
        )
    return task


@router.get("/mastery", response_model=list[ProductionMasteryRead])
async def get_mastery(service: ProductionServiceDep, track_id: int | None = None):
    return await service.get_mastery(track_id)


@router.post("/attempts", response_model=ProductionAttemptRead, status_code=status.HTTP_201_CREATED)
async def grade_attempt(request: ProductionAttemptCreate, service: ProductionServiceDep):
    return await service.grade_attempt(request)
