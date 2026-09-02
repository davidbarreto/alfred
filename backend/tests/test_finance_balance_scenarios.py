"""End-to-end balance scenarios: run a realistic sequence of transactions (shapes
mirrored from a real production checking account, names anonymized) through the
real TransactionService.create() -- with a stateful fake AccountRepository that
actually accumulates balance like the real one, instead of an AsyncMock that only
records calls -- and assert the final balance matches a hand-computed expected
total. This is what the confirmed/unconfirmed-transfer double-counting bugs
(see transactions/service.py's balance notes) would have caught: those bugs only
showed up once a *sequence* of transactions ran, not from any single call's
arguments in isolation.
"""
from datetime import datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.features.finance.transactions.repository import TransactionRepository
from app.features.finance.transactions.schemas import TransactionCreate
from app.features.finance.transactions.service import TransactionService
from app.features.finance.transactions.tables import Transaction


class _StatefulAccountRepo:
    """Mimics AccountRepository.adjust_balance/get closely enough to accumulate a
    real running balance across a sequence of calls, unlike AsyncMock which only
    records call arguments."""

    def __init__(self, auto_mirror_accounts: set[int] = frozenset()):
        self.balances: dict[int, Decimal] = {}
        self._auto_mirror_accounts = auto_mirror_accounts

    async def adjust_balance(self, account_id: int, delta: Decimal) -> None:
        self.balances[account_id] = self.balances.get(account_id, Decimal("0")) + delta

    async def get(self, account_id: int):
        return MagicMock(auto_mirror_transfers=account_id in self._auto_mirror_accounts)


class _StatefulTransactionRepo:
    """Mimics TransactionRepository.create closely enough to build a real Transaction
    ORM instance (not persisted -- no session/DB involved) from whatever
    TransactionCreate data was passed, with an auto-incrementing id, so
    TransactionRead.model_validate and the mirror/link logic both work against
    realistic objects instead of hand-built mocks."""

    def __init__(self):
        self._next_id = 1
        self.created: list[Transaction] = []

    async def create(self, data: TransactionCreate, amount_eur: Decimal | None = None) -> Transaction:
        txn = Transaction(
            id=self._next_id, created_at=datetime(2026, 1, 1), amount_eur=amount_eur,
            **data.model_dump(),
        )
        self._next_id += 1
        self.created.append(txn)
        return txn

    async def set_counterpart_transaction(self, transaction_id: int, counterpart_transaction_id: int | None) -> None:
        pass


@pytest.fixture
def service_with_state():
    def _make(auto_mirror_accounts: set[int] = frozenset()):
        svc = TransactionService.__new__(TransactionService)
        svc._repo = _StatefulTransactionRepo()
        svc._account_repo = _StatefulAccountRepo(auto_mirror_accounts)
        svc._fx = AsyncMock()
        svc._fx.convert_to_eur.return_value = None
        return svc
    return _make


def _txn(account_id: int, amount: str, type_: str, description: str, **kwargs) -> TransactionCreate:
    return TransactionCreate(
        account_id=account_id, date=datetime(2026, 6, 12), amount=Decimal(amount),
        currency="EUR", type=type_, description=description, **kwargs,
    )


class TestSingleAccountLedgerScenario:
    """Mirrors the shape of a real checking-account statement: opening balance,
    day-to-day card expenses, salary income, and confirmed transfers to a savings
    account and a credit card -- none of which should credit this account's own
    balance from the *other* side (see TransactionService.create's balance note)."""

    async def test_final_balance_matches_hand_computed_total(self, service_with_state):
        service = service_with_state()
        checking_account = 1
        # Seed the account's opening balance the way the app does -- a direct
        # adjust_balance from backfill/account creation, not a transaction.
        await service._account_repo.adjust_balance(checking_account, Decimal("1000.00"))

        # expense/transfer amounts are stored positive when money LEAVES this
        # account and negative when it ARRIVES -- transfer reuses the exact same
        # sign convention as expense (see _account_delta: -amount for both).
        rows = [
            _txn(checking_account, "4.50", "expense", "Coffee Shop"),
            _txn(checking_account, "38.20", "expense", "Grocery Store"),
            _txn(checking_account, "12.00", "expense", "Ride Share"),
            _txn(checking_account, "2500.00", "income", "Salary"),
            # Confirmed transfer to a savings account -- both legs already real
            # (imported/matched independently), so this account's own leg is the
            # only thing that should move ITS balance.
            _txn(
                checking_account, "300.00", "transfer", "Savings",
                counterpart_account_id=2, counterpart_transaction_id=999,
            ),
            # Confirmed transfer paying down a credit card.
            _txn(
                checking_account, "150.00", "transfer", "Credit Card Payment",
                counterpart_account_id=3, counterpart_transaction_id=998,
            ),
            _txn(checking_account, "65.30", "expense", "Utility Bill"),
            # A confirmed incoming transfer (e.g. a refund routed through another
            # tracked account) -- negative, since money is arriving.
            _txn(
                checking_account, "-40.00", "transfer", "Refund via Wallet",
                counterpart_account_id=4, counterpart_transaction_id=997,
            ),
        ]
        for row in rows:
            await service.create(row)

        expected = (
            Decimal("1000.00") - Decimal("4.50") - Decimal("38.20") - Decimal("12.00")
            + Decimal("2500.00") - Decimal("300.00") - Decimal("150.00") - Decimal("65.30")
            + Decimal("40.00")
        )
        assert expected == Decimal("2970.00")
        assert service._account_repo.balances[checking_account] == expected
        # Only this account was ever touched -- no counterpart credit leaked out.
        assert set(service._account_repo.balances) == {checking_account}


class TestAutoMirroredTransferScenario:
    """An unconfirmed transfer (no counterpart_transaction_id -- freshly created,
    not yet matched to anything) into an account with auto_mirror_transfers
    enabled must move BOTH accounts by exactly the transfer amount, once each --
    the source's own leg, and the mirror's own leg on the other side."""

    async def test_both_accounts_move_by_exactly_the_transfer_amount(self, service_with_state):
        checking_account, savings_account = 1, 2
        service = service_with_state(auto_mirror_accounts={savings_account})

        await service.create(_txn(
            checking_account, "500.00", "transfer", "Move to Savings",
            counterpart_account_id=savings_account,
        ))

        assert service._account_repo.balances[checking_account] == Decimal("-500.00")
        assert service._account_repo.balances[savings_account] == Decimal("500.00")
        # Exactly two rows exist: the source and its mirror -- no double insert.
        assert len(service._repo.created) == 2


class TestMultiCurrencyAccountScenario:
    """Mirrors a Wise/Revolut-style multi-currency setup: several currency wallets
    that are really the same underlying entity for the user, but modeled as
    separate accounts here. A same-event currency conversion between two of the
    user's own wallets, already confirmed-linked (as the import's automatic
    same-event-currency pairing would leave it), must not double-count into
    either wallet."""

    async def test_confirmed_currency_conversion_moves_each_wallet_once(self, service_with_state):
        eur_wallet, usd_wallet = 10, 11
        service = service_with_state()

        await service._account_repo.adjust_balance(eur_wallet, Decimal("200.00"))
        await service._account_repo.adjust_balance(usd_wallet, Decimal("50.00"))

        await service.create(_txn(
            eur_wallet, "90.00", "transfer", "Currency Exchange",
            counterpart_account_id=usd_wallet, counterpart_transaction_id=500,
        ))
        await service.create(_txn(
            usd_wallet, "-97.50", "transfer", "Currency Exchange",
            counterpart_account_id=eur_wallet, counterpart_transaction_id=499,
        ))

        assert service._account_repo.balances[eur_wallet] == Decimal("110.00")
        assert service._account_repo.balances[usd_wallet] == Decimal("147.50")
