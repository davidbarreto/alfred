"""One-off maintenance script: backfill finance.accounts.balance from the full
transaction ledger.

Account.balance was a manually-edited snapshot never kept in sync with
transactions (every account sitting at 0 regardless of real history). From
this point on it's maintained incrementally by the app on every transaction
create/update/delete and statement import commit (see
TransactionService._reconcile_balance and ImportService._sync_account_balance),
but existing accounts need their balance reconstructed once from history
first -- this script does that, then incremental maintenance takes over.

Two branches, mirroring ImportService._sync_account_balance exactly:

1. Any account with at least one transaction carrying balance_after (ActivoBank
   checking, Banco Inter, Revolut -- statements that report their own running
   "Saldo" per row) gets set directly to the balance_after of its most recently
   dated such transaction. This is the authoritative, bank-reported number --
   reconstructing it by summing deltas is unnecessary AND fragile: it has to
   correctly account for opening_balance/opening_balance_date overlap with
   pre-existing history, confirmed vs. unconfirmed transfer legs, and
   installment-plan lump-sum superseding, and a bug in any one of those
   silently compounds across the account's entire history. Trusting the
   statement's own number sidesteps all of it.

2. Only accounts with NO balance_after anywhere in their history (card-format
   statements, manual entries) fall back to summing signed transaction deltas --
   income credits; expense AND transfer legs both debit/credit only their OWN
   account, by their own stored amount, exactly like an expense/income (see
   TransactionService.create's note: counterpart_account_id is pure linking
   metadata, never a second account's balance mutation -- the counterpart's own
   balance always comes from its own transaction row, e.g. a mirror or an
   independently-imported leg, so this never reaches into another account here
   either). Summed on top of opening_balance (0 if unset), and restricted to
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

from sqlalchemy import text

from app.db.session import async_session

_STATEMENT_BALANCE_QUERY = text(
    """
    WITH latest AS (
        SELECT DISTINCT ON (account_id) account_id, balance_after
        FROM finance.transactions
        WHERE balance_after IS NOT NULL
        ORDER BY account_id, date DESC, id DESC
    )
    UPDATE finance.accounts a
    SET balance = l.balance_after
    FROM latest l
    WHERE a.id = l.account_id
    RETURNING a.id, a.name, a.balance
    """
)

_DELTA_SUM_QUERY = text(
    """
    WITH statement_tracked AS (
        SELECT DISTINCT account_id FROM finance.transactions WHERE balance_after IS NOT NULL
    ),
    totals AS (
        SELECT t.account_id,
               SUM(CASE WHEN t.type = 'income' THEN t.amount ELSE -t.amount END) AS total_delta
        FROM finance.transactions t
        JOIN finance.accounts a ON a.id = t.account_id
        WHERE t.account_id NOT IN (SELECT account_id FROM statement_tracked)
          AND (a.opening_balance_date IS NULL OR t.date >= a.opening_balance_date)
        GROUP BY t.account_id
    )
    UPDATE finance.accounts a
    SET balance = COALESCE(a.opening_balance, 0) + COALESCE(t.total_delta, 0)
    FROM totals t
    WHERE a.id = t.account_id
      AND a.id NOT IN (SELECT account_id FROM statement_tracked)
    RETURNING a.id, a.name, a.balance
    """
)


async def main() -> None:
    async with async_session() as session:
        statement_rows = (await session.execute(_STATEMENT_BALANCE_QUERY)).all()
        delta_rows = (await session.execute(_DELTA_SUM_QUERY)).all()
        await session.commit()
        for row in statement_rows:
            print(f"  account_id={row.id} name={row.name!r} balance -> {row.balance} (from statement balance_after)")
        for row in delta_rows:
            print(f"  account_id={row.id} name={row.name!r} balance -> {row.balance} (from summed deltas)")
        print(f"Updated {len(statement_rows) + len(delta_rows)} account(s).")


if __name__ == "__main__":
    asyncio.run(main())
