from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.api.auth import require_auth
from app.dependencies import ChecklistServiceDep
from app.features.travel.checklist.schemas import ChecklistGenerated, ChecklistItemRead, ChecklistItemWrite
from app.features.travel.errors import TravelConflictError, TravelNotFoundError

router = APIRouter(prefix="/travel", tags=["travel"], dependencies=[Depends(require_auth)])


@router.get("/checklist-template", response_model=list[ChecklistItemRead])
async def get_checklist_template(service: ChecklistServiceDep) -> list[ChecklistItemRead]:
    """The pre-trip checklist template (defaults are written the first time it is read)."""
    return await service.get_template()


@router.put("/checklist-template/{anchor}/{name}", response_model=ChecklistItemRead)
async def put_checklist_item(anchor: str, name: str, request: ChecklistItemWrite, service: ChecklistServiceDep) -> ChecklistItemRead:
    """Create or update an item: `anchor` is start or end, `offset_days` is signed (negative = before)."""
    try:
        return await service.put_item(anchor, name, request.offset_days)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    except TravelConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))


@router.delete("/checklist-template/{anchor}/{name}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_checklist_item(anchor: str, name: str, service: ChecklistServiceDep) -> Response:
    try:
        deleted = await service.delete_item(anchor, name)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Checklist item not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/trips/{trip_id}/checklist", response_model=ChecklistGenerated)
async def generate_trip_checklist(trip_id: int, service: ChecklistServiceDep) -> ChecklistGenerated:
    """Create one task per template item, due at its offset from the trip; items that already have a task are skipped."""
    try:
        return await service.generate(trip_id)
    except TravelNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
