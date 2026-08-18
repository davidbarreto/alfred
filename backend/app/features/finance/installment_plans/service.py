from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.finance.imports.repository import ImportRepository
from app.features.finance.imports.schemas import ImportRuleCreate
from app.features.finance.installment_plans.repository import InstallmentPlanRepository
from app.features.finance.installment_plans.schemas import InstallmentPlanCreate, InstallmentPlanRead
from app.features.finance.installment_plans.tables import InstallmentPlan

logger = logging.getLogger(__name__)


def _to_read(plan: InstallmentPlan, captured: int) -> InstallmentPlanRead:
    return InstallmentPlanRead(
        id=plan.id,
        account_id=plan.account_id,
        description=plan.description,
        total_installments=plan.total_installments,
        captured_installments=captured,
        plan_ref=plan.plan_ref,
        opened_date=plan.opened_date,
        status=plan.status,
        total_interest_paid=plan.total_interest_paid,
        total_duty_paid=plan.total_duty_paid,
        created_at=plan.created_at,
    )


class InstallmentPlanService:
    """Orchestrates InstallmentPlanRepository and ImportRepository: a plan is always
    created together with the ImportRule that tags future matching transactions with
    its id, so there's exactly one mechanism for how a transaction ever gets linked
    to a plan (whether the plan was opened manually or auto-detected from an
    ActivoBank PDF)."""

    def __init__(self, session: AsyncSession) -> None:
        self._repo = InstallmentPlanRepository(session)
        self._import_repo = ImportRepository(session)

    async def create_plan_with_rule(self, data: InstallmentPlanCreate) -> InstallmentPlanRead:
        plan = await self._repo.create(
            account_id=data.account_id,
            description=data.description,
            total_installments=data.total_installments,
            opened_date=data.opened_date,
            plan_ref=data.plan_ref,
        )
        await self._import_repo.create_rule(
            ImportRuleCreate(
                pattern=data.pattern,
                amount=data.amount,
                mode=data.mode,
                installment_plan_id=plan.id,
            )
        )
        logger.info(
            "Installment plan created: id=%d account_id=%d total_installments=%d",
            plan.id, plan.account_id, plan.total_installments,
        )
        return _to_read(plan, captured=0)

    async def get(self, plan_id: int) -> InstallmentPlanRead | None:
        found = await self._repo.get_with_captured_count(plan_id)
        if found is None:
            return None
        plan, captured = found
        return _to_read(plan, captured)

    async def list(
        self, account_id: int | None = None, status: str | None = None
    ) -> list[InstallmentPlanRead]:
        return [_to_read(plan, captured) for plan, captured in await self._repo.list(account_id, status)]

    async def update(
        self, plan_id: int, description: str | None, total_installments: int | None
    ) -> InstallmentPlanRead | None:
        plan = await self._repo.update(plan_id, description, total_installments)
        if plan is None:
            return None
        logger.info("Installment plan updated: id=%d", plan_id)
        found = await self._repo.get_with_captured_count(plan_id)
        return None if found is None else _to_read(*found)

    async def delete(self, plan_id: int) -> bool:
        rules_deleted = await self._import_repo.delete_rules_by_installment_plan(plan_id)
        deleted = await self._repo.delete(plan_id)
        if deleted:
            logger.info("Installment plan deleted: id=%d rules_deleted=%d", plan_id, rules_deleted)
        return deleted
