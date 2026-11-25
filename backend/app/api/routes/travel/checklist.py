from fastapi import APIRouter, Depends, HTTPException, status

from app.api.auth import require_auth
from app.dependencies import ChecklistServiceDep
from app.features.travel.checklist.schemas import ChecklistGenerated, ChecklistTemplateRead, ChecklistTemplateUpdate
from app.features.travel.errors import TravelNotFoundError

router = APIRouter(prefix="/travel", tags=["travel"], dependencies=[Depends(require_auth)])


@router.get("/checklist-template", response_model=ChecklistTemplateRead)
async def get_checklist_template(service: ChecklistServiceDep) -> ChecklistTemplateRead:
    """The pre-trip checklist template (defaults are written the first time it is read)."""
    return await service.get_template()


@router.put("/checklist-template", response_model=ChecklistTemplateRead)
async def put_checklist_template(request: ChecklistTemplateUpdate, service: ChecklistServiceDep) -> ChecklistTemplateRead:
    """Replace the whole template: `anchor` is start or end, `offset_days` is signed (negative = before); items left
    out are deleted and names are unique across both anchors."""
    return await service.replace_template(request.items)


@router.post("/trips/{trip_id}/checklist", response_model=ChecklistGenerated)
async def generate_trip_checklist(trip_id: int, service: ChecklistServiceDep) -> ChecklistGenerated:
    """Create one task per template item, due at its offset from the trip; items that already have a task are skipped."""
    try:
        return await service.generate(trip_id)
    except TravelNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
