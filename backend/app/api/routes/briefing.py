from fastapi import APIRouter, Depends

from app.api.auth import require_auth
from app.dependencies import (
    EveningDigestFormatterServiceDep,
    EveningDigestSummaryServiceDep,
    MorningBriefingFormatterServiceDep,
    MorningBriefingSummaryServiceDep,
)
from app.features.briefing.schemas import EveningDigest, FormattedBriefing, MorningBriefing

router = APIRouter(prefix="/briefing", tags=["briefing"], dependencies=[Depends(require_auth)])


@router.get("/morning", response_model=MorningBriefing)
async def get_morning_briefing(service: MorningBriefingSummaryServiceDep) -> MorningBriefing:
    return await service.build()


@router.get("/morning/formatted", response_model=FormattedBriefing)
async def get_morning_briefing_formatted(
    summary_service: MorningBriefingSummaryServiceDep,
    formatter_service: MorningBriefingFormatterServiceDep,
    force: bool = False,
) -> FormattedBriefing:
    if not force:
        saved = await formatter_service.get_saved()
        if saved is not None:
            return saved
    briefing = await summary_service.build()
    return await formatter_service.format(briefing)


@router.get("/evening", response_model=EveningDigest)
async def get_evening_digest(service: EveningDigestSummaryServiceDep) -> EveningDigest:
    return await service.build()


@router.get("/evening/formatted", response_model=FormattedBriefing)
async def get_evening_digest_formatted(
    summary_service: EveningDigestSummaryServiceDep,
    formatter_service: EveningDigestFormatterServiceDep,
    force: bool = False,
) -> FormattedBriefing:
    if not force:
        saved = await formatter_service.get_saved()
        if saved is not None:
            return saved
    digest = await summary_service.build()
    return await formatter_service.format(digest)
