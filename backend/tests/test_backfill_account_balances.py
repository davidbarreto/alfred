from datetime import date
from decimal import Decimal

from scripts.backfill_account_balances import LedgerTransaction, compute_account_balance


def _txn(id_: int, day: date, type_: str = "expense", amount: str = "10.00", balance_after: str | None = None) -> LedgerTransaction:
    return LedgerTransaction(
        id=id_, date=day, type=type_, amount=Decimal(amount),
        balance_after=Decimal(balance_after) if balance_after is not None else None,
    )


class TestNoBalanceAfterAnywhere:
    """Card-format statements / manual entries: falls back to summing signed
    deltas on top of opening_balance."""

    def test_sums_income_and_expense_deltas_on_top_of_opening_balance(self):
        transactions = [
            _txn(1, date(2026, 1, 5), type_="expense", amount="20.00"),
            _txn(2, date(2026, 1, 6), type_="income", amount="500.00"),
            _txn(3, date(2026, 1, 7), type_="expense", amount="15.50"),
        ]
        balance = compute_account_balance(Decimal("100.00"), None, transactions)
        assert balance == Decimal("100.00") - Decimal("20.00") + Decimal("500.00") - Decimal("15.50")

    def test_transfer_debits_and_credits_like_expense(self):
        """A transfer with a positive amount leaves the account (like an
        expense); negative arrives (like income) -- see
        TransactionService._account_delta's sign convention."""
        transactions = [
            _txn(1, date(2026, 1, 5), type_="transfer", amount="300.00"),   # leaving
            _txn(2, date(2026, 1, 6), type_="transfer", amount="-40.00"),   # arriving
        ]
        balance = compute_account_balance(Decimal("1000.00"), None, transactions)
        assert balance == Decimal("1000.00") - Decimal("300.00") + Decimal("40.00")

    def test_no_opening_balance_defaults_to_zero(self):
        transactions = [_txn(1, date(2026, 1, 5), type_="income", amount="50.00")]
        assert compute_account_balance(None, None, transactions) == Decimal("50.00")

    def test_no_transactions_returns_opening_balance_unchanged(self):
        assert compute_account_balance(Decimal("42.00"), None, []) == Decimal("42.00")

    def test_no_transactions_and_no_opening_balance_returns_zero(self):
        assert compute_account_balance(None, None, []) == Decimal("0")


class TestOpeningBalanceDateCutoff:
    """opening_balance is a snapshot as of opening_balance_date -- transactions
    dated before it are already baked into that snapshot and must be ignored,
    or their effect gets double-counted on top of it."""

    def test_ignores_transactions_dated_before_opening_balance_date(self):
        transactions = [
            # Pre-existing history the opening_balance snapshot already reflects.
            _txn(1, date(2025, 6, 2), type_="expense", amount="169.98"),
            _txn(2, date(2025, 7, 20), type_="income", amount="3699.16"),
            # Only these, on/after opening_balance_date, should count.
            _txn(3, date(2025, 8, 1), type_="expense", amount="3.82"),
            _txn(4, date(2025, 8, 4), type_="expense", amount="600.00"),
        ]
        balance = compute_account_balance(
            Decimal("2997.74"), date(2025, 8, 1), transactions,
        )
        assert balance == Decimal("2997.74") - Decimal("3.82") - Decimal("600.00")

    def test_transaction_dated_exactly_on_opening_balance_date_counts(self):
        transactions = [_txn(1, date(2025, 8, 1), type_="expense", amount="5.00")]
        balance = compute_account_balance(Decimal("100.00"), date(2025, 8, 1), transactions)
        assert balance == Decimal("95.00")

    def test_all_transactions_predating_opening_balance_date_are_ignored_entirely(self):
        transactions = [
            _txn(1, date(2025, 1, 1), type_="expense", amount="9999.00"),
            _txn(2, date(2025, 6, 1), type_="income", amount="8888.00"),
        ]
        balance = compute_account_balance(Decimal("50.00"), date(2025, 8, 1), transactions)
        assert balance == Decimal("50.00")


class TestBalanceAfterTrusted:
    """Any account with at least one statement-reported balance_after uses the
    latest one directly, bypassing delta-summing (and its opening_balance_date
    cutoff) entirely -- the bank's own number is authoritative."""

    def test_uses_latest_balance_after_ignoring_summed_deltas(self):
        transactions = [
            _txn(1, date(2026, 1, 5), type_="expense", amount="20.00", balance_after="480.00"),
            _txn(2, date(2026, 1, 6), type_="income", amount="500.00", balance_after="980.00"),
            _txn(3, date(2026, 1, 7), type_="expense", amount="15.50", balance_after="964.50"),
        ]
        # A naive delta-sum on top of some opening_balance would land somewhere
        # else entirely -- the statement's own number must win regardless.
        balance = compute_account_balance(Decimal("999999.00"), None, transactions)
        assert balance == Decimal("964.50")

    def test_ignores_opening_balance_date_cutoff_when_balance_after_present(self):
        """Even a transaction dated before opening_balance_date is eligible to be
        the latest balance_after row -- this branch doesn't consult
        opening_balance_date at all, only the statement's own report."""
        transactions = [
            _txn(1, date(2025, 6, 1), type_="expense", amount="10.00", balance_after="990.00"),
        ]
        balance = compute_account_balance(Decimal("1.00"), date(2025, 8, 1), transactions)
        assert balance == Decimal("990.00")

    def test_mixed_rows_only_balance_after_rows_are_considered_for_latest(self):
        """A statement-tracked account can still have rows with no balance_after
        (e.g. a manually-added transaction) -- those must never be picked as
        "latest" just for being dated later, since they carry no real number."""
        transactions = [
            _txn(1, date(2026, 1, 5), type_="expense", amount="20.00", balance_after="480.00"),
            _txn(2, date(2026, 1, 9), type_="expense", amount="5.00"),  # no balance_after, latest date
        ]
        balance = compute_account_balance(Decimal("500.00"), None, transactions)
        assert balance == Decimal("480.00")

    def test_ties_on_date_broken_by_highest_id(self):
        transactions = [
            _txn(1, date(2026, 1, 5), balance_after="100.00"),
            _txn(2, date(2026, 1, 5), balance_after="105.00"),
        ]
        balance = compute_account_balance(Decimal("0"), None, transactions)
        assert balance == Decimal("105.00")
