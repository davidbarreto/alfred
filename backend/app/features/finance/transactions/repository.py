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


def _spend_condition(transaction_type: str):
    """A transfer with no tracked counterpart account is money that left an
    Alfred-tracked account and never landed in another one (e.g. sent to an external
    wallet, or converted to a currency Alfred doesn't track) -- it's effectively spent,
    even though the bank/import labeled it a transfer. A transfer that does have a
    counterpart_account_id is a genuine internal move between two tracked accounts and
    stays excluded from spend. Only applies when reporting "expense"; other types
    (income) match the column exactly.

    Only a negative amount can count as spend -- a positive-amount unmatched transfer
    (e.g. a Revolut top-up funded from an external card) is money coming in, never an
    outflow, regardless of counterpart state.

    An auto-generated mirror row (generated_from_transaction_id set, see
    Account.auto_mirror_transfers) has no counterpart_account_id of its own but is
    still a genuine internal move -- excluded from spend the same way.
    """
    if transaction_type == "expense":
        return or_(
            Transaction.type == "expense",
            and_(
                Transaction.type == "transfer",
                Transaction.counterpart_account_id.is_(None),
                Transaction.generated_from_transaction_id.is_(None),
                Transaction.amount < 0,
            ),
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
    if filters.merchant is not None:
        conditions.append(Transaction.merchant.ilike(f"%{filters.merchant}%"))
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

    async def get_transfer_match_candidates(self, transaction: Transaction) -> list[Transaction]:
        """Other accounts' unmatched legs that could be this transaction's missing
        counterpart, same day only, not already linked or a mirror row. Used to
        reconcile a transfer whose two legs were imported from separate statement files
        (or, for a same-file currency exchange, never paired at import time), so no
        shared transfer_pair_key was ever set. Not restricted to type=transfer -- one or
        both legs may have been miscategorized as expense/income on import, which is
        exactly the case this is meant to catch. Candidates are only ever suggested,
        never auto-linked. Two independent match strategies, either sufficient:
        - same currency + exactly opposite amount -- a same-currency transfer split
          across separate imports (e.g. an external card charge and the Revolut top-up
          it funds).
        - identical bank_description + opposite sign, different currency -- a currency
          exchange, where the two legs are in different currencies with an FX-converted
          (not exactly opposite) amount, but both sides of one Revolut "Exchange" row
          share the exact same bank text (e.g. "Exchanged to PLN"). Restricted to
          different currencies so this strategy only ever fires for a genuine exchange,
          never overlapping with the same-currency strategy above. The same generic
          bank text can also appear on multiple same-day exchanges, so when both legs
          have a EUR-normalized amount, their magnitudes must additionally land within
          5% of each other -- generous enough to absorb a bank's exchange spread while
          still ruling out an unrelated exchange that happens to share the same text.
        """
        same_currency_opposite_amount = and_(
            Transaction.currency == transaction.currency,
            Transaction.amount == -transaction.amount,
        )
        same_description_opposite_sign = and_(
            Transaction.currency != transaction.currency,
            Transaction.bank_description.isnot(None),
            Transaction.bank_description == transaction.bank_description,
            Transaction.amount < 0 if transaction.amount > 0 else Transaction.amount > 0,
        )
        if transaction.amount_eur is not None:
            same_description_opposite_sign = and_(
                same_description_opposite_sign,
                Transaction.amount_eur.isnot(None),
                func.abs(func.abs(Transaction.amount_eur) - abs(transaction.amount_eur))
                <= abs(transaction.amount_eur) * Decimal("0.05"),
            )
        result = await self._session.execute(
            select(Transaction).where(
                Transaction.id != transaction.id,
                Transaction.account_id != transaction.account_id,
                Transaction.counterpart_account_id.is_(None),
                Transaction.generated_from_transaction_id.is_(None),
                func.date(Transaction.date) == func.date(transaction.date),
                or_(same_currency_opposite_amount, same_description_opposite_sign),
            )
        )
        return list(result.scalars().all())

    async def list(self, filters: TransactionFilters, cycle_start_day: int = 1) -> list[Transaction]:
        query = select(Transaction).order_by(_build_order_by(filters.sort))
        for condition in _filter_conditions(filters, cycle_start_day):
            query = query.where(condition)
        query = query.offset(filters.offset).limit(filters.limit)
        result = await self._session.execute(query)
        return list(result.scalars().all())

    async def get_filtered_sum(self, filters: TransactionFilters, cycle_start_day: int = 1) -> tuple[Decimal, int]:
        """Net signed total across every transaction matching filters.type (and the
        rest of the filter set), regardless of pagination -- income credits, expense
        and transfer debit, matching the sign convention used everywhere else
        (_account_delta, get_ledger_events). Used for the "total across all pages of
        this filtered result" summary on the transactions page.
        """
        # No currency filter means the list itself spans every currency, so the sum
        # must be normalized (amount_eur) rather than adding raw native amounts
        # across currencies -- same fallback GLOBAL_CURRENCY uses everywhere else.
        amount_column = _amount_column(filters.currency or GLOBAL_CURRENCY)
        delta = case((Transaction.type == "income", amount_column), else_=-amount_column)
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
                Transaction.generated_from_transaction_id == source_transaction_id
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

        Income credits its account; expense and untracked-counterpart
        transfers debit their account (money left the tracked system);
        internal transfers (counterpart_account_id set) debit the source
        *and* credit the counterpart -- two legs from one row, so those are
        produced as a second, unioned select.

        A source leg whose counterpart account has auto_mirror_transfers enabled
        (see Account.auto_mirror_transfers) has a real mirror Transaction row on the
        counterpart side instead -- that mirror already contributes its own credit
        via source_legs, so the synthetic counterpart leg is skipped for it here to
        avoid crediting the counterpart account twice.
        """
        amount_column = _amount_column(currency)
        delta = case((Transaction.type == "income", amount_column), else_=-amount_column)
        Mirror = aliased(Transaction)
        has_mirror = (
            select(Mirror.id).where(Mirror.generated_from_transaction_id == Transaction.id).exists()
        )

        source_legs = select(Transaction.account_id, Transaction.date, delta).where(
            Transaction.date <= to_date
        )
        counterpart_legs = select(
            Transaction.counterpart_account_id, Transaction.date, amount_column
        ).where(
            Transaction.type == "transfer",
            Transaction.counterpart_account_id.is_not(None),
            Transaction.date <= to_date,
            ~has_mirror,
        )
        if currency != GLOBAL_CURRENCY:
            source_legs = source_legs.where(Transaction.currency == currency)
            counterpart_legs = counterpart_legs.where(Transaction.currency == currency)

        query = source_legs.union_all(counterpart_legs)
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
