from fastapi import APIRouter, Depends, HTTPException, status

from app.api.auth import require_auth
from app.dependencies import CalendarImportServiceDep
from app.features.travel.calendar_import.schemas import CalendarCandidate

router = APIRouter(prefix="/travel/trips", tags=["travel"], dependencies=[Depends(require_auth)])


@router.get("/{trip_id}/calendar-events", response_model=list[CalendarCandidate])
async def get_calendar_candidates(trip_id: int, service: CalendarImportServiceDep) -> list[CalendarCandidate]:
    """Events already in Alfred's local calendar copy within the trip's dates (no Google call)."""
    candidates = await service.get_candidates(trip_id)
    if candidates is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trip not found")
    return candidates
