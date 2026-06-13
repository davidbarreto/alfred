from fastapi import APIRouter, Depends, HTTPException, Response, status
from app.features.organizer.calendar_events.schemas import EventRead, EventCreate, EventUpdate, EventFilters
from app.api.auth import require_auth
from app.dependencies import CalendarEventServiceDep

router = APIRouter(prefix="/organizer/calendar-events", tags=["organizer"], dependencies=[Depends(require_auth)])


@router.post("/", response_model=EventRead, status_code=status.HTTP_201_CREATED)
async def add_event(request: EventCreate, service: CalendarEventServiceDep):
    return await service.create_event(request)


@router.get("/", response_model=list[EventRead])
async def get_events(service: CalendarEventServiceDep, filters: EventFilters = Depends()):
    return await service.get_events(filters)


@router.get("/{event_id}", response_model=EventRead)
async def get_event(event_id: int, service: CalendarEventServiceDep):
    event_read = await service.get_event(event_id)
    if event_read is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
    return event_read


@router.patch("/{event_id}", response_model=EventRead)
async def update_event(event_id: int, request: EventUpdate, service: CalendarEventServiceDep):
    event_read = await service.update_event(event_id, request)
    if event_read is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
    return event_read


@router.delete("/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_event(event_id: int, service: CalendarEventServiceDep):
    await service.delete_event(event_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
