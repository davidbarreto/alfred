from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.auth import require_auth
from app.dependencies import CsRecommendationServiceDep
from app.features.cs.recommendations.schemas import LiveRecommendation
from app.features.cs.study_plans.schemas import StudyPlanRead
from app.features.cs.study_plans.service import ActivePlanIncompleteError

router = APIRouter(prefix="/cs/recommendations", tags=["cs"], dependencies=[Depends(require_auth)])


@router.get("/live", response_model=LiveRecommendation)
async def get_live_recommendation(service: CsRecommendationServiceDep):
    recommendation = await service.get_live_recommendation()
    if recommendation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Not enough submission history yet to compute a recommendation",
        )
    return recommendation


@router.post("/plans/{cadence}", response_model=StudyPlanRead, status_code=status.HTTP_201_CREATED)
async def generate_plan(
    cadence: Literal["weekly", "monthly"], service: CsRecommendationServiceDep, force: bool = False
):
    try:
        return await service.generate_plan(cadence, force=force)
    except ActivePlanIncompleteError as exc:
        incomplete = sum(1 for item in exc.plan.items if not item.is_done)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": (
                    f"The current plan still has {incomplete} unfinished item(s). "
                    "Generate a new one anyway?"
                ),
                "plan_id": exc.plan.id,
                "incomplete_count": incomplete,
            },
        ) from exc
