from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.finance.imports.repository import ImportRepository
from app.features.finance.imports.schemas import ImportRuleCreate
from app.features.finance.installment_plans.repository import InstallmentPlanRepository
from app.features.finance.installment_plans.schemas import InstallmentPlanCreate, InstallmentPlanRead
from app.features.finance.installment_plans.tables import InstallmentPlan
from app.features.finance.transactions.repository import TransactionRepository

logger = logging.getLogger(__name__)


def _to_read(plan: InstallmentPlan, captured: int) -> InstallmentPlanRead:
    return InstallmentPlanRead(
        id=plan.id,
        account_id=plan.account_id,
        description=plan.description,
        total_installments=plan.total_installments,
        captured_installments=captured,
        plan_ref=plan.plan_ref,
        original_amount=plan.original_amount,
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
        self._txn_repo = TransactionRepository(session)

    async def create_plan_with_rule(self, data: InstallmentPlanCreate) -> InstallmentPlanRead:
        plan = await self._repo.create(
            account_id=data.account_id,
            description=data.description,
            total_installments=data.total_installments,
            opened_date=data.opened_date,
            plan_ref=data.plan_ref,
            original_amount=data.original_amount,
        )
        await self._import_repo.create_rule(
            ImportRuleCreate(
                pattern=data.pattern,
                # Imported rows always carry a negative amount for an expense (see
                # _rule_matches, which compares against row.amount directly) -- an
                # installment payment is always an expense, but the form has no sign
                # hint, so a user typing the amount off their statement naturally
                # enters it positive. Normalize here rather than expect them to guess.
                amount=-abs(data.amount) if data.amount is not None else None,
                mode=data.mode,
                installment_plan_id=plan.id,
            )
        )
        logger.info(
            "Installment plan created: id=%d account_id=%d total_installments=%d",
            plan.id, plan.account_id, plan.total_installments,
        )
        return _to_read(plan, captured=0)

    async def ensure_plan_for_ref(
        self,
        account_id: int,
        plan_ref: str,
        description: str,
        total_installments: int,
        original_amount: Decimal,
        opened_date: date,
    ) -> tuple[InstallmentPlanRead, bool]:
        """Get-or-create by plan_ref, called for every distinct plan_ref seen in a PDF
        import (any statement month, not just the plan's opening one -- see
        ParsedInstallmentPlanSignal). Returns (plan, was_created) so the caller can
        decide whether to attempt the one-time "find a match, else create a
        placeholder" step, which only makes sense right when a plan is first seen.
        """
        existing = await self._repo.get_by_account_and_plan_ref(account_id, plan_ref)
        if existing is not None:
            found = await self._repo.get_with_captured_count(existing.id)
            assert found is not None
            return _to_read(*found), False
        created = await self.create_plan_with_rule(
            InstallmentPlanCreate(
                account_id=account_id,
                description=description,
                total_installments=total_installments,
                opened_date=opened_date,
                plan_ref=plan_ref,
                original_amount=original_amount,
                pattern=plan_ref,
                mode="auto",
            )
        )
        return created, True

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
        # A placeholder is meaningless without its plan -- deleting it here avoids
        # leaving a stray €0.00 "Placeholder" transaction behind with no plan to
        # explain it. A real (non-placeholder) linked transaction is left alone,
        # just unlinked (installment_plan_id -> NULL via ondelete=SET NULL).
        await self._txn_repo.delete_placeholder_for_plan(plan_id)
        deleted = await self._repo.delete(plan_id)
        if deleted:
            logger.info("Installment plan deleted: id=%d rules_deleted=%d", plan_id, rules_deleted)
        return deleted
