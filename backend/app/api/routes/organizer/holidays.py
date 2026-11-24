from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.auth import require_auth
from app.dependencies import HolidayServiceDep
from app.features.organizer.holidays.errors import HolidayRangeError
from app.features.organizer.holidays.schemas import HolidayRead

router = APIRouter(prefix="/organizer/holidays", tags=["organizer"], dependencies=[Depends(require_auth)])


@router.get("", response_model=list[HolidayRead])
async def list_holidays(
    service: HolidayServiceDep,
    from_date: Annotated[date, Query(alias="from", description="First local date (inclusive)")],
    to_date: Annotated[date, Query(alias="to", description="Last local date (inclusive)")],
):
    """Public holidays of the primary holiday calendar (the first HOLIDAY_CALENDARS entry) in the range."""
    try:
        return await service.list(from_date, to_date)
    except HolidayRangeError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
