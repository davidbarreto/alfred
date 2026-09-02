"""One-off maintenance script: backfill finance.accounts.balance from the full
transaction ledger.

Account.balance was a manually-edited snapshot never kept in sync with
transactions (every account sitting at 0 regardless of real history). From
this point on it's maintained incrementally by the app on every transaction
create/update/delete and statement import commit (see
TransactionService._reconcile_balance and ImportService._sync_account_balance),
but existing accounts need their balance reconstructed once from history
first -- this script does that, then incremental maintenance takes over.

compute_account_balance() (below) is the one piece of decision logic and is
covered by tests/test_backfill_account_balances.py with plain Python inputs --
no DB needed. Two branches, mirroring ImportService._sync_account_balance
exactly:

1. Any account with at least one transaction carrying balance_after (ActivoBank
   checking, Banco Inter, Revolut -- statements that report their own running
   "Saldo" per row) gets set directly to the balance_after of its most recently
   dated such transaction (ties broken by highest id). This is the
   authoritative, bank-reported number -- reconstructing it by summing deltas
   is unnecessary AND fragile: it has to correctly account for
   opening_balance/opening_balance_date overlap with pre-existing history,
   confirmed vs. unconfirmed transfer legs, and installment-plan lump-sum
   superseding, and a bug in any one of those silently compounds across the
   account's entire history. Trusting the statement's own number sidesteps all
   of it -- opening_balance_date plays no role in this branch at all.

2. Only accounts with NO balance_after anywhere in their history (card-format
   statements, manual entries) fall back to summing signed transaction deltas.
   expense stores an unsigned magnitude (sign implied by type, always a debit);
   income and transfer both store their real signed delta directly -- positive
   means money arrived/credited this account, negative means it left/debited it
   (every statement parser reads the bank's own signed column as-is for these
   two types) -- so they're summed as-is (see TransactionService._account_delta).
   counterpart_account_id is pure linking metadata, never a second account's
   balance mutation (see TransactionService.create's note) -- the counterpart's
   own balance always comes from its own transaction row, e.g. a mirror or an
   independently-imported leg, so this never reaches into another account here
   either. Summed on top of opening_balance (0 if unset), and restricted to
   transactions on/after opening_balance_date: if opening_balance was captured
   as a snapshot after existing history (rather than at zero, before any
   transactions), that earlier history's effect is already baked into
   opening_balance -- summing it again on top would double-count it. No
   currency filtering/conversion: each account's transactions are assumed to
   already be in that account's own currency, so amounts are summed as stored.

Usage (from backend/, with the venv active):
    python scripts/backfill_account_balances.py
"""
import asyncio
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import select

import app.main  # noqa: F401 -- importing every router transitively imports every tables.py,
# which SQLAlchemy needs to fully configure before a flush can resolve any model's FKs/
# relationships (see fix_installment_plan_original_amount_sign.py for the same need).
from app.db.session import async_session
from app.features.finance.accounts.tables import Account
from app.features.finance.transactions.tables import Transaction


@dataclass(frozen=True)
class LedgerTransaction:
    """Just the fields compute_account_balance needs, decoupled from the ORM so
    the function can be unit tested with plain Python objects."""

    id: int
    date: date
    type: str
    amount: Decimal
    balance_after: Decimal | None = None


def compute_account_balance(
    opening_balance: Decimal | None,
    opening_balance_date: date | None,
    transactions: list[LedgerTransaction],
) -> Decimal:
    balance_rows = [t for t in transactions if t.balance_after is not None]
    if balance_rows:
        latest = max(balance_rows, key=lambda t: (t.date, t.id))
        return latest.balance_after

    relevant = [
        t for t in transactions
        if opening_balance_date is None or t.date >= opening_balance_date
    ]
    delta = Decimal("0")
    for t in relevant:
        delta += -t.amount if t.type == "expense" else t.amount
    return (opening_balance or Decimal("0")) + delta


async def main() -> None:
    async with async_session() as session:
        accounts = (await session.execute(select(Account))).scalars().all()
        txns = (await session.execute(select(Transaction))).scalars().all()

        by_account: dict[int, list[LedgerTransaction]] = {}
        for t in txns:
            by_account.setdefault(t.account_id, []).append(
                LedgerTransaction(
                    id=t.id, date=t.date.date(), type=t.type, amount=t.amount,
                    balance_after=t.balance_after,
                )
            )

        for account in accounts:
            account.balance = compute_account_balance(
                account.opening_balance, account.opening_balance_date,
                by_account.get(account.id, []),
            )
            print(f"  account_id={account.id} name={account.name!r} balance -> {account.balance}")
        await session.commit()
        print(f"Updated {len(accounts)} account(s).")


if __name__ == "__main__":
    asyncio.run(main())
