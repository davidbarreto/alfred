from __future__ import annotations

from fastapi import APIRouter, Depends, status

from app.api.auth import require_auth
from app.dependencies import InterviewInsightServiceDep
from app.features.organizer.interviews.insights.schemas import InterviewInsightFilters, InterviewInsightRead

router = APIRouter(
    prefix="/organizer/interview-insights",
    tags=["organizer"],
    dependencies=[Depends(require_auth)],
)


@router.post("", response_model=InterviewInsightRead, status_code=status.HTTP_201_CREATED)
async def generate_insights(service: InterviewInsightServiceDep) -> InterviewInsightRead:
    return await service.generate_insights()


@router.get("", response_model=list[InterviewInsightRead])
async def get_insights_history(
    service: InterviewInsightServiceDep,
    filters: InterviewInsightFilters = Depends(),
) -> list[InterviewInsightRead]:
    return await service.get_insights_history(filters)
