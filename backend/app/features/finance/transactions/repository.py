from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from sqlalchemy import and_, case, func, or_, select, update
from sqlalchemy.orm import aliased
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.finance.installment_plans.tables import InstallmentPlan
from app.features.finance.transactions.tables import Transaction
from app.features.finance.transactions.schemas import (
    GLOBAL_CURRENCY,
    TransactionBulkMoveRequest,
    TransactionCreate,
    TransactionUpdate,
    TransactionFilters,
)

_PLACEHOLDER_NOTE_PREFIX = "Placeholder"


def _amount_column(currency: str):
    return Transaction.amount_eur if currency == GLOBAL_CURRENCY else Transaction.amount


def _confirmed_installment_transfer_condition():
    """True when a row belongs to an installment plan whose zeroed anchor row (see
    create_placeholder_for_plan / the superseded-original path in
    ImportService._apply_one_installment_plan_action) has itself been confirmed as a
    transfer (counterpart_transaction_id set via TransactionService.link_transfer).
    A confirmed anchor means the whole purchase was a transfer to/from another
    Alfred-tracked account, not real spend or an unresolved transfer -- so every
    installment capture in the plan shares that status too, even though each one
    is its own real, non-zero row with no counterpart of its own.
    """
    Anchor = aliased(Transaction)
    installment_plan_transfer_confirmed = (
        select(Anchor.id)
        .where(
            Anchor.installment_plan_id == Transaction.installment_plan_id,
            Anchor.amount == 0,
            Anchor.counterpart_transaction_id.isnot(None),
        )
        .correlate(Transaction)
        .exists()
    )
    return and_(
        Transaction.installment_plan_id.isnot(None),
        installment_plan_transfer_confirmed,
    )


def _spend_condition(transaction_type: str):
    """A transfer with no *confirmed* counterpart transaction is money that left an
    Alfred-tracked account with no verified evidence it landed in another one (e.g.
    sent to an external wallet, converted to a currency Alfred doesn't track, or only
    a rule/user guess at the destination account that was never confirmed) -- it's
    effectively spent, even though the bank/import labeled it a transfer. A transfer
    only stays excluded from spend once counterpart_transaction_id is set (see
    TransactionService.link_transfer) -- counterpart_account_id alone is not proof,
    since it can be an unconfirmed guess. Only applies when reporting "expense"; other
    types (income) match the column exactly.

    Only a negative amount can count as spend -- a positive-amount unmatched transfer
    (e.g. a Revolut top-up funded from an external card) is money coming in, never an
    outflow, regardless of counterpart state.

    An auto-generated mirror row (Transaction.source == "auto_transfer", see
    Account.auto_mirror_transfers) always has its own counterpart_transaction_id set
    (pointing back at the source leg that spawned it) -- excluded from spend by the
    same counterpart_transaction_id check, no separate condition needed.

    A plan's monthly installment captures (type="expense", installment_plan_id set)
    are excluded the same way once their plan's anchor is a confirmed transfer -- see
    _confirmed_installment_transfer_condition.
    """
    if transaction_type == "expense":
        return and_(
            or_(
                Transaction.type == "expense",
                and_(
                    Transaction.type == "transfer",
                    Transaction.counterpart_transaction_id.is_(None),
                    Transaction.amount < 0,
                ),
            ),
            ~_confirmed_installment_transfer_condition(),
        )
    return Transaction.type == transaction_type


_NAME_COLUMN = func.coalesce(Transaction.description, Transaction.merchant, Transaction.bank_description)

_SORT_COLUMNS = {
    "date": Transaction.date,
    "amount": Transaction.amount,
    "name": _NAME_COLUMN,
}


def _build_order_by(sort: str):
    column_key, _, direction = sort.rpartition("_")
    column = _SORT_COLUMNS.get(column_key, Transaction.date)
    return column.asc() if direction == "asc" else column.desc()


def _filter_conditions(filters: Any, cycle_start_day: int = 1) -> list:
    """Shared WHERE-clause building for anything shaped like TransactionFilters
    (duck-typed: also used by TransactionBulkMoveRequest, which carries the same
    optional type/category/merchant/date/currency fields plus a required account_id).
    """
    conditions = []
    if filters.type is not None:
        conditions.append(_spend_condition(filters.type))
    if getattr(filters, "uncategorized", False):
        conditions.append(Transaction.category_id.is_(None))
    elif filters.category_id is not None:
        conditions.append(Transaction.category_id == filters.category_id)
    if getattr(filters, "account_id", None) is not None:
        conditions.append(Transaction.account_id == filters.account_id)
    if getattr(filters, "installment_plan_id", None) is not None:
        conditions.append(Transaction.installment_plan_id == filters.installment_plan_id)
    if getattr(filters, "unconfirmed_transfer", False):
        conditions.append(
            and_(
                Transaction.type == "transfer",
                Transaction.counterpart_transaction_id.is_(None),
                ~_confirmed_installment_transfer_condition(),
            )
        )
    if filters.merchant is not None:
        conditions.append(Transaction.merchant.ilike(f"%{filters.merchant}%"))
    if getattr(filters, "search", None):
        conditions.append(_NAME_COLUMN.ilike(f"%{filters.search}%"))
    if filters.currency is not None and filters.currency != GLOBAL_CURRENCY:
        conditions.append(Transaction.currency == filters.currency)
    if filters.from_date is not None:
        conditions.append(Transaction.date >= filters.from_date)
    if filters.to_date is not None:
        conditions.append(Transaction.date <= filters.to_date)
    elif filters.period is not None:
        from app.features.finance.transactions.schemas import resolve_period
        from_dt, to_dt = resolve_period(filters.period, filters.from_date, filters.to_date, cycle_start_day)
        conditions.append(Transaction.date >= from_dt)
        conditions.append(Transaction.date <= to_dt)
    return conditions


class TransactionRepository:

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, transaction_id: int) -> Transaction | None:
        result = await self._session.execute(
            select(Transaction).where(Transaction.id == transaction_id)
        )
        return result.scalars().first()

    async def get_related(self, transaction: Transaction) -> Transaction | None:
        """The confirmed transfer counterpart, if any -- two cheap PK lookups rather
        than a join, since this is an on-demand single-row fetch, not a list-rendering
        hot path. Returns None both when there's no counterpart and when the FK is
        dangling (e.g. the counterpart was deleted), so callers don't need to
        special-case either.
        """
        if transaction.counterpart_transaction_id is None:
            return None
        return await self.get(transaction.counterpart_transaction_id)

    async def get_transfer_match_candidates(self, transaction: Transaction) -> list[Transaction]:
        """Other accounts' unmatched legs that could be this transaction's missing
        counterpart, same day only, not a mirror row. A candidate's counterpart_account_id
        may be set from an import rule's guessed destination account rather than a
        confirmed link (see TransactionService.link_transfer) -- that's not disqualifying
        as long as the guess already points back at this transaction's own account, since
        that's consistent with this transaction being the missing counterpart. A guess
        pointing at some other account rules the candidate out, narrowing results instead
        of blocking the search entirely. Used to reconcile a transfer whose two legs were
        imported from separate statement files (or, for a same-file currency exchange,
        never paired at import time), so no shared transfer_pair_key was ever set. Not
        restricted to type=transfer -- one or both legs may have been miscategorized as
        expense/income on import, which is exactly the case this is meant to catch.
        Candidates are only ever suggested, never auto-linked. Two independent match
        strategies, either sufficient:
        - same currency + exactly opposite amount -- a same-currency transfer split
          across separate imports (e.g. an external card charge and the Revolut top-up
          it funds).
        - opposite sign, different currency, EUR-normalized magnitudes within 5% of
          each other -- a cross-currency transfer (e.g. a Wise EUR debit funding a
          Banco Inter BRL credit) or a same-bank currency exchange. Deliberately does
          not require bank_description to match: two different institutions describe
          the same transfer in unrelated, independently-generated text (a counterparty
          name on one side, bank jargon on the other), so requiring equality there
          made this strategy unreachable for the exact cross-currency transfers it's
          meant to catch. The 5% tolerance is generous enough to absorb a bank's
          exchange spread while still ruling out an unrelated same-day transfer.
          When amount_eur isn't available on one of the legs (no FX rate on record),
          falls back to requiring identical bank_description, since without an
          EUR-normalized amount to compare there'd otherwise be nothing to narrow the
          match down beyond "opposite sign, different currency, same day".

        A candidate anchoring an installment plan (its own amount zeroed to 0.00 --
        see create_placeholder_for_plan, and the superseded-original path in
        ImportService._apply_one_installment_plan_action) can never satisfy either
        strategy on its raw amount/date: the real value only exists on
        InstallmentPlan.original_amount, and its date is the plan's opened_date (an
        import period boundary, not the actual purchase day -- e.g. a Revolut top-up
        paid via an ActivoBank card and then split into installments never has a
        -100 row to match against, only 0.00). For such a candidate, the
        same-currency amount check, the cross-currency amount_eur check, and the day
        check all substitute the plan's original_amount/opened_date (matched by
        month, not exact day) for the candidate's own zeroed amount/date --
        original_amount doubles as the EUR-normalized amount since a plan anchor is
        always created in EUR (see create_placeholder_for_plan). `transaction` itself
        may just as well be a plan anchor (the user opened the placeholder row and
        asked to find its match) -- substituted the same way before building the
        query.
        """
        transaction_amount = transaction.amount
        transaction_amount_eur = transaction.amount_eur
        transaction_date = transaction.date
        transaction_is_plan_anchor = False
        if transaction.installment_plan_id is not None and transaction.amount == 0:
            plan_result = await self._session.execute(
                select(InstallmentPlan).where(InstallmentPlan.id == transaction.installment_plan_id)
            )
            transaction_plan = plan_result.scalars().first()
            if transaction_plan is not None and transaction_plan.original_amount is not None:
                transaction_amount = transaction_plan.original_amount
                transaction_amount_eur = transaction_plan.original_amount
                transaction_date = datetime.combine(transaction_plan.opened_date, datetime.min.time())
                transaction_is_plan_anchor = True

        plan_anchor = and_(
            Transaction.installment_plan_id.isnot(None),
            Transaction.amount == 0,
            InstallmentPlan.original_amount.isnot(None),
        )
        effective_amount = case((plan_anchor, InstallmentPlan.original_amount), else_=Transaction.amount)
        effective_amount_eur = case((plan_anchor, InstallmentPlan.original_amount), else_=Transaction.amount_eur)
        same_currency_opposite_amount = and_(
            Transaction.currency == transaction.currency,
            effective_amount == -transaction_amount,
        )
        cross_currency_opposite_sign = and_(
            Transaction.currency != transaction.currency,
            Transaction.amount < 0 if transaction_amount > 0 else Transaction.amount > 0,
        )
        if transaction_amount_eur is not None:
            cross_currency_opposite_sign = and_(
                cross_currency_opposite_sign,
                effective_amount_eur.isnot(None),
                func.abs(func.abs(effective_amount_eur) - abs(transaction_amount_eur))
                <= abs(transaction_amount_eur) * Decimal("0.05"),
            )
        else:
            cross_currency_opposite_sign = and_(
                cross_currency_opposite_sign,
                Transaction.bank_description.isnot(None),
                Transaction.bank_description == transaction.bank_description,
            )
        same_month_as_plan_open = and_(
            plan_anchor,
            func.extract("year", InstallmentPlan.opened_date) == transaction_date.year,
            func.extract("month", InstallmentPlan.opened_date) == transaction_date.month,
        )
        if transaction_is_plan_anchor:
            date_matches = or_(
                and_(
                    func.extract("year", Transaction.date) == transaction_date.year,
                    func.extract("month", Transaction.date) == transaction_date.month,
                ),
                same_month_as_plan_open,
            )
        else:
            date_matches = or_(func.date(Transaction.date) == func.date(transaction_date), same_month_as_plan_open)
        result = await self._session.execute(
            select(Transaction)
            .outerjoin(InstallmentPlan, Transaction.installment_plan_id == InstallmentPlan.id)
            .where(
                Transaction.id != transaction.id,
                Transaction.account_id != transaction.account_id,
                or_(
                    Transaction.counterpart_account_id.is_(None),
                    Transaction.counterpart_account_id == transaction.account_id,
                ),
                Transaction.counterpart_transaction_id.is_(None),
                date_matches,
                or_(same_currency_opposite_amount, cross_currency_opposite_sign),
            )
        )
        return list(result.scalars().all())

    async def set_counterpart_transaction(self, transaction_id: int, counterpart_transaction_id: int | None) -> None:
        """Raw column update, no ORM object refresh -- used to confirm a link (or clear
        one) without re-triggering balance/mirror side effects, which the caller has
        already applied (or never needed) separately.
        """
        await self._session.execute(
            update(Transaction)
            .where(Transaction.id == transaction_id)
            .values(counterpart_transaction_id=counterpart_transaction_id)
        )
        await self._session.commit()

    async def list(self, filters: TransactionFilters, cycle_start_day: int = 1) -> list[Transaction]:
        query = select(Transaction).order_by(_build_order_by(filters.sort))
        for condition in _filter_conditions(filters, cycle_start_day):
            query = query.where(condition)
        query = query.offset(filters.offset).limit(filters.limit)
        result = await self._session.execute(query)
        return list(result.scalars().all())

    async def get_filtered_sum(self, filters: TransactionFilters, cycle_start_day: int = 1) -> tuple[Decimal, int]:
        """Net signed total across every transaction matching filters.type (and the
        rest of the filter set), regardless of pagination -- expense debits (stored
        as an unsigned magnitude); income and transfer both already store their real
        signed delta directly, so they're summed as-is, matching the sign convention
        used everywhere else (_account_delta, get_ledger_events). Used for the "total
        across all pages of this filtered result" summary on the transactions page.
        """
        # No currency filter means the list itself spans every currency, so the sum
        # must be normalized (amount_eur) rather than adding raw native amounts
        # across currencies -- same fallback GLOBAL_CURRENCY uses everywhere else.
        amount_column = _amount_column(filters.currency or GLOBAL_CURRENCY)
        delta = case((Transaction.type == "expense", -amount_column), else_=amount_column)
        query = select(func.coalesce(func.sum(delta), 0), func.count(Transaction.id))
        for condition in _filter_conditions(filters, cycle_start_day):
            query = query.where(condition)
        result = await self._session.execute(query)
        total, count = result.one()
        return Decimal(str(total)), count

    async def bulk_reassign_account(self, request: TransactionBulkMoveRequest, cycle_start_day: int = 1) -> int:
        """Move every transaction matching request's account_id + optional filters to
        target_account_id. Clears deduplication_hash on moved rows: the stored hash was
        computed against the old account_id (and the source statement's balance, which
        isn't persisted), so it can no longer be trusted to detect a future re-import.
        """
        stmt = update(Transaction).values(account_id=request.target_account_id, deduplication_hash=None)
        for condition in _filter_conditions(request, cycle_start_day):
            stmt = stmt.where(condition)
        result = await self._session.execute(stmt)
        await self._session.commit()
        return result.rowcount

    async def create(self, data: TransactionCreate, amount_eur: Decimal | None = None) -> Transaction:
        transaction = Transaction(**data.model_dump(), amount_eur=amount_eur)
        self._session.add(transaction)
        await self._session.commit()
        await self._session.refresh(transaction)
        return transaction

    async def update(
        self,
        transaction_id: int,
        data: TransactionUpdate,
        amount_eur: Decimal | None = None,
        recompute_amount_eur: bool = False,
    ) -> Transaction | None:
        transaction = await self.get(transaction_id)
        if transaction is None:
            return None
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(transaction, field, value)
        if recompute_amount_eur:
            transaction.amount_eur = amount_eur
        await self._session.commit()
        await self._session.refresh(transaction)
        return transaction

    async def add(self, data: TransactionCreate, amount_eur: Decimal | None = None) -> Transaction:
        """Add transaction to session without committing. Caller is responsible for commit."""
        transaction = Transaction(**data.model_dump(), amount_eur=amount_eur)
        self._session.add(transaction)
        return transaction

    async def count_by_account(self, account_id: int) -> int:
        result = await self._session.execute(
            select(func.count(Transaction.id)).where(Transaction.account_id == account_id)
        )
        return result.scalar_one()

    async def exists_by_dedup_hash(self, dedup_hash: str) -> bool:
        result = await self._session.execute(
            select(Transaction.id).where(Transaction.deduplication_hash == dedup_hash)
        )
        return result.scalar() is not None

    async def get_by_dedup_hash(self, dedup_hash: str) -> Transaction | None:
        result = await self._session.execute(
            select(Transaction).where(Transaction.deduplication_hash == dedup_hash)
        )
        return result.scalars().first()

    async def get_existing_dedup_hashes(self, dedup_hashes: list[str]) -> set[str]:
        if not dedup_hashes:
            return set()
        result = await self._session.execute(
            select(Transaction.deduplication_hash).where(
                Transaction.deduplication_hash.in_(dedup_hashes)
            )
        )
        return {row for row in result.scalars().all()}

    async def get_existing_keys(
        self, account_id: int, dates: set[date]
    ) -> set[tuple[date, str, Decimal]]:
        """Every (date, bank_description, amount) already stored for this account on
        the given dates -- used to flag statement-format imports with no reported
        balance (so no reliable per-row disambiguator) as duplicates by content, since
        a synthetic per-file occurrence counter can't stay reproducible across separate
        import runs that don't repeat rows in the same relative order.
        """
        if not dates:
            return set()
        result = await self._session.execute(
            select(Transaction.date, Transaction.bank_description, Transaction.amount).where(
                Transaction.account_id == account_id,
                func.date(Transaction.date).in_(dates),
            )
        )
        return {(row[0].date(), row[1], row[2]) for row in result.all()}

    async def find_unmatched_transaction(
        self, account_id: int, bank_description: str, amount: Decimal
    ) -> Transaction | None:
        """A pre-existing, not-yet-linked transaction matching (account, description,
        amount) -- used right when a plan is first created (see
        InstallmentPlanService.ensure_plan_for_ref) to check whether its original
        lump-sum purchase was already imported earlier (e.g. by a prior CSV import).
        No date constraint, for the same reason as find_open_plan_match below."""
        result = await self._session.execute(
            select(Transaction).where(
                Transaction.account_id == account_id,
                Transaction.bank_description == bank_description,
                Transaction.amount == amount,
                Transaction.amount != 0,
                Transaction.installment_plan_id.is_(None),
            )
        )
        return result.scalars().first()

    async def find_open_plan_match(
        self, account_id: int, bank_description: str, amount: Decimal
    ) -> InstallmentPlan | None:
        """An open installment plan whose original lump-sum purchase this row could
        be, matched by (account, description, original_amount) -- no date constraint,
        since a plan created retroactively (first seen mid-life, not at its opening
        month) has no reliable original purchase date to constrain by. Skips plans
        that already have their real original matched (a non-placeholder zeroed
        transaction already linked); a plan with only a placeholder, or nothing yet,
        is still eligible. Runs for every newly-parsed row of every import (not just
        PDF-sourced ones), so a CSV import landing before OR after the PDF that
        created the plan both resolve the same way.
        """
        already_matched = (
            select(Transaction.id)
            .where(
                Transaction.installment_plan_id == InstallmentPlan.id,
                Transaction.amount == 0,
                or_(
                    Transaction.note.is_(None),
                    ~Transaction.note.like(f"{_PLACEHOLDER_NOTE_PREFIX}%"),
                ),
            )
            .correlate(InstallmentPlan)
            .exists()
        )
        result = await self._session.execute(
            select(InstallmentPlan).where(
                InstallmentPlan.account_id == account_id,
                InstallmentPlan.status == "open",
                InstallmentPlan.original_amount.isnot(None),
                InstallmentPlan.original_amount == amount,
                InstallmentPlan.description == bank_description,
                ~already_matched,
            )
        )
        return result.scalars().first()

    async def create_placeholder_for_plan(
        self, account_id: int, plan_id: int, description: str, txn_date: date, note: str
    ) -> Transaction:
        """A zeroed anchor transaction for a plan whose original purchase hasn't been
        matched to any imported transaction yet, so the plan always has something to
        show on its transaction list. Deleted automatically once a real match is
        found (see delete_placeholder_for_plan)."""
        placeholder = Transaction(
            account_id=account_id,
            date=datetime.combine(txn_date, datetime.min.time()),
            amount=Decimal("0.00"),
            currency="EUR",
            type="expense",
            description=description,
            note=note,
            installment_plan_id=plan_id,
        )
        self._session.add(placeholder)
        await self._session.commit()
        await self._session.refresh(placeholder)
        return placeholder

    async def delete_placeholder_for_plan(self, plan_id: int) -> None:
        result = await self._session.execute(
            select(Transaction).where(
                Transaction.installment_plan_id == plan_id,
                Transaction.amount == 0,
                Transaction.note.like(f"{_PLACEHOLDER_NOTE_PREFIX}%"),
            )
        )
        placeholder = result.scalars().first()
        if placeholder is not None:
            await self._session.delete(placeholder)
            await self._session.commit()

    async def unlink_installment_plan(self, transaction_id: int) -> Transaction | None:
        """Clear a mismatched link -- the transaction itself is kept, same treatment
        as deleting a whole plan (InstallmentPlanService.delete), just for one row."""
        transaction = await self.get(transaction_id)
        if transaction is None:
            return None
        transaction.installment_plan_id = None
        await self._session.commit()
        await self._session.refresh(transaction)
        return transaction

    async def get_mirror(self, source_transaction_id: int) -> Transaction | None:
        result = await self._session.execute(
            select(Transaction).where(
                Transaction.counterpart_transaction_id == source_transaction_id,
                Transaction.source == "auto_transfer",
            )
        )
        return result.scalars().first()

    async def get_by_ids(self, transaction_ids: list[int]) -> list[Transaction]:
        if not transaction_ids:
            return []
        result = await self._session.execute(
            select(Transaction).where(Transaction.id.in_(transaction_ids))
        )
        return list(result.scalars().all())

    async def get_ids_by_import_batch(self, import_batch_id: int) -> list[int]:
        result = await self._session.execute(
            select(Transaction.id).where(Transaction.import_batch_id == import_batch_id)
        )
        return list(result.scalars().all())

    async def delete_by_ids(self, transaction_ids: list[int]) -> int:
        if not transaction_ids:
            return 0
        result = await self._session.execute(
            select(Transaction).where(Transaction.id.in_(transaction_ids))
        )
        transactions = list(result.scalars().all())
        for transaction in transactions:
            await self._session.delete(transaction)
        await self._session.commit()
        return len(transactions)

    async def delete(self, transaction_id: int) -> bool:
        transaction = await self.get(transaction_id)
        if transaction is None:
            return False
        await self._session.delete(transaction)
        await self._session.commit()
        return True

    async def get_spending_total(
        self,
        from_date: date,
        to_date: date,
        category_id: int | None = None,
        account_id: int | None = None,
        merchant: str | None = None,
        currency: str = "EUR",
        transaction_type: str = "expense",
    ) -> tuple[Decimal, int]:
        amount_column = _amount_column(currency)
        query = select(
            func.coalesce(func.sum(amount_column), 0),
            func.count(Transaction.id),
        ).where(
            _spend_condition(transaction_type),
            Transaction.date >= from_date,
            Transaction.date <= to_date,
        )
        if currency != GLOBAL_CURRENCY:
            query = query.where(Transaction.currency == currency)
        if category_id is not None:
            query = query.where(Transaction.category_id == category_id)
        if account_id is not None:
            query = query.where(Transaction.account_id == account_id)
        if merchant is not None:
            query = query.where(Transaction.merchant.ilike(f"%{merchant}%"))
        result = await self._session.execute(query)
        total, count = result.one()
        return Decimal(str(total)), count

    async def get_top_expenses(
        self,
        from_date: date,
        to_date: date,
        top_n: int,
        category_id: int | None = None,
        currency: str = "EUR",
    ) -> list[Transaction]:
        query = (
            select(Transaction)
            .where(
                _spend_condition("expense"),
                Transaction.date >= from_date,
                Transaction.date <= to_date,
            )
            .order_by(_amount_column(currency).desc())
            .limit(top_n)
        )
        if currency != GLOBAL_CURRENCY:
            query = query.where(Transaction.currency == currency)
        if category_id is not None:
            query = query.where(Transaction.category_id == category_id)
        result = await self._session.execute(query)
        return list(result.scalars().all())

    async def get_spending_by_category(
        self,
        from_date: date,
        to_date: date,
        account_id: int | None = None,
        currency: str = "EUR",
    ) -> list[tuple[int | None, str | None, Decimal, int]]:
        from app.features.finance.categories.tables import Category

        amount_column = _amount_column(currency)
        query = (
            select(
                Transaction.category_id,
                Category.name,
                func.coalesce(func.sum(amount_column), 0),
                func.count(Transaction.id),
            )
            .outerjoin(Category, Transaction.category_id == Category.id)
            .where(
                _spend_condition("expense"),
                Transaction.date >= from_date,
                Transaction.date <= to_date,
            )
            .group_by(Transaction.category_id, Category.name)
            .order_by(func.sum(amount_column).desc())
        )
        if currency != GLOBAL_CURRENCY:
            query = query.where(Transaction.currency == currency)
        if account_id is not None:
            query = query.where(Transaction.account_id == account_id)
        result = await self._session.execute(query)
        return [
            (row[0], row[1], Decimal(str(row[2])), row[3])
            for row in result.all()
        ]

    async def get_spending_over_time(
        self,
        from_date: date,
        to_date: date,
        group_by: str,
        account_id: int | None = None,
        currency: str = "EUR",
        transaction_type: str = "expense",
    ) -> list[tuple[str, Decimal]]:
        """Aggregate expense (or income) totals bucketed by day or month, entirely
        in SQL -- unlike fetching raw transactions, this scales to any date range
        without a row cap silently dropping older buckets.
        """
        amount_column = _amount_column(currency)
        bucket = func.date_trunc(group_by, Transaction.date)
        query = (
            select(bucket, func.coalesce(func.sum(amount_column), 0))
            .where(
                _spend_condition(transaction_type),
                Transaction.date >= from_date,
                Transaction.date <= to_date,
            )
            .group_by(bucket)
            .order_by(bucket)
        )
        if currency != GLOBAL_CURRENCY:
            query = query.where(Transaction.currency == currency)
        if account_id is not None:
            query = query.where(Transaction.account_id == account_id)
        result = await self._session.execute(query)
        key_format = "%Y-%m" if group_by == "month" else "%Y-%m-%d"
        return [(row[0].strftime(key_format), Decimal(str(row[1]))) for row in result.all()]

    async def get_earliest_transaction_date(self, account_id: int | None = None) -> date | None:
        query = select(func.min(Transaction.date))
        if account_id is not None:
            query = query.where(Transaction.account_id == account_id)
        result = await self._session.execute(query)
        value = result.scalar()
        return value.date() if value is not None else None

    async def get_transaction_counts(
        self,
        from_date: date,
        to_date: date,
        group_by: str,
        account_id: int | None = None,
    ) -> list[tuple[str, int, int, list[dict]]]:
        """Transaction counts bucketed by day or month, regardless of type/currency --
        unlike get_spending_over_time, used to show which periods have any imported
        data at all (the finance data-coverage page), not to total spend.

        Also reports, per bucket, how many of those transactions are unresolved
        transfers (type='transfer' with no confirmed counterpart_transaction_id --
        see TransactionService.link_transfer). A transfer left dangling like this is a
        signal the *other* leg's account statement may not have been imported yet for
        that period, even though this account's own coverage looks complete -- the
        4th tuple element names which account(s), via counterpart_account_id (an
        unconfirmed guess, but the best hint available), so the coverage page can
        point at the specific statement that's still missing instead of just flagging
        "something's unresolved".
        """
        from app.features.finance.accounts.tables import Account

        counterpart = aliased(Account)
        bucket = func.date_trunc(group_by, Transaction.date)
        is_unmatched = and_(
            Transaction.type == "transfer", Transaction.counterpart_transaction_id.is_(None)
        )
        unmatched_transfer = case((is_unmatched, 1), else_=0)
        missing_accounts = func.jsonb_agg(
            func.distinct(func.jsonb_build_object("id", counterpart.id, "name", counterpart.name))
        ).filter(and_(is_unmatched, counterpart.id.is_not(None)))
        query = (
            select(
                bucket,
                func.count(Transaction.id),
                func.coalesce(func.sum(unmatched_transfer), 0),
                missing_accounts,
            )
            .outerjoin(counterpart, Transaction.counterpart_account_id == counterpart.id)
            .where(Transaction.date >= from_date, Transaction.date <= to_date)
            .group_by(bucket)
            .order_by(bucket)
        )
        if account_id is not None:
            query = query.where(Transaction.account_id == account_id)
        result = await self._session.execute(query)
        key_format = "%Y-%m" if group_by == "month" else "%Y-%m-%d"
        return [
            (row[0].strftime(key_format), row[1], int(row[2]), row[3] or [])
            for row in result.all()
        ]

    async def get_spending_by_account(
        self,
        from_date: date,
        to_date: date,
        category_id: int | None = None,
        currency: str = "EUR",
    ) -> list[tuple[int | None, str | None, Decimal, int]]:
        from app.features.finance.accounts.tables import Account

        amount_column = _amount_column(currency)
        query = (
            select(
                Transaction.account_id,
                Account.name,
                func.coalesce(func.sum(amount_column), 0),
                func.count(Transaction.id),
            )
            .outerjoin(Account, Transaction.account_id == Account.id)
            .where(
                _spend_condition("expense"),
                Transaction.date >= from_date,
                Transaction.date <= to_date,
            )
            .group_by(Transaction.account_id, Account.name)
            .order_by(func.sum(amount_column).desc())
        )
        if currency != GLOBAL_CURRENCY:
            query = query.where(Transaction.currency == currency)
        if category_id is not None:
            query = query.where(Transaction.category_id == category_id)
        result = await self._session.execute(query)
        return [
            (row[0], row[1], Decimal(str(row[2])), row[3])
            for row in result.all()
        ]

    async def get_ledger_events(
        self, to_date: date, currency: str = "EUR"
    ) -> list[tuple[int, date, Decimal]]:
        """Every balance-affecting event across all tracked accounts, as
        (account_id, date, signed delta) triples -- the raw material for
        reconstructing a running per-account (and total) balance over time.

        Every transaction only ever moves its own account's balance by its own
        amount -- expense debits (stored as an unsigned magnitude); income and
        transfer both already store their real signed delta directly, so they're
        used as-is (see TransactionService._account_delta). counterpart_account_id
        is pure linking metadata, never a second account's balance mutation here
        either: the counterpart's own balance comes from its own transaction row
        (an independently-imported/confirmed leg, or a mirror), so crediting it a
        second time from this row would double-count it -- mirrors
        Account.balance's own incremental maintenance so the two never disagree.
        """
        amount_column = _amount_column(currency)
        delta = case((Transaction.type == "expense", -amount_column), else_=amount_column)

        query = select(Transaction.account_id, Transaction.date, delta).where(
            Transaction.date <= to_date
        )
        if currency != GLOBAL_CURRENCY:
            query = query.where(Transaction.currency == currency)

        result = await self._session.execute(query)
        return [
            (row[0], row[1].date() if hasattr(row[1], "date") else row[1], Decimal(str(row[2])))
            for row in result.all()
        ]

    async def get_category_spent(
        self,
        category_id: int,
        from_date: date,
        to_date: date,
        currency: str = "EUR",
    ) -> Decimal:
        query = select(
            func.coalesce(func.sum(_amount_column(currency)), 0)
        ).where(
            _spend_condition("expense"),
            Transaction.category_id == category_id,
            Transaction.date >= from_date,
            Transaction.date <= to_date,
        )
        if currency != GLOBAL_CURRENCY:
            query = query.where(Transaction.currency == currency)
        result = await self._session.execute(query)
        return Decimal(str(result.scalar()))

    async def list_missing_amount_eur(self, limit: int = 1000) -> list[Transaction]:
        result = await self._session.execute(
            select(Transaction)
            .where(Transaction.amount_eur.is_(None))
            .order_by(Transaction.id)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def set_amount_eur(self, transaction_id: int, amount_eur: Decimal) -> None:
        await self._session.execute(
            update(Transaction).where(Transaction.id == transaction_id).values(amount_eur=amount_eur)
        )
        await self._session.commit()

    async def count_missing_amount_eur(self) -> int:
        result = await self._session.execute(
            select(func.count(Transaction.id)).where(Transaction.amount_eur.is_(None))
        )
        return result.scalar_one()
