from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.api.auth import require_auth
from app.dependencies import InstallmentPlanServiceDep
from app.features.finance.installment_plans.schemas import (
    InstallmentPlanCreate,
    InstallmentPlanFilters,
    InstallmentPlanRead,
    InstallmentPlanUpdate,
)

router = APIRouter(
    prefix="/finance/installment-plans", tags=["finance"], dependencies=[Depends(require_auth)]
)


@router.get("", response_model=list[InstallmentPlanRead])
async def list_installment_plans(
    service: InstallmentPlanServiceDep, filters: InstallmentPlanFilters = Depends()
):
    return await service.list(account_id=filters.account_id, status=filters.status)


@router.post("", response_model=InstallmentPlanRead, status_code=status.HTTP_201_CREATED)
async def create_installment_plan(request: InstallmentPlanCreate, service: InstallmentPlanServiceDep):
    return await service.create_plan_with_rule(request)


@router.get("/{plan_id}", response_model=InstallmentPlanRead)
async def get_installment_plan(plan_id: int, service: InstallmentPlanServiceDep):
    plan = await service.get(plan_id)
    if plan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Installment plan not found")
    return plan


@router.patch("/{plan_id}", response_model=InstallmentPlanRead)
async def update_installment_plan(
    plan_id: int, request: InstallmentPlanUpdate, service: InstallmentPlanServiceDep
):
    plan = await service.update(plan_id, request.description, request.total_installments)
    if plan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Installment plan not found")
    return plan


@router.delete("/{plan_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_installment_plan(plan_id: int, service: InstallmentPlanServiceDep):
    deleted = await service.delete(plan_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Installment plan not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{plan_id}/transactions/{transaction_id}/unlink", status_code=status.HTTP_204_NO_CONTENT)
async def unlink_installment_plan_transaction(
    plan_id: int, transaction_id: int, service: InstallmentPlanServiceDep
):
    unlinked = await service.unlink_transaction(plan_id, transaction_id)
    if not unlinked:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found on this plan")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
