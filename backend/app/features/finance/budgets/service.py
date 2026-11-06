from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.finance import cycle
from app.features.finance.budgets.repository import BudgetTargetRepository
from app.features.finance.budgets.schemas import (
    BudgetHistoryCycle,
    BudgetTargetBulkSetItem,
    BudgetTargetRead,
    CategoryAverageSpend,
    CategoryBudgetStatus,
    CurrentPeriodResponse,
    TagBudgetStatus,
    TagBudgetTargetBulkSetItem,
)
from app.features.finance.budgets.tables import BudgetTarget
from app.features.finance.categories.repository import CategoryRepository
from app.features.finance.settings.service import FinanceSettingsService
from app.features.finance.tags.repository import TagRepository
from app.features.finance.transactions.repository import TransactionRepository
from app.shared.timezone import local_today

logger = logging.getLogger(__name__)


class BudgetTagNotFoundError(Exception):
    """Raised when a tag budget is set for a tag that doesn't exist."""


class BudgetTargetService:

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = BudgetTargetRepository(session)
        self._category_repo = CategoryRepository(session)
        self._tag_repo = TagRepository(session)
        self._txn_repo = TransactionRepository(session)
        self._settings = FinanceSettingsService(session)

    async def list_current_targets(self) -> list[BudgetTargetRead]:
        targets = await self._repo.list_current()
        return [BudgetTargetRead.model_validate(t) for t in targets]

    async def set_target(self, category_id: int, amount: Decimal | None) -> BudgetTargetRead | None:
        """Set or clear a category's budget, versioned per cycle.

        A change takes effect from the start of the current cycle. Editing again
        within the same cycle overwrites that version; editing in a later cycle
        closes the old version at the cycle boundary and opens a new one, so past
        cycles keep the budget that applied then.
        """
        open_target = await self._repo.get_open(category_id)
        return await self._apply_target(open_target, amount, {"category_id": category_id}, f"category_id={category_id}")

    async def set_tag_target(self, tag_id: int, amount: Decimal | None) -> BudgetTargetRead | None:
        """Set or clear a tag's budget, versioned per cycle exactly like a category's.

        While it is open, transactions carrying the tag count toward it and no longer
        toward their category's budget.
        """
        if amount is not None and await self._tag_repo.get_tag(tag_id) is None:
            raise BudgetTagNotFoundError(tag_id)
        open_target = await self._repo.get_open_tag(tag_id)
        return await self._apply_target(open_target, amount, {"tag_id": tag_id}, f"tag_id={tag_id}")

    async def _apply_target(
        self, open_target: BudgetTarget | None, amount: Decimal | None, subject: dict, label: str
    ) -> BudgetTargetRead | None:
        cycle_start_day = await self._settings.get_cycle_start_day()
        from_date, _ = cycle.current_cycle_range(local_today(), cycle_start_day)
        cycle_start = datetime.combine(from_date, time.min)

        if amount is None:
            if open_target is not None:
                open_target.effective_to = cycle_start
                await self._session.commit()
                logger.info("Budget target cleared: %s", label)
            return None

        if open_target is not None and open_target.effective_from >= cycle_start:
            open_target.amount = amount
            await self._session.commit()
            await self._session.refresh(open_target)
            logger.info("Budget target updated in place: %s amount=%s", label, amount)
            return BudgetTargetRead.model_validate(open_target)

        if open_target is not None:
            open_target.effective_to = cycle_start

        new_target = self._repo.add(amount=amount, effective_from=cycle_start, **subject)
        await self._session.commit()
        await self._session.refresh(new_target)
        logger.info("Budget target set: %s amount=%s", label, amount)
        return BudgetTargetRead.model_validate(new_target)

    async def set_targets_bulk(
        self,
        items: list[BudgetTargetBulkSetItem],
        tag_items: list[TagBudgetTargetBulkSetItem] | None = None,
    ) -> list[BudgetTargetRead]:
        results = []
        for item in items:
            result = await self.set_target(item.category_id, item.amount)
            if result is not None:
                results.append(result)
        for tag_item in tag_items or []:
            result = await self.set_tag_target(tag_item.tag_id, tag_item.amount)
            if result is not None:
                results.append(result)
        return results

    async def get_status(self, year_month: str | None) -> list[CategoryBudgetStatus]:
        from_date, to_date = await self._cycle_for(year_month)
        categories = {c.id: c.name for c in await self._category_repo.list()}
        items, _tag_items = await self._status_for_cycle(from_date, to_date, categories)
        return items

    async def get_tag_status(self, year_month: str | None) -> list[TagBudgetStatus]:
        from_date, to_date = await self._cycle_for(year_month)
        _items, tag_items = await self._status_for_cycle(from_date, to_date, {})
        return tag_items

    async def _cycle_for(self, year_month: str | None) -> tuple[date, date]:
        cycle_start_day = await self._settings.get_cycle_start_day()
        reference = cycle.parse_year_month_reference(year_month, cycle_start_day)
        return cycle.current_cycle_range(reference, cycle_start_day)

    async def get_history(self, cycles: int) -> list[BudgetHistoryCycle]:
        """Budget vs. spend for the current cycle and the `cycles - 1` before it, newest first."""
        cycle_start_day = await self._settings.get_cycle_start_day()
        categories = {c.id: c.name for c in await self._category_repo.list()}
        from_date, to_date = cycle.current_cycle_range(local_today(), cycle_start_day)
        history = []
        for _ in range(cycles):
            items, tag_items = await self._status_for_cycle(from_date, to_date, categories)
            history.append(
                BudgetHistoryCycle(
                    year_month=from_date.strftime("%Y-%m"),
                    from_date=from_date,
                    to_date=to_date,
                    items=items,
                    tag_items=tag_items,
                )
            )
            from_date, to_date = cycle.previous_cycle_range(from_date, cycle_start_day)
        return history

    async def _status_for_cycle(
        self, from_date: date, to_date: date, categories: dict[int, str]
    ) -> tuple[list[CategoryBudgetStatus], list[TagBudgetStatus]]:
        """Category and tag budget status for one cycle.

        A transaction counts toward exactly one budget: a tag's when it carries a budgeted
        tag (the oldest such budget if it carries several), its category's otherwise.
        """
        cycle_start = datetime.combine(from_date, time.min)
        cycle_end = datetime.combine(to_date + timedelta(days=1), time.min)
        tag_targets = await self._repo.list_effective_tags(cycle_start, cycle_end)
        budgeted_tag_ids = [t.tag_id for t in tag_targets]

        tag_items: list[TagBudgetStatus] = []
        if tag_targets:
            tag_names = {t.id: t.name for t in await self._tag_repo.get_tags()}
            older_tag_ids: list[int] = []
            for target in tag_targets:
                spent, overlap = await self._txn_repo.get_tag_budget_spending(
                    from_date, to_date, target.tag_id, list(older_tag_ids)
                )
                tag_items.append(
                    TagBudgetStatus(
                        tag_id=target.tag_id,
                        tag_name=tag_names.get(target.tag_id, ""),
                        year_month=from_date.replace(day=1),
                        limit_amount=target.amount,
                        spent=spent,
                        overlap_count=overlap,
                    )
                )
                older_tag_ids.append(target.tag_id)

        targets = await self._repo.list_effective(cycle_start, cycle_end)
        spent_by_category = {
            category_id: total
            for category_id, _name, total, _count in await self._txn_repo.get_spending_by_category(
                from_date, to_date, exclude_tag_ids=budgeted_tag_ids
            )
        }
        category_items = [
            CategoryBudgetStatus(
                category_id=target.category_id,
                category_name=categories.get(target.category_id, ""),
                year_month=from_date.replace(day=1),
                limit_amount=target.amount,
                spent=spent_by_category.get(target.category_id, Decimal("0")),
            )
            for target in targets
        ]
        return category_items, tag_items

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

    async def get_period(self, year_month: str | None) -> CurrentPeriodResponse:
        """The cycle named by `year_month` (today's when omitted) with its date range."""
        cycle_start_day = await self._settings.get_cycle_start_day()
        reference = cycle.parse_year_month_reference(year_month, cycle_start_day)
        from_date, to_date = cycle.current_cycle_range(reference, cycle_start_day)
        return CurrentPeriodResponse(
            year_month=from_date.strftime("%Y-%m"), from_date=from_date, to_date=to_date
        )
