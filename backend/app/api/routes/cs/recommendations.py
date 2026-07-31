from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.auth import require_auth
from app.dependencies import CsRecommendationServiceDep
from app.features.cs.recommendations.schemas import LiveRecommendation
from app.features.cs.study_plans.schemas import StudyPlanRead

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
async def generate_plan(cadence: Literal["weekly", "monthly"], service: CsRecommendationServiceDep):
    return await service.generate_plan(cadence)
