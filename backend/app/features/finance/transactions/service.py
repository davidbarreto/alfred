from datetime import date, timedelta
from decimal import Decimal
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.finance.transactions.repository import TransactionRepository
from app.features.finance.transactions.schemas import (
    AnalyticsFilters,
    BalanceForecastResponse,
    CategorySpendingItem,
    SpendingAverageResponse,
    SpendingByCategoryResponse,
    SpendingReportResponse,
    SpendingTopResponse,
    TransactionCreate,
    TransactionFilters,
    TransactionRead,
    TransactionUpdate,
    resolve_period,
)


class TransactionService:

    def __init__(self, session: AsyncSession) -> None:
        self._repo = TransactionRepository(session)

    async def get(self, transaction_id: int) -> TransactionRead | None:
        txn = await self._repo.get(transaction_id)
        if txn is None:
            return None
        return TransactionRead.model_validate(txn)

    async def list(self, filters: TransactionFilters) -> list[TransactionRead]:
        txns = await self._repo.list(filters)
        return [TransactionRead.model_validate(t) for t in txns]

    async def create(self, data: TransactionCreate) -> TransactionRead:
        txn = await self._repo.create(data)
        return TransactionRead.model_validate(txn)

    async def update(self, transaction_id: int, data: TransactionUpdate) -> TransactionRead | None:
        txn = await self._repo.update(transaction_id, data)
        if txn is None:
            return None
        return TransactionRead.model_validate(txn)

    async def delete(self, transaction_id: int) -> bool:
        return await self._repo.delete(transaction_id)

    async def spending_report(self, filters: AnalyticsFilters) -> SpendingReportResponse:
        from_date, to_date = resolve_period(filters.period, filters.from_date, filters.to_date)
        total, count = await self._repo.get_spending_total(
            from_date=from_date,
            to_date=to_date,
            category_id=filters.category_id,
            account_id=filters.account_id,
            merchant=filters.merchant,
        )
        return SpendingReportResponse(
            total=total,
            currency="EUR",
            from_date=from_date,
            to_date=to_date,
            transaction_count=count,
        )

    async def spending_average(self, filters: AnalyticsFilters) -> SpendingAverageResponse:
        from_date, to_date = resolve_period(filters.period, filters.from_date, filters.to_date)
        total, _ = await self._repo.get_spending_total(
            from_date=from_date,
            to_date=to_date,
            category_id=filters.category_id,
        )
        days = max((to_date - from_date).days + 1, 1)
        average_per_day = total / days if days > 0 else Decimal("0")
        return SpendingAverageResponse(
            average_per_day=average_per_day.quantize(Decimal("0.01")),
            total=total,
            days=days,
            from_date=from_date,
            to_date=to_date,
        )

    async def spending_by_category(self, filters: AnalyticsFilters) -> SpendingByCategoryResponse:
        from_date, to_date = resolve_period(filters.period, filters.from_date, filters.to_date)
        rows = await self._repo.get_spending_by_category(
            from_date=from_date,
            to_date=to_date,
            account_id=filters.account_id,
        )
        items = [
            CategorySpendingItem(
                category_id=row[0],
                category_name=row[1],
                total=row[2],
                transaction_count=row[3],
            )
            for row in rows
        ]
        return SpendingByCategoryResponse(
            items=items,
            from_date=from_date,
            to_date=to_date,
            currency="EUR",
        )

    async def spending_top(self, filters: AnalyticsFilters) -> SpendingTopResponse:
        from_date, to_date = resolve_period(filters.period, filters.from_date, filters.to_date)
        txns = await self._repo.get_top_expenses(
            from_date=from_date,
            to_date=to_date,
            top_n=filters.top_n,
            category_id=filters.category_id,
        )
        return SpendingTopResponse(
            transactions=[TransactionRead.model_validate(t) for t in txns],
            from_date=from_date,
            to_date=to_date,
            top_n=filters.top_n,
        )

    async def balance_forecast(
        self,
        filters: AnalyticsFilters,
        recurring_transactions: list,
    ) -> BalanceForecastResponse:
        """
        Project the balance to the end of the forecast period.
        Requires the list of active recurring transactions passed in from the caller
        to avoid a cross-service DB call inside this service.
        """
        today = date.today()
        _, forecast_to = resolve_period(filters.period, filters.from_date, filters.to_date)

        # Sum balances from account service is done at the route level; we accept
        # current_balance as a parameter injected by the route handler.
        # Here we compute projected cash flows from recurring transactions.
        projected_income = Decimal("0")
        projected_expenses = Decimal("0")

        days_remaining = max((forecast_to - today).days, 0)
        months_remaining = days_remaining / 30

        rule_multipliers = {
            "daily": days_remaining,
            "weekly": days_remaining / 7,
            "biweekly": days_remaining / 14,
            "monthly": months_remaining,
            "yearly": months_remaining / 12,
        }

        for rt in recurring_transactions:
            multiplier = Decimal(str(rule_multipliers.get(rt.recurrence_rule.lower(), 0)))
            projected_amount = rt.amount * multiplier
            if rt.type == "income":
                projected_income += projected_amount
            else:
                projected_expenses += projected_amount

        return projected_income, projected_expenses, forecast_to
