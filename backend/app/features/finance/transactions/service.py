import logging
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import List
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

from app.features.finance.accounts.repository import AccountRepository
from app.features.finance.accounts.schemas import AccountFilters
from app.features.finance.exchange_rates.service import ExchangeRateService
from app.features.finance.installment_plans.repository import InstallmentPlanRepository
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
    TransactionCountItem,
    TransactionCoverageResponse,
    TransactionCreate,
    TransactionFilters,
    TransactionRead,
    TransactionSumResponse,
    TransactionUpdate,
    TransferMatchCandidate,
    UnmatchedTransferAccount,
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

    counterpart_transaction_id=source.id points the mirror back at its source --
    source.id is already known here since the mirror is only ever built after the
    source has been committed. source="auto_transfer" is what distinguishes a mirror
    from an ordinary Find Match-confirmed leg (both share the same counterpart_transaction_id
    concept). The reverse pointer (source's own counterpart_transaction_id -> mirror.id)
    is set by the caller once the mirror row has its own id (see _maybe_create_mirror /
    _sync_mirror / ImportService._create_transfer_mirrors).
    """
    return TransactionCreate(
        account_id=source.counterpart_account_id,
        date=source.date,
        amount=-source.amount,
        currency=source.currency,
        type="transfer",
        description=source.description,
        bank_description=source.bank_description,
        note=f"Auto-mirrored from transfer match. {source.note}" if source.note else "Auto-mirrored from transfer match",
        merchant=source.merchant,
        source="auto_transfer",
        counterpart_account_id=None,
        counterpart_transaction_id=source.id,
    )


@dataclass
class _TransactionSnapshot:
    """Plain pre-update copy of the fields _reconcile_balance/_sync_mirror/
    _sync_counterpart_link compare against. Needed because TransactionRepository.get()
    and .update() run in the same session and share SQLAlchemy's identity map -- both
    calls return the *same* Transaction object for a given id, so update()'s setattr
    mutates it in place. Without this snapshot, the "old" values passed to those
    helpers would already reflect the post-update state (same object, not a copy),
    making every diff against "new" compare a row to itself.
    """

    id: int
    source: str | None
    account_id: int
    type: str
    amount: Decimal
    counterpart_account_id: int | None
    counterpart_transaction_id: int | None

    @classmethod
    def of(cls, txn: Transaction) -> "_TransactionSnapshot":
        return cls(
            id=txn.id,
            source=txn.source,
            account_id=txn.account_id,
            type=txn.type,
            amount=txn.amount,
            counterpart_account_id=txn.counterpart_account_id,
            counterpart_transaction_id=txn.counterpart_transaction_id,
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
        self._plan_repo = InstallmentPlanRepository(session)
        self._fx = exchange_rate_service
        self._settings = FinanceSettingsService(session)

    async def _effective_transfer_match(self, txn: Transaction) -> tuple[Decimal, date]:
        """(amount, reference date) to validate a transfer link against. A transaction
        anchoring an installment plan (own amount zeroed -- see
        TransactionRepository.create_placeholder_for_plan) has no real amount/date of
        its own to compare; substitute the plan's original_amount/opened_date,
        mirroring TransactionRepository.get_transfer_match_candidates.
        """
        if txn.installment_plan_id is not None and txn.amount == 0:
            plan = await self._plan_repo.get(txn.installment_plan_id)
            if plan is not None and plan.original_amount is not None:
                return plan.original_amount, plan.opened_date
        return txn.amount, txn.date.date()

    async def _resolve_period(self, filters) -> tuple[date, date]:
        cycle_start_day = await self._settings.get_cycle_start_day()
        return resolve_period(filters.period, filters.from_date, filters.to_date, cycle_start_day)

    async def get(self, transaction_id: int) -> TransactionRead | None:
        txn = await self._repo.get(transaction_id)
        if txn is None:
            return None
        return TransactionRead.model_validate(txn)

    async def get_related(self, transaction_id: int) -> TransactionRead | None:
        transaction = await self._repo.get(transaction_id)
        if transaction is None:
            return None
        related = await self._repo.get_related(transaction)
        if related is None:
            return None
        return TransactionRead.model_validate(related)

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
        await self._repo.set_counterpart_transaction(source.id, mirror.id)
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

        # Snapshot before repo.update() mutates `current` in place -- see
        # _TransactionSnapshot for why old/new would otherwise alias the same object.
        old = _TransactionSnapshot.of(current)

        txn = await self._repo.update(
            transaction_id, data, amount_eur=amount_eur, recompute_amount_eur=recompute_amount_eur
        )
        if txn is None:
            logger.debug("Transaction update: id=%d not found", transaction_id)
            return None
        await self._reconcile_balance(old=old, new=txn)
        mirror_related = await self._sync_mirror(old=old, new=txn)
        if not mirror_related:
            await self._sync_counterpart_link(old=old, new=txn, fields=fields)
        logger.info("Transaction updated: id=%d fields=%s", transaction_id, list(fields.keys()))
        return TransactionRead.model_validate(txn)

    async def _sync_counterpart_link(self, old, new, fields) -> None:
        """Editing any field a confirmed match was validated against (see
        link_transfer) invalidates it -- clears counterpart_transaction_id on both
        legs rather than leaving a stale, no-longer-accurate confirmed pairing.
        """
        if old.counterpart_transaction_id is None:
            return
        invalidating_fields = {"type", "counterpart_account_id", "amount", "currency", "date", "account_id"}
        if not invalidating_fields & fields.keys():
            return
        counterpart_id = old.counterpart_transaction_id
        await self._repo.set_counterpart_transaction(new.id, None)
        await self._repo.set_counterpart_transaction(counterpart_id, None)
        logger.info("Transfer link invalidated by edit: id=%d counterpart_id=%d", new.id, counterpart_id)

    async def _reconcile_balance(self, old, new) -> None:
        """Reverse a transaction's old balance effect and apply its new one -- covers
        every field an update could change (amount, type, account, counterpart).
        A mirror row (source == "auto_transfer") carries no balance effect of its own
        -- see create()/delete() -- so editing one directly is a no-op here.
        """
        if old.source == "auto_transfer":
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

    async def _sync_mirror(self, old, new) -> bool:
        """Keep an auto-generated counterpart mirror row (see create()) in step with
        edits to its source leg -- content only, never balance (mirrors carry none).
        Creates one if the edit newly qualifies (e.g. counterpart_account_id changed
        to a mirrored account), removes it if the edit no longer qualifies, or moves
        it to the new counterpart account if that changed.

        Returns True whenever this transaction's counterpart_transaction_id is (or
        was, or becomes) a mirror relationship rather than an ordinary Find
        Match-confirmed pair -- the caller should then skip _sync_counterpart_link's
        invalidation logic entirely, since this method already owns the mirror link's
        full lifecycle (including its pointer to/from the source leg) and editing a
        mirrored transfer's amount/date/etc. must never be treated as breaking the
        match the way it would for two independently-imported legs.
        """
        if old.source == "auto_transfer":
            return True
        mirror = await self._repo.get_mirror(old.id)
        counterpart = None
        if new.type == "transfer" and new.counterpart_account_id is not None:
            counterpart = await self._account_repo.get(new.counterpart_account_id)
        wants_mirror = counterpart is not None and counterpart.auto_mirror_transfers

        if not wants_mirror:
            if mirror is not None:
                await self._repo.delete(mirror.id)
                return True
            return False

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
            new_mirror = await self._repo.create(
                build_mirror_transaction_create(new),
                amount_eur=(-new.amount_eur if new.amount_eur is not None else None),
            )
            await self._repo.set_counterpart_transaction(new.id, new_mirror.id)
        return True

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
            # A mirror row (source == "auto_transfer") carries no balance effect of
            # its own -- see create() -- deleting one directly is balance-neutral.
            # Deleting the source leg does NOT cascade-delete its mirror (
            # counterpart_transaction_id is ondelete="SET NULL", not CASCADE) --  the
            # mirror is left orphaned rather than cleaned up automatically. Accepted
            # trade-off for sharing one column with confirmed Find Match links, which
            # must never cascade-delete a real counterpart transaction.
            if txn.source != "auto_transfer":
                await self._account_repo.adjust_balance(
                    txn.account_id, -_account_delta(txn.type, txn.amount)
                )
                if txn.type == "transfer" and txn.counterpart_account_id is not None:
                    await self._account_repo.adjust_balance(txn.counterpart_account_id, -txn.amount)
            logger.info("Transaction deleted: id=%d", transaction_id)
        return deleted

    async def get_transfer_match_candidates(self, transaction_id: int) -> List[TransferMatchCandidate]:
        """counterpart_account_id only records which account a transfer moves to/from --
        it is not proof a specific counterpart transaction was ever found (an import rule
        can set it as a guess with no reciprocal row). So a transaction is still eligible
        to search here as long as it isn't itself a generated mirror row; the repo query
        allows candidates whose own counterpart_account_id is unset or already guesses
        this transaction's account, so a genuinely mutually-linked pair naturally yields
        no candidates while a pair of independent rule-guesses can still be found.
        """
        transaction = await self._repo.get(transaction_id)
        if (
            transaction is None
            or transaction.source == "auto_transfer"
            or transaction.counterpart_transaction_id is not None
        ):
            return []
        candidates = await self._repo.get_transfer_match_candidates(transaction)
        return await self._to_transfer_match_candidates(candidates)

    async def search_link_candidates(
        self, transaction_id: int, query: str, limit: int = 20
    ) -> List[TransferMatchCandidate]:
        """Free-text search (by description/merchant/bank_description) across every
        other transaction, for manually picking a transfer counterpart that
        get_transfer_match_candidates' automated day/month + amount matching didn't
        surface -- e.g. a genuine transfer whose amounts diverge for a reason the
        matcher doesn't model (a fee taken on one leg, a partial refund folded in).
        Widens *what can be searched*, not what can be linked: link_transfer still
        re-validates the chosen pair before confirming.
        """
        query = query.strip()
        if not query:
            return []
        candidates = await self._repo.list(TransactionFilters(search=query, limit=limit))
        candidates = [c for c in candidates if c.id != transaction_id]
        return await self._to_transfer_match_candidates(candidates)

    async def _to_transfer_match_candidates(self, candidates: List[Transaction]) -> List[TransferMatchCandidate]:
        results = []
        for c in candidates:
            plan_original_amount = None
            if c.installment_plan_id is not None and c.amount == 0:
                plan = await self._plan_repo.get(c.installment_plan_id)
                if plan is not None and plan.original_amount is not None:
                    plan_original_amount = plan.original_amount
            results.append(
                TransferMatchCandidate(
                    id=c.id,
                    account_id=c.account_id,
                    date=c.date,
                    amount=c.amount,
                    currency=c.currency,
                    amount_eur=c.amount_eur,
                    type=c.type,
                    description=c.description,
                    bank_description=c.bank_description,
                    note=c.note,
                    merchant=c.merchant,
                    source=c.source,
                    plan_original_amount=plan_original_amount,
                )
            )
        return results

    async def auto_create_transfer_mirror(self, transaction_id: int) -> TransactionRead:
        """Explicit, user-confirmed counterpart to _maybe_create_mirror -- offered from
        Find Match when a transfer's counterpart_account_id already points at an
        auto_mirror_transfers account (typically an import rule guess) but no mirror
        exists yet, e.g. the row predates the rule or the flag was enabled afterwards.
        Reuses _maybe_create_mirror for the actual creation; the checks here exist only
        to turn its silent no-op into an explicit, actionable error for the caller.
        """
        transaction = await self._repo.get(transaction_id)
        if transaction is None:
            raise TransferMatchError("Transaction not found")
        if transaction.source == "auto_transfer":
            raise TransferMatchError("A generated mirror row cannot be linked")
        if transaction.counterpart_transaction_id is not None:
            raise TransferMatchError("Transaction is already linked")
        if transaction.type != "transfer" or transaction.counterpart_account_id is None:
            raise TransferMatchError("Transaction has no counterpart account set")
        counterpart_account = await self._account_repo.get(transaction.counterpart_account_id)
        if counterpart_account is None or not counterpart_account.auto_mirror_transfers:
            raise TransferMatchError("Counterpart account does not auto-mirror transfers")

        await self._maybe_create_mirror(transaction)
        updated = await self._repo.get(transaction_id)
        assert updated is not None
        logger.info("Transfer mirror auto-created from Find Match: id=%d", transaction_id)
        return TransactionRead.model_validate(updated)

    async def link_transfer(self, transaction_id: int, counterpart_transaction_id: int) -> TransactionRead:
        """Link two independently-imported transfer legs as each other's counterpart --
        see TransferLinkRequest. Always user-confirmed (the caller already chose this
        counterpart from get_transfer_match_candidates); re-validated here since either
        side could have changed since the candidate list was fetched. Either side may
        start out as an expense/income (a transfer miscategorized on import, with no
        tracked destination account) -- linking always sets both legs to type='transfer'
        so they're consistently excluded from spend/income totals afterward.
        """
        if transaction_id == counterpart_transaction_id:
            raise TransferMatchError("A transaction cannot be linked to itself")
        transaction = await self._repo.get(transaction_id)
        counterpart = await self._repo.get(counterpart_transaction_id)
        if transaction is None or counterpart is None:
            raise TransferMatchError("Transaction not found")
        if transaction.source == "auto_transfer" or counterpart.source == "auto_transfer":
            raise TransferMatchError("A generated mirror row cannot be linked")
        if transaction.counterpart_transaction_id is not None or counterpart.counterpart_transaction_id is not None:
            raise TransferMatchError("A transaction is already confirmed-linked")
        # transaction.counterpart_account_id may already be set from an import rule's
        # guessed destination account (see _apply_rules) rather than a confirmed
        # counterpart. Same for counterpart.counterpart_account_id: it's only a problem
        # if it points somewhere other than transaction's own account -- a guess already
        # pointing back at transaction's account is consistent with this being a genuine
        # (if previously unconfirmed) link.
        if counterpart.counterpart_account_id is not None and counterpart.counterpart_account_id != transaction.account_id:
            raise TransferMatchError("The counterpart transaction is already linked")
        if transaction.account_id == counterpart.account_id:
            raise TransferMatchError("Cannot link two legs on the same account")

        transaction_amount, transaction_ref_date = await self._effective_transfer_match(transaction)
        counterpart_amount, counterpart_ref_date = await self._effective_transfer_match(counterpart)
        transaction_is_plan_anchor = transaction.installment_plan_id is not None and transaction.amount == 0
        counterpart_is_plan_anchor = counterpart.installment_plan_id is not None and counterpart.amount == 0
        # A plan-anchored leg's reference date is the plan's opened_date -- an import
        # period boundary, not the actual purchase day -- so it's compared by month
        # rather than exact day (see _effective_transfer_match).
        if transaction_is_plan_anchor or counterpart_is_plan_anchor:
            dates_match = (
                transaction_ref_date.year == counterpart_ref_date.year
                and transaction_ref_date.month == counterpart_ref_date.month
            )
        else:
            dates_match = transaction_ref_date == counterpart_ref_date
        if not dates_match:
            raise TransferMatchError("Dates do not match")

        # Mirrors TransactionRepository.get_transfer_match_candidates' two match
        # strategies: same currency + exactly opposite amount (a plain transfer split
        # across separate imports), or opposite sign + different currency with
        # EUR-normalized magnitudes within 5% (a cross-currency transfer or exchange,
        # where legs are in different currencies with an FX-converted, not exactly
        # opposite, amount) -- falling back to identical bank_description when either
        # leg has no amount_eur to compare. Amount comparison uses each leg's
        # effective (plan-substituted) amount; the cross-currency strategy still
        # compares raw amount_eur, since InstallmentPlan carries none of its own.
        same_currency_opposite_amount = (
            transaction.currency == counterpart.currency and transaction_amount == -counterpart_amount
        )
        cross_currency_opposite_sign = (
            transaction.currency != counterpart.currency
            and (transaction.amount > 0) != (counterpart.amount > 0)
        )
        if transaction.amount_eur is not None and counterpart.amount_eur is not None:
            cross_currency_opposite_sign = cross_currency_opposite_sign and abs(
                abs(transaction.amount_eur) - abs(counterpart.amount_eur)
            ) <= abs(transaction.amount_eur) * Decimal("0.05")
        else:
            cross_currency_opposite_sign = (
                cross_currency_opposite_sign
                and transaction.bank_description is not None
                and transaction.bank_description == counterpart.bank_description
            )
        if not same_currency_opposite_amount and not cross_currency_opposite_sign:
            raise TransferMatchError("Amounts do not match")

        updated = await self.update(
            transaction.id,
            TransactionUpdate(
                type="transfer",
                counterpart_account_id=counterpart.account_id,
                counterpart_transaction_id=counterpart.id,
            ),
        )
        await self.update(
            counterpart.id,
            TransactionUpdate(
                type="transfer",
                counterpart_account_id=transaction.account_id,
                counterpart_transaction_id=transaction.id,
            ),
        )
        assert updated is not None
        logger.info("Transfer linked: id=%d counterpart_id=%d", transaction.id, counterpart.id)
        return updated

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

    async def transaction_coverage(
        self,
        account_id: int | None,
        group_by: str,
        from_date: date | None,
        to_date: date | None,
    ) -> TransactionCoverageResponse:
        """Transaction counts per period, defaulting the range to [this account's (or
        overall) earliest transaction, today] -- the finance data-coverage page uses
        this to show which months/days actually have imported data.
        """
        resolved_to = to_date or date.today()
        resolved_from = from_date
        if resolved_from is None:
            resolved_from = await self._repo.get_earliest_transaction_date(account_id)
            resolved_from = resolved_from or resolved_to
        rows = await self._repo.get_transaction_counts(
            from_date=resolved_from, to_date=resolved_to, group_by=group_by, account_id=account_id
        )
        items = [
            TransactionCountItem(
                period=period,
                count=count,
                unmatched_transfer_count=unmatched,
                unmatched_transfer_accounts=[
                    UnmatchedTransferAccount(id=a["id"], name=a["name"]) for a in missing_accounts
                ],
            )
            for period, count, unmatched, missing_accounts in rows
        ]
        return TransactionCoverageResponse(
            items=items, from_date=resolved_from, to_date=resolved_to, group_by=group_by, account_id=account_id
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
