import logging
from datetime import date, timedelta
from decimal import Decimal
from typing import List
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

from app.features.finance.accounts.repository import AccountRepository
from app.features.finance.accounts.schemas import AccountFilters
from app.features.finance.exchange_rates.service import ExchangeRateService
from app.features.finance.settings.service import FinanceSettingsService
from app.features.finance.transactions.repository import TransactionRepository
from app.features.finance.transactions.tables import Transaction
from app.features.finance.transactions.schemas import (
    GLOBAL_CURRENCY,
    AccountSpendingItem,
    AnalyticsFilters,
    BalanceForecastResponse,
    CategorySpendingItem,
    IncomeExpenseOverTimeItem,
    IncomeExpenseOverTimeResponse,
    NetWorthFilters,
    NetWorthHistoryItem,
    NetWorthHistoryResponse,
    SpendingAverageResponse,
    SpendingByAccountResponse,
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
    TransactionSumResponse,
    TransactionUpdate,
    resolve_period,
)


def _account_delta(type_: str, amount: Decimal) -> Decimal:
    """Signed effect of a transaction on its own account's balance -- income credits,
    expense and transfer (the source leg; a transfer's counterpart leg is applied
    separately by the caller) debit. Mirrors TransactionRepository.get_ledger_events'
    delta convention so incremental Account.balance maintenance and the net-worth
    ledger reconstruction never disagree.
    """
    return amount if type_ == "income" else -amount


def build_mirror_transaction_create(source: Transaction) -> TransactionCreate:
    """The auto-generated counterpart-account echo of a transfer whose counterpart
    account has auto_mirror_transfers enabled (see Account.auto_mirror_transfers).
    Carries no balance effect of its own -- the source leg's existing counterpart
    credit (see create()/_reconcile_balance()) already moves the money; this only
    makes the transfer visible in the counterpart account's own transaction list.
    Shared by TransactionService and ImportService so both paths mirror identically.
    """
    return TransactionCreate(
        account_id=source.counterpart_account_id,
        date=source.date,
        amount=-source.amount,
        currency=source.currency,
        type="transfer",
        description=source.description,
        bank_description=source.bank_description,
        merchant=source.merchant,
        source="auto_transfer",
        counterpart_account_id=None,
        generated_from_transaction_id=source.id,
    )


class InvalidBulkMoveError(Exception):
    """Raised when a bulk account-move request is malformed (same source/target
    account, or a target account that doesn't exist)."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class TransferMatchError(Exception):
    """Raised when a suggested transfer link is no longer valid at confirm time (one
    side was edited/deleted/already linked since the candidate list was fetched)."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class TransactionService:

    def __init__(self, session: AsyncSession, exchange_rate_service: ExchangeRateService) -> None:
        self._repo = TransactionRepository(session)
        self._account_repo = AccountRepository(session)
        self._fx = exchange_rate_service
        self._settings = FinanceSettingsService(session)

    async def _resolve_period(self, filters) -> tuple[date, date]:
        cycle_start_day = await self._settings.get_cycle_start_day()
        return resolve_period(filters.period, filters.from_date, filters.to_date, cycle_start_day)

    async def get(self, transaction_id: int) -> TransactionRead | None:
        txn = await self._repo.get(transaction_id)
        if txn is None:
            return None
        return TransactionRead.model_validate(txn)

    async def list(self, filters: TransactionFilters) -> list[TransactionRead]:
        cycle_start_day = await self._settings.get_cycle_start_day()
        txns = await self._repo.list(filters, cycle_start_day)
        return [TransactionRead.model_validate(t) for t in txns]

    async def filtered_sum(self, filters: TransactionFilters) -> TransactionSumResponse:
        cycle_start_day = await self._settings.get_cycle_start_day()
        total, count = await self._repo.get_filtered_sum(filters, cycle_start_day)
        return TransactionSumResponse(
            total=total,
            transaction_count=count,
            currency=filters.currency or GLOBAL_CURRENCY,
        )

    async def create(self, data: TransactionCreate) -> TransactionRead:
        amount_eur = await self._fx.convert_to_eur(data.amount, data.currency, data.date.date())
        txn = await self._repo.create(data, amount_eur=amount_eur)
        await self._account_repo.adjust_balance(data.account_id, _account_delta(data.type, data.amount))
        if data.type == "transfer" and data.counterpart_account_id is not None:
            await self._account_repo.adjust_balance(data.counterpart_account_id, data.amount)
            await self._maybe_create_mirror(txn)
        logger.info("Transaction created: id=%d merchant=%r", txn.id, data.merchant)
        return TransactionRead.model_validate(txn)

    async def _maybe_create_mirror(self, source: Transaction) -> None:
        counterpart = await self._account_repo.get(source.counterpart_account_id)
        if counterpart is None or not counterpart.auto_mirror_transfers:
            return
        mirror = await self._repo.create(
            build_mirror_transaction_create(source),
            amount_eur=(-source.amount_eur if source.amount_eur is not None else None),
        )
        logger.info(
            "Auto-mirror transaction created: id=%d source_id=%d account_id=%d",
            mirror.id, source.id, mirror.account_id,
        )

    async def update(self, transaction_id: int, data: TransactionUpdate) -> TransactionRead | None:
        current = await self._repo.get(transaction_id)
        if current is None:
            logger.debug("Transaction update: id=%d not found", transaction_id)
            return None

        fields = data.model_dump(exclude_unset=True)
        amount_eur: Decimal | None = None
        recompute_amount_eur = False
        if {"amount", "currency", "date"} & fields.keys():
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
        await self._reconcile_balance(old=current, new=txn)
        await self._sync_mirror(old=current, new=txn)
        logger.info("Transaction updated: id=%d fields=%s", transaction_id, list(fields.keys()))
        return TransactionRead.model_validate(txn)

    async def _reconcile_balance(self, old, new) -> None:
        """Reverse a transaction's old balance effect and apply its new one -- covers
        every field an update could change (amount, type, account, counterpart).
        A mirror row (generated_from_transaction_id set) carries no balance effect of
        its own -- see create()/delete() -- so editing one directly is a no-op here.
        """
        if old.generated_from_transaction_id is not None:
            return
        await self._account_repo.adjust_balance(
            old.account_id, -_account_delta(old.type, old.amount)
        )
        if old.type == "transfer" and old.counterpart_account_id is not None:
            await self._account_repo.adjust_balance(old.counterpart_account_id, -old.amount)
        await self._account_repo.adjust_balance(
            new.account_id, _account_delta(new.type, new.amount)
        )
        if new.type == "transfer" and new.counterpart_account_id is not None:
            await self._account_repo.adjust_balance(new.counterpart_account_id, new.amount)

    async def _sync_mirror(self, old, new) -> None:
        """Keep an auto-generated counterpart mirror row (see create()) in step with
        edits to its source leg -- content only, never balance (mirrors carry none).
        Creates one if the edit newly qualifies (e.g. counterpart_account_id changed
        to a mirrored account), removes it if the edit no longer qualifies, or moves
        it to the new counterpart account if that changed.
        """
        if old.generated_from_transaction_id is not None:
            return
        mirror = await self._repo.get_mirror(old.id)
        counterpart = None
        if new.type == "transfer" and new.counterpart_account_id is not None:
            counterpart = await self._account_repo.get(new.counterpart_account_id)
        wants_mirror = counterpart is not None and counterpart.auto_mirror_transfers

        if not wants_mirror:
            if mirror is not None:
                await self._repo.delete(mirror.id)
            return

        if mirror is not None and mirror.account_id == new.counterpart_account_id:
            await self._repo.update(
                mirror.id,
                TransactionUpdate(
                    date=new.date, amount=-new.amount, currency=new.currency, description=new.description,
                    merchant=new.merchant,
                ),
                amount_eur=(-new.amount_eur if new.amount_eur is not None else None),
                recompute_amount_eur=True,
            )
        else:
            if mirror is not None:
                await self._repo.delete(mirror.id)
            await self._repo.create(
                build_mirror_transaction_create(new),
                amount_eur=(-new.amount_eur if new.amount_eur is not None else None),
            )

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
        txn = await self._repo.get(transaction_id)
        if txn is None:
            logger.debug("Transaction delete: id=%d not found", transaction_id)
            return False
        deleted = await self._repo.delete(transaction_id)
        if deleted:
            # A mirror row (generated_from_transaction_id set) carries no balance
            # effect of its own -- see create() -- deleting one directly is balance-
            # neutral. Deleting the source leg cascades its mirror row away at the DB
            # level (ondelete="CASCADE"); the source leg's own reversal below already
            # undoes the money movement, so nothing extra is needed for the mirror.
            if txn.generated_from_transaction_id is None:
                await self._account_repo.adjust_balance(
                    txn.account_id, -_account_delta(txn.type, txn.amount)
                )
                if txn.type == "transfer" and txn.counterpart_account_id is not None:
                    await self._account_repo.adjust_balance(txn.counterpart_account_id, -txn.amount)
            logger.info("Transaction deleted: id=%d", transaction_id)
        return deleted

    async def get_transfer_match_candidates(self, transaction_id: int) -> List[TransactionRead]:
        transaction = await self._repo.get(transaction_id)
        if transaction is None or transaction.type != "transfer" or transaction.counterpart_account_id is not None:
            return []
        candidates = await self._repo.get_transfer_match_candidates(transaction)
        return [TransactionRead.model_validate(c) for c in candidates]

    async def link_transfer(self, transaction_id: int, counterpart_transaction_id: int) -> TransactionRead:
        """Link two independently-imported transfer legs as each other's counterpart --
        see TransferLinkRequest. Always user-confirmed (the caller already chose this
        counterpart from get_transfer_match_candidates); re-validated here since either
        side could have changed since the candidate list was fetched.
        """
        if transaction_id == counterpart_transaction_id:
            raise TransferMatchError("A transaction cannot be linked to itself")
        transaction = await self._repo.get(transaction_id)
        counterpart = await self._repo.get(counterpart_transaction_id)
        if transaction is None or counterpart is None:
            raise TransferMatchError("Transaction not found")
        if transaction.type != "transfer" or counterpart.type != "transfer":
            raise TransferMatchError("Both transactions must be transfers")
        if transaction.counterpart_account_id is not None or counterpart.counterpart_account_id is not None:
            raise TransferMatchError("One of the transactions is already linked")
        if transaction.account_id == counterpart.account_id:
            raise TransferMatchError("Cannot link two legs on the same account")
        if transaction.date.date() != counterpart.date.date():
            raise TransferMatchError("Dates do not match")

        # Mirrors TransactionRepository.get_transfer_match_candidates' two match
        # strategies: same currency + exactly opposite amount (a plain transfer split
        # across separate imports), or identical bank_description + opposite sign (a
        # currency exchange, where legs are in different currencies with an
        # FX-converted, not exactly opposite, amount).
        same_currency_opposite_amount = (
            transaction.currency == counterpart.currency and transaction.amount == -counterpart.amount
        )
        same_description_opposite_sign = (
            transaction.bank_description is not None
            and transaction.bank_description == counterpart.bank_description
            and (transaction.amount > 0) != (counterpart.amount > 0)
        )
        if not same_currency_opposite_amount and not same_description_opposite_sign:
            raise TransferMatchError("Amounts do not match")

        updated = await self._repo.update(
            transaction.id, TransactionUpdate(counterpart_account_id=counterpart.account_id)
        )
        await self._repo.update(
            counterpart.id, TransactionUpdate(counterpart_account_id=transaction.account_id)
        )
        logger.info("Transfer linked: id=%d counterpart_id=%d", transaction.id, counterpart.id)
        return TransactionRead.model_validate(updated)

    async def bulk_move_account(self, request: TransactionBulkMoveRequest) -> int:
        if request.account_id == request.target_account_id:
            raise InvalidBulkMoveError("Source and target account must be different")
        target = await self._account_repo.get(request.target_account_id)
        if target is None:
            raise InvalidBulkMoveError("Target account not found")

        cycle_start_day = await self._settings.get_cycle_start_day()
        moved = await self._repo.bulk_reassign_account(request, cycle_start_day)
        logger.info(
            "Transactions bulk-moved: source_account_id=%d target_account_id=%d count=%d",
            request.account_id, request.target_account_id, moved,
        )
        return moved

    async def spending_report(self, filters: AnalyticsFilters) -> SpendingReportResponse:
        from_date, to_date = await self._resolve_period(filters)
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
        from_date, to_date = await self._resolve_period(filters)
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
        from_date, to_date = await self._resolve_period(filters)
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
        from_date, to_date = await self._resolve_period(filters)
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
        from_date, to_date = await self._resolve_period(filters)
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

    async def spending_by_account(self, filters: AnalyticsFilters) -> SpendingByAccountResponse:
        from_date, to_date = await self._resolve_period(filters)
        rows = await self._repo.get_spending_by_account(
            from_date=from_date,
            to_date=to_date,
            category_id=filters.category_id,
            currency=filters.currency,
        )
        items = [
            AccountSpendingItem(
                account_id=row[0],
                account_name=row[1],
                total=row[2],
                transaction_count=row[3],
            )
            for row in rows
        ]
        return SpendingByAccountResponse(
            items=items,
            from_date=from_date,
            to_date=to_date,
            currency=filters.currency,
        )

    async def income_vs_expense_over_time(
        self, filters: AnalyticsFilters, group_by: str
    ) -> IncomeExpenseOverTimeResponse:
        from_date, to_date = await self._resolve_period(filters)
        expense_rows = await self._repo.get_spending_over_time(
            from_date=from_date,
            to_date=to_date,
            group_by=group_by,
            account_id=filters.account_id,
            currency=filters.currency,
            transaction_type="expense",
        )
        income_rows = await self._repo.get_spending_over_time(
            from_date=from_date,
            to_date=to_date,
            group_by=group_by,
            account_id=filters.account_id,
            currency=filters.currency,
            transaction_type="income",
        )
        expense_by_period = dict(expense_rows)
        income_by_period = dict(income_rows)
        periods = sorted(set(expense_by_period) | set(income_by_period))
        items = [
            IncomeExpenseOverTimeItem(
                period=period,
                income=income_by_period.get(period, Decimal("0")),
                expense=expense_by_period.get(period, Decimal("0")),
            )
            for period in periods
        ]
        return IncomeExpenseOverTimeResponse(
            items=items,
            from_date=from_date,
            to_date=to_date,
            currency=filters.currency,
            group_by=group_by,
        )

    async def net_worth_history(
        self, filters: NetWorthFilters, group_by: str
    ) -> NetWorthHistoryResponse:
        """Reconstruct a running total-balance series from the transaction
        ledger (see TransactionRepository.get_ledger_events) plus each
        account's optional opening_balance anchor, rather than from
        Account.balance -- which is a manually-edited snapshot with no
        guaranteed link to transaction history.
        """
        account_filters = AccountFilters(
            currency=None if filters.currency == GLOBAL_CURRENCY else filters.currency
        )
        accounts = await self._account_repo.list(account_filters)

        events: list[tuple[int, date, Decimal]] = [
            (account.id, account.opening_balance_date, account.opening_balance)
            for account in accounts
            if account.opening_balance_date is not None and account.opening_balance is not None
        ]
        events.extend(await self._repo.get_ledger_events(filters.to_date, filters.currency))
        events.sort(key=lambda event: event[1])

        key_format = "%Y-%m" if group_by == "month" else "%Y-%m-%d"
        running_total = Decimal("0")
        bucket_totals: dict[str, Decimal] = {}
        total_before_from_date = Decimal("0")
        for _account_id, event_date, delta in events:
            running_total += delta
            if filters.from_date is not None and event_date < filters.from_date:
                total_before_from_date = running_total
                continue
            bucket_totals[event_date.strftime(key_format)] = running_total

        items = [
            NetWorthHistoryItem(period=period, total=total)
            for period, total in sorted(bucket_totals.items())
        ]
        if filters.from_date is not None:
            anchor_period = filters.from_date.strftime(key_format)
            if not items or items[0].period != anchor_period:
                items.insert(
                    0, NetWorthHistoryItem(period=anchor_period, total=total_before_from_date)
                )

        return NetWorthHistoryResponse(
            items=items,
            from_date=filters.from_date,
            to_date=filters.to_date,
            currency=filters.currency,
            group_by=group_by,
        )

    async def spending_top(self, filters: AnalyticsFilters) -> SpendingTopResponse:
        from_date, to_date = await self._resolve_period(filters)
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
        _, forecast_to = await self._resolve_period(filters)

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
