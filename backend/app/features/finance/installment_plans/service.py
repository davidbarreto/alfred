from __future__ import annotations

import logging
from collections import defaultdict
from datetime import date
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.finance.imports.repository import ImportRepository
from app.features.finance.imports.schemas import ImportRuleCreate
from app.features.finance.installment_plans.repository import InstallmentPlanRepository
from app.features.finance.installment_plans.gaps import CapturedInstallment, build_slots, parse_plan_ref, parse_position
from app.features.finance.installment_plans.schemas import (
    InstallmentPlanCreate,
    InstallmentPlanRead,
    InstallmentSlot,
    MissingInstallment,
    MissingInstallmentsMonth,
)
from app.features.finance.installment_plans.tables import InstallmentPlan
from app.features.finance.transactions.repository import TransactionRepository
from app.features.finance.transactions.tables import Transaction
from app.shared.timezone import local_today

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


def _slots_for_plan(plan: InstallmentPlan, transactions: list[Transaction], today: date) -> list[InstallmentSlot]:
    captured = [
        CapturedInstallment(position, txn.id, txn.date.date(), txn.amount)
        for txn in transactions
        if (position := parse_position(txn.bank_description)) is not None
    ]
    return build_slots(plan.total_installments, captured, today)


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
        original_amount: Decimal | None,
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

    async def get_slots(self, plan_id: int) -> list[InstallmentSlot] | None:
        plan = await self._repo.get(plan_id)
        if plan is None:
            return None
        slots = _slots_for_plan(plan, await self._repo.list_captured_transactions([plan_id]), local_today())
        logger.debug("Installment slots: plan_id=%d slots=%d", plan_id, len(slots))
        return slots

    async def get_missing(self, account_id: int | None = None) -> list[MissingInstallmentsMonth]:
        """Missing/overdue installments of open plans, grouped by the statement month to import."""
        plans = [plan for plan, _ in await self._repo.list(account_id=account_id, status="open")]
        transactions = await self._repo.list_captured_transactions([plan.id for plan in plans])
        by_plan: dict[int, list[Transaction]] = defaultdict(list)
        for txn in transactions:
            by_plan[txn.installment_plan_id].append(txn)

        today = local_today()
        by_month: dict[str, list[MissingInstallment]] = defaultdict(list)
        for plan in plans:
            for slot in _slots_for_plan(plan, by_plan[plan.id], today):
                if slot.status in ("missing", "overdue"):
                    by_month[slot.expected_month].append(
                        MissingInstallment(
                            plan_id=plan.id,
                            description=plan.description,
                            plan_ref=plan.plan_ref,
                            position=slot.position,
                            total_installments=plan.total_installments,
                            status=slot.status,
                        )
                    )
        logger.debug("Missing installments: months=%d", len(by_month))
        return [MissingInstallmentsMonth(month=month, items=by_month[month]) for month in sorted(by_month)]

    async def relink_orphans(self) -> int:
        """Link already-imported installment transactions that never joined their plan.

        Before the rule-ordering fix, a generic rule listed ahead of a plan's own rule
        hid the plan link, and a re-import skips those rows as duplicates. Matches by
        account + plan_ref in the description. Interest/duty totals are not recomputed
        (the per-row figures only exist in the original statement).
        """
        plans = {(plan.account_id, plan.plan_ref): plan for plan, _ in await self._repo.list() if plan.plan_ref}
        to_link: dict[int, list[int]] = defaultdict(list)
        for txn in await self._repo.list_unlinked_installment_transactions():
            plan = plans.get((txn.account_id, parse_plan_ref(txn.bank_description)))
            if plan is not None:
                to_link[plan.id].append(txn.id)
        for plan_id, transaction_ids in to_link.items():
            await self._repo.link_transactions(plan_id, transaction_ids)
            await self._repo.recompute_status(plan_id)
        linked = sum(len(ids) for ids in to_link.values())
        logger.info("Installment orphans relinked: transactions=%d plans=%d", linked, len(to_link))
        return linked

    async def update(
        self, plan_id: int, description: str | None, total_installments: int | None
    ) -> InstallmentPlanRead | None:
        plan = await self._repo.update(plan_id, description, total_installments)
        if plan is None:
            return None
        logger.info("Installment plan updated: id=%d", plan_id)
        found = await self._repo.get_with_captured_count(plan_id)
        return None if found is None else _to_read(*found)

    async def unlink_transaction(self, plan_id: int, transaction_id: int) -> bool:
        txn = await self._txn_repo.get(transaction_id)
        if txn is None or txn.installment_plan_id != plan_id:
            return False
        await self._txn_repo.unlink_installment_plan(transaction_id)
        await self._repo.recompute_status(plan_id)
        logger.info(
            "Transaction unlinked from installment plan: transaction_id=%d plan_id=%d",
            transaction_id, plan_id,
        )
        return True

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
