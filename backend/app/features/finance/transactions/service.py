import logging
from datetime import date, timedelta
from decimal import Decimal
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

from app.features.finance.accounts.repository import AccountRepository
from app.features.finance.exchange_rates.service import ExchangeRateService
from app.features.finance.transactions.repository import TransactionRepository
from app.features.finance.transactions.schemas import (
    GLOBAL_CURRENCY,
    AnalyticsFilters,
    BalanceForecastResponse,
    CategorySpendingItem,
    SpendingAverageResponse,
    SpendingByCategoryResponse,
    SpendingOverTimeItem,
    SpendingOverTimeResponse,
    SpendingReportResponse,
    SpendingTopResponse,
    TransactionBackfillEurResponse,
    TransactionBulkMoveRequest,
    TransactionCreate,
    TransactionFilters,
    TransactionRead,
    TransactionUpdate,
    resolve_period,
)


class InvalidBulkMoveError(Exception):
    """Raised when a bulk account-move request is malformed (same source/target
    account, or a target account that doesn't exist)."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class TransactionService:

    def __init__(self, session: AsyncSession, exchange_rate_service: ExchangeRateService) -> None:
        self._repo = TransactionRepository(session)
        self._account_repo = AccountRepository(session)
        self._fx = exchange_rate_service

    async def get(self, transaction_id: int) -> TransactionRead | None:
        txn = await self._repo.get(transaction_id)
        if txn is None:
            return None
        return TransactionRead.model_validate(txn)

    async def list(self, filters: TransactionFilters) -> list[TransactionRead]:
        txns = await self._repo.list(filters)
        return [TransactionRead.model_validate(t) for t in txns]

    async def create(self, data: TransactionCreate) -> TransactionRead:
        amount_eur = await self._fx.convert_to_eur(data.amount, data.currency, data.date.date())
        txn = await self._repo.create(data, amount_eur=amount_eur)
        logger.info("Transaction created: id=%d merchant=%r", txn.id, data.merchant)
        return TransactionRead.model_validate(txn)

    async def update(self, transaction_id: int, data: TransactionUpdate) -> TransactionRead | None:
        fields = data.model_dump(exclude_unset=True)
        amount_eur: Decimal | None = None
        recompute_amount_eur = False
        if {"amount", "currency", "date"} & fields.keys():
            current = await self._repo.get(transaction_id)
            if current is None:
                logger.debug("Transaction update: id=%d not found", transaction_id)
                return None
            effective_amount = fields.get("amount", current.amount)
            effective_currency = fields.get("currency", current.currency)
            effective_date = fields.get("date", current.date)
            amount_eur = await self._fx.convert_to_eur(
                effective_amount, effective_currency, effective_date.date()
            )
            recompute_amount_eur = True

        txn = await self._repo.update(
            transaction_id, data, amount_eur=amount_eur, recompute_amount_eur=recompute_amount_eur
        )
        if txn is None:
            logger.debug("Transaction update: id=%d not found", transaction_id)
            return None
        logger.info("Transaction updated: id=%d fields=%s", transaction_id, list(fields.keys()))
        return TransactionRead.model_validate(txn)

    async def backfill_amount_eur(self, batch_size: int = 1000) -> TransactionBackfillEurResponse:
        pending = await self._repo.list_missing_amount_eur(limit=batch_size)
        updated = 0
        failed = 0
        for txn in pending:
            amount_eur = await self._fx.convert_to_eur(txn.amount, txn.currency, txn.date.date())
            if amount_eur is None:
                failed += 1
                continue
            await self._repo.set_amount_eur(txn.id, amount_eur)
            updated += 1
        remaining = await self._repo.count_missing_amount_eur()
        logger.info(
            "Transaction EUR backfill: updated=%d failed=%d remaining=%d", updated, failed, remaining
        )
        return TransactionBackfillEurResponse(
            updated_count=updated, failed_count=failed, remaining_count=remaining
        )

    async def delete(self, transaction_id: int) -> bool:
        deleted = await self._repo.delete(transaction_id)
        if deleted:
            logger.info("Transaction deleted: id=%d", transaction_id)
        else:
            logger.debug("Transaction delete: id=%d not found", transaction_id)
        return deleted

    async def bulk_move_account(self, request: TransactionBulkMoveRequest) -> int:
        if request.account_id == request.target_account_id:
            raise InvalidBulkMoveError("Source and target account must be different")
        target = await self._account_repo.get(request.target_account_id)
        if target is None:
            raise InvalidBulkMoveError("Target account not found")

        moved = await self._repo.bulk_reassign_account(request)
        logger.info(
            "Transactions bulk-moved: source_account_id=%d target_account_id=%d count=%d",
            request.account_id, request.target_account_id, moved,
        )
        return moved

    async def spending_report(self, filters: AnalyticsFilters) -> SpendingReportResponse:
        from_date, to_date = resolve_period(filters.period, filters.from_date, filters.to_date)
        total, count = await self._repo.get_spending_total(
            from_date=from_date,
            to_date=to_date,
            category_id=filters.category_id,
            account_id=filters.account_id,
            merchant=filters.merchant,
            currency=filters.currency,
        )
        return SpendingReportResponse(
            total=total,
            currency=filters.currency,
            from_date=from_date,
            to_date=to_date,
            transaction_count=count,
        )

    async def income_report(self, filters: AnalyticsFilters) -> SpendingReportResponse:
        from_date, to_date = resolve_period(filters.period, filters.from_date, filters.to_date)
        total, count = await self._repo.get_spending_total(
            from_date=from_date,
            to_date=to_date,
            category_id=filters.category_id,
            account_id=filters.account_id,
            merchant=filters.merchant,
            currency=filters.currency,
            transaction_type="income",
        )
        return SpendingReportResponse(
            total=total,
            currency=filters.currency,
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
            currency=filters.currency,
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
            currency=filters.currency,
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
            currency=filters.currency,
        )

    async def spending_over_time(self, filters: AnalyticsFilters, group_by: str) -> SpendingOverTimeResponse:
        from_date, to_date = resolve_period(filters.period, filters.from_date, filters.to_date)
        rows = await self._repo.get_spending_over_time(
            from_date=from_date,
            to_date=to_date,
            group_by=group_by,
            account_id=filters.account_id,
            currency=filters.currency,
        )
        items = [SpendingOverTimeItem(period=period, total=total) for period, total in rows]
        return SpendingOverTimeResponse(
            items=items,
            from_date=from_date,
            to_date=to_date,
            currency=filters.currency,
            group_by=group_by,
        )

    async def spending_top(self, filters: AnalyticsFilters) -> SpendingTopResponse:
        from_date, to_date = resolve_period(filters.period, filters.from_date, filters.to_date)
        txns = await self._repo.get_top_expenses(
            from_date=from_date,
            to_date=to_date,
            top_n=filters.top_n,
            category_id=filters.category_id,
            currency=filters.currency,
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
            parts = {k: v for k, v in (p.split("=", 1) for p in rt.recurrence_rule.upper().split(";") if "=" in p)}
            freq = parts.get("FREQ", rt.recurrence_rule.upper().split(";")[0]).lower()
            interval = int(parts.get("INTERVAL", "1"))
            if freq == "weekly" and interval == 2:
                freq = "biweekly"
            multiplier = Decimal(str(rule_multipliers.get(freq, 0)))
            projected_amount = rt.amount * multiplier
            if rt.type == "income":
                projected_income += projected_amount
            else:
                projected_expenses += projected_amount

        return projected_income, projected_expenses, forecast_to
