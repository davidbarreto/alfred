from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.api.auth import require_auth
from app.dependencies import StudyPlanGeneratorServiceDep, StudyPlanServiceDep
from app.features.study.generator.service import PlanGenerationError, StudyTrackNotFoundError
from app.features.study.plans.schemas import StudyPlanFilters, StudyPlanRead, StudyPlansOverview
from app.features.study.plans.service import ActivePlanCapReachedError, InvalidPlanTransitionError

router = APIRouter(prefix="/study/plans", tags=["study"], dependencies=[Depends(require_auth)])


def _transition_conflict(exc: InvalidPlanTransitionError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=f"Cannot {exc.action} this plan: it is {exc.status}",
    )


def _not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Study plan not found")


@router.get("", response_model=list[StudyPlanRead])
async def list_plans(service: StudyPlanServiceDep, filters: StudyPlanFilters = Depends()):
    return await service.get_plans(filters)


@router.get("/overview", response_model=StudyPlansOverview)
async def get_overview(service: StudyPlanServiceDep):
    return await service.get_overview()


@router.post("/generate", response_model=StudyPlanRead, status_code=status.HTTP_201_CREATED)
async def generate_plan(service: StudyPlanGeneratorServiceDep):
    try:
        return await service.generate_from_cs_stats()
    except StudyTrackNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Study track not found") from exc
    except PlanGenerationError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


@router.post("/items/{item_id}/complete", status_code=status.HTTP_204_NO_CONTENT)
async def complete_item(item_id: int, service: StudyPlanServiceDep):
    marked = await service.mark_item_done(item_id)
    if not marked:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Study plan item not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{plan_id}", response_model=StudyPlanRead)
async def get_plan(plan_id: int, service: StudyPlanServiceDep):
    plan = await service.get_plan(plan_id)
    if plan is None:
        raise _not_found()
    return plan


@router.post("/{plan_id}/activate", response_model=StudyPlanRead)
async def activate_plan(plan_id: int, service: StudyPlanServiceDep):
    try:
        plan = await service.activate_plan(plan_id)
    except InvalidPlanTransitionError as exc:
        raise _transition_conflict(exc) from exc
    except ActivePlanCapReachedError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"You already have {exc.max_active_plans} active plan(s). Finish or abandon one first.",
        ) from exc
    if plan is None:
        raise _not_found()
    return plan


@router.post("/{plan_id}/complete", response_model=StudyPlanRead)
async def complete_plan(plan_id: int, service: StudyPlanServiceDep):
    try:
        plan = await service.complete_plan(plan_id)
    except InvalidPlanTransitionError as exc:
        raise _transition_conflict(exc) from exc
    if plan is None:
        raise _not_found()
    return plan


@router.post("/{plan_id}/abandon", response_model=StudyPlanRead)
async def abandon_plan(plan_id: int, service: StudyPlanServiceDep):
    try:
        plan = await service.abandon_plan(plan_id)
    except InvalidPlanTransitionError as exc:
        raise _transition_conflict(exc) from exc
    if plan is None:
        raise _not_found()
    return plan


@router.delete("/{plan_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_plan(plan_id: int, service: StudyPlanServiceDep):
    deleted = await service.delete_plan(plan_id)
    if not deleted:
        raise _not_found()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
