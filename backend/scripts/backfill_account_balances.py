"""One-off maintenance script: backfill finance.accounts.balance from the full
transaction ledger.

Account.balance was a manually-edited snapshot never kept in sync with
transactions (every account sitting at 0 regardless of real history). From
this point on it's maintained incrementally by the app on every transaction
create/update/delete and statement import commit (see
TransactionService._reconcile_balance and ImportService._sync_account_balance),
but existing accounts need their balance reconstructed once from history
first -- this script does that, then incremental maintenance takes over.

balance_after (added alongside this) is not used here: it's NULL for every
transaction imported before that column existed, so this always sums signed
transaction deltas -- income credits; expense and transfer legs debit their
own account. A transfer's counterpart_account_id also credits the *other*
account, but only when counterpart_transaction_id is NULL -- i.e. still an
unconfirmed guess, with no real second transaction row of its own. Once a
transfer is confirmed-linked (counterpart_transaction_id set, via
TransactionService.link_transfer or an import's automatic same-event-currency
pairing), the counterpart leg is itself a real row already contributing its
own delta -- crediting it again here would double-count the transfer (see
TransactionService.create/_reconcile_balance/delete for the matching live
logic this mirrors). On top of each account's opening_balance (0 if unset).
No currency filtering/conversion: each account's transactions are assumed to
already be in that account's own currency, so amounts are summed as stored.

Usage (from backend/, with the venv active):
    python scripts/backfill_account_balances.py
"""
import asyncio

from sqlalchemy import text

from app.db.session import async_session

_QUERY = text(
    """
    WITH source_legs AS (
        SELECT account_id,
               CASE WHEN type = 'income' THEN amount ELSE -amount END AS delta
        FROM finance.transactions
    ),
    counterpart_legs AS (
        SELECT counterpart_account_id AS account_id, amount AS delta
        FROM finance.transactions
        WHERE type = 'transfer'
          AND counterpart_account_id IS NOT NULL
          AND counterpart_transaction_id IS NULL
    ),
    totals AS (
        SELECT account_id, SUM(delta) AS total_delta
        FROM (SELECT * FROM source_legs UNION ALL SELECT * FROM counterpart_legs) legs
        GROUP BY account_id
    )
    UPDATE finance.accounts a
    SET balance = COALESCE(a.opening_balance, 0) + COALESCE(t.total_delta, 0)
    FROM totals t
    WHERE a.id = t.account_id
    RETURNING a.id, a.name, a.balance
    """
)


async def main() -> None:
    async with async_session() as session:
        result = await session.execute(_QUERY)
        rows = result.all()
        await session.commit()
        for row in rows:
            print(f"  account_id={row.id} name={row.name!r} balance -> {row.balance}")
        print(f"Updated {len(rows)} account(s).")


if __name__ == "__main__":
    asyncio.run(main())
