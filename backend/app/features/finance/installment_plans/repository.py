from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.finance.installment_plans.tables import InstallmentPlan
from app.features.finance.transactions.tables import Transaction


def _captured_count_subquery():
    """Live count of transactions linked to a plan that actually represent a
    captured installment -- excludes a superseded lump-sum original, which is
    zeroed out (amount == 0) but still linked via installment_plan_id so it
    shows up alongside the real installments on the plan's transaction list.
    """
    return (
        select(func.count(Transaction.id))
        .where(
            Transaction.installment_plan_id == InstallmentPlan.id,
            Transaction.amount != 0,
        )
        .correlate(InstallmentPlan)
        .scalar_subquery()
    )


class InstallmentPlanRepository:

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, plan_id: int) -> InstallmentPlan | None:
        result = await self._session.execute(
            select(InstallmentPlan).where(InstallmentPlan.id == plan_id)
        )
        return result.scalars().first()

    async def get_with_captured_count(self, plan_id: int) -> tuple[InstallmentPlan, int] | None:
        result = await self._session.execute(
            select(InstallmentPlan, _captured_count_subquery()).where(InstallmentPlan.id == plan_id)
        )
        row = result.first()
        return None if row is None else (row[0], row[1])

    async def get_open_by_account_and_description(
        self, account_id: int, description: str
    ) -> InstallmentPlan | None:
        result = await self._session.execute(
            select(InstallmentPlan).where(
                and_(
                    InstallmentPlan.account_id == account_id,
                    InstallmentPlan.description == description,
                    InstallmentPlan.status == "open",
                )
            )
        )
        return result.scalars().first()

    async def list(
        self, account_id: int | None = None, status: str | None = None
    ) -> list[tuple[InstallmentPlan, int]]:
        query = select(InstallmentPlan, _captured_count_subquery()).order_by(
            InstallmentPlan.opened_date.desc()
        )
        if account_id is not None:
            query = query.where(InstallmentPlan.account_id == account_id)
        if status is not None:
            query = query.where(InstallmentPlan.status == status)
        result = await self._session.execute(query)
        return [(row[0], row[1]) for row in result.all()]

    async def list_open_by_account(self, account_id: int) -> list[tuple[InstallmentPlan, int]]:
        return await self.list(account_id=account_id, status="open")

    async def create(
        self,
        account_id: int,
        description: str,
        total_installments: int,
        opened_date: date,
        plan_ref: str | None = None,
    ) -> InstallmentPlan:
        plan = InstallmentPlan(
            account_id=account_id,
            description=description,
            total_installments=total_installments,
            opened_date=opened_date,
            plan_ref=plan_ref,
            status="open",
        )
        self._session.add(plan)
        await self._session.commit()
        await self._session.refresh(plan)
        return plan

    async def update(
        self, plan_id: int, description: str | None, total_installments: int | None
    ) -> InstallmentPlan | None:
        plan = await self.get(plan_id)
        if plan is None:
            return None
        if description is not None:
            plan.description = description
        if total_installments is not None:
            plan.total_installments = total_installments
        await self._session.commit()
        await self._session.refresh(plan)
        return plan

    async def delete(self, plan_id: int) -> bool:
        plan = await self.get(plan_id)
        if plan is None:
            return False
        await self._session.delete(plan)
        await self._session.commit()
        return True

    async def record_capture(
        self,
        plan_id: int,
        plan_ref: str | None,
        juros: Decimal | None,
        imposto_selo: Decimal | None,
    ) -> InstallmentPlan | None:
        """Called once per newly-inserted transaction linked to a plan. juros/
        imposto_selo are only ever set for ActivoBank-PDF-sourced Capital rows
        (None for a manually-matched Cetelem/Nubank transaction), so the
        interest/duty accumulation and plan_ref backfill are no-ops there --
        everything else (live recount, closing) applies uniformly.
        """
        plan = await self.get(plan_id)
        if plan is None:
            return None
        if plan_ref and not plan.plan_ref:
            plan.plan_ref = plan_ref
        if juros is not None:
            plan.total_interest_paid += juros
        if imposto_selo is not None:
            plan.total_duty_paid += imposto_selo
        await self._session.commit()
        await self._session.refresh(plan)

        result = await self._session.execute(
            select(func.count(Transaction.id)).where(
                Transaction.installment_plan_id == plan_id, Transaction.amount != 0
            )
        )
        captured = result.scalar() or 0
        if captured >= plan.total_installments and plan.status != "closed":
            plan.status = "closed"
            await self._session.commit()
            await self._session.refresh(plan)
        return plan
