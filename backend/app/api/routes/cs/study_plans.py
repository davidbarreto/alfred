from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.api.auth import require_auth
from app.dependencies import CsStudyPlanServiceDep
from app.features.cs.study_plans.schemas import StudyPlanRead

router = APIRouter(prefix="/cs/study-plans", tags=["cs"], dependencies=[Depends(require_auth)])


@router.get("/active/{cadence}", response_model=StudyPlanRead)
async def get_active_plan(cadence: Literal["weekly", "monthly"], service: CsStudyPlanServiceDep):
    plan = await service.get_active_plan(cadence)
    if plan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No active plan for this cadence")
    return plan


@router.get("/{plan_id}", response_model=StudyPlanRead)
async def get_plan(plan_id: int, service: CsStudyPlanServiceDep):
    plan = await service.get_plan(plan_id)
    if plan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan not found")
    return plan


@router.post("/items/{item_id}/complete", status_code=status.HTTP_204_NO_CONTENT)
async def complete_item(item_id: int, service: CsStudyPlanServiceDep):
    marked = await service.mark_item_done(item_id)
    if not marked:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Study plan item not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
