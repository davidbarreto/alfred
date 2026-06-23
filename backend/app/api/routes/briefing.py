from fastapi import APIRouter, Depends

from app.api.auth import require_auth
from app.dependencies import BriefingFormatterServiceDep, BriefingSummaryServiceDep
from app.features.briefing.schemas import FormattedBriefing, MorningBriefing

router = APIRouter(prefix="/briefing", tags=["briefing"], dependencies=[Depends(require_auth)])


@router.get("/morning", response_model=MorningBriefing)
async def get_morning_briefing(service: BriefingSummaryServiceDep) -> MorningBriefing:
    return await service.build()


@router.get("/morning/formatted", response_model=FormattedBriefing)
async def get_morning_briefing_formatted(
    summary_service: BriefingSummaryServiceDep,
    formatter_service: BriefingFormatterServiceDep,
) -> FormattedBriefing:
    briefing = await summary_service.build()
    return await formatter_service.format(briefing)
