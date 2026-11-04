from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.finance import cycle
from app.features.finance.budgets.repository import BudgetTargetRepository
from app.features.finance.budgets.schemas import (
    BudgetTargetBulkSetItem,
    BudgetTargetRead,
    CategoryAverageSpend,
    CategoryBudgetStatus,
)
from app.features.finance.categories.repository import CategoryRepository
from app.features.finance.settings.service import FinanceSettingsService
from app.features.finance.transactions.repository import TransactionRepository
from app.shared.timezone import local_today

logger = logging.getLogger(__name__)


class BudgetTargetService:

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = BudgetTargetRepository(session)
        self._category_repo = CategoryRepository(session)
        self._txn_repo = TransactionRepository(session)
        self._settings = FinanceSettingsService(session)

    async def list_current_targets(self) -> list[BudgetTargetRead]:
        targets = await self._repo.list_current()
        return [BudgetTargetRead.model_validate(t) for t in targets]

    async def set_target(self, category_id: int, amount: Decimal | None) -> BudgetTargetRead | None:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        open_target = await self._repo.get_open(category_id)

        if amount is None:
            if open_target is not None:
                open_target.effective_to = now
                await self._session.commit()
                logger.info("Budget target cleared: category_id=%d", category_id)
            return None

        same_month = (
            open_target is not None
            and open_target.effective_from.year == now.year
            and open_target.effective_from.month == now.month
        )
        if same_month:
            open_target.amount = amount
            await self._session.commit()
            await self._session.refresh(open_target)
            logger.info("Budget target updated in place: category_id=%d amount=%s", category_id, amount)
            return BudgetTargetRead.model_validate(open_target)

        if open_target is not None:
            open_target.effective_to = now

        new_target = self._repo.add(category_id=category_id, amount=amount, effective_from=now)
        await self._session.commit()
        await self._session.refresh(new_target)
        logger.info("Budget target set: category_id=%d amount=%s", category_id, amount)
        return BudgetTargetRead.model_validate(new_target)

    async def set_targets_bulk(self, items: list[BudgetTargetBulkSetItem]) -> list[BudgetTargetRead]:
        results = []
        for item in items:
            result = await self.set_target(item.category_id, item.amount)
            if result is not None:
                results.append(result)
        return results

    async def get_status(self, year_month: str | None) -> list[CategoryBudgetStatus]:
        cycle_start_day = await self._settings.get_cycle_start_day()
        reference = cycle.parse_year_month_reference(year_month, cycle_start_day)
        from_date, to_date = cycle.current_cycle_range(reference, cycle_start_day)
        label = from_date.replace(day=1)

        next_month_start = datetime.combine(to_date + timedelta(days=1), datetime.min.time())
        targets = await self._repo.list_effective(next_month_start)
        categories = {c.id: c.name for c in await self._category_repo.list()}

        spent_by_category = {
            category_id: total
            for category_id, _name, total, _count in await self._txn_repo.get_spending_by_category(from_date, to_date)
        }

        results = []
        for target in targets:
            results.append(
                CategoryBudgetStatus(
                    category_id=target.category_id,
                    category_name=categories.get(target.category_id, ""),
                    year_month=label,
                    limit_amount=target.amount,
                    spent=spent_by_category.get(target.category_id, Decimal("0")),
                )
            )
        return results

    async def get_average_spend(self, months: int) -> list[CategoryAverageSpend]:
        """Average EUR spend per category over the last `months` completed cycles.

        Cycles with no spend in a category count as zero, so the average is the
        total divided by `months`. The in-progress cycle is excluded because a
        partial month would drag the baseline down.
        """
        cycle_start_day = await self._settings.get_cycle_start_day()
        # Cycles are contiguous, so one query over the whole span gives the same
        # per-category totals as summing each cycle separately.
        reference = local_today()
        _, to_date = cycle.previous_cycle_range(reference, cycle_start_day)
        from_date = to_date
        for _ in range(months):
            from_date, _ = cycle.previous_cycle_range(reference, cycle_start_day)
            reference = from_date
        rows = await self._txn_repo.get_spending_by_category(from_date, to_date)
        totals: dict[int, Decimal] = {}
        names: dict[int, str] = {}
        for category_id, category_name, total, _count in rows:
            if category_id is None:
                continue
            totals[category_id] = total
            names[category_id] = category_name or ""

        results = [
            CategoryAverageSpend(
                category_id=category_id,
                category_name=names[category_id],
                average=(total / months).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
                months=months,
            )
            for category_id, total in totals.items()
        ]
        logger.debug("Budget averages computed: months=%d categories=%d", months, len(results))
        return results

    async def current_period_label(self) -> str:
        cycle_start_day = await self._settings.get_cycle_start_day()
        from_date, _ = cycle.current_cycle_range(local_today(), cycle_start_day)
        return from_date.strftime("%Y-%m")
