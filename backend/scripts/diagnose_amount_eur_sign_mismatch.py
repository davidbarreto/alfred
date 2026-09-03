"""Read-only diagnostic: separates two different explanations for "native currency
sum is zero but the EUR sum isn't" on the transactions page.

1. A genuine sign bug -- amount_eur's sign disagrees with amount's sign on some row.
   TransactionRepository now normalizes this on every write (create/update/add/
   set_amount_eur), but rows written before that guard existed could still be wrong
   in the DB. These need a backfill.
2. Expected FX-rate drift -- amount and amount_eur can both have consistent, correct
   signs, and a currency's legs still net to zero natively but not in EUR, simply
   because each transaction was converted at its own date's exchange rate. A deposit
   and a same-size withdrawal on different days convert to different EUR amounts
   even though they cancel natively. This is not a bug and a backfill can't "fix" it.

Reports both separately so it's clear which one actually applies before deciding
whether a backfill migration is needed.

Makes no changes.

Usage (from backend/, with the venv active):
    python scripts/diagnose_amount_eur_sign_mismatch.py [account_id]
"""
import asyncio
import sys

from sqlalchemy import text

from app.db.session import async_session

_SIGN_MISMATCH_QUERY = text(
    """
    SELECT id, account_id, date, currency, type, amount, amount_eur
    FROM finance.transactions
    WHERE amount_eur IS NOT NULL
      AND amount <> 0
      AND amount_eur <> 0
      AND sign(amount) <> sign(amount_eur)
      AND (:account_id::int IS NULL OR account_id = :account_id)
    ORDER BY account_id, date
    """
)

_ZERO_NATIVE_NONZERO_EUR_QUERY = text(
    """
    SELECT account_id, currency,
           SUM(CASE WHEN type = 'expense' THEN -amount ELSE amount END) AS native_total,
           SUM(CASE WHEN type = 'expense' THEN -amount_eur ELSE amount_eur END) AS eur_total,
           count(*) AS n
    FROM finance.transactions
    WHERE currency <> 'EUR'
      AND amount_eur IS NOT NULL
      AND (:account_id::int IS NULL OR account_id = :account_id)
    GROUP BY account_id, currency
    HAVING SUM(CASE WHEN type = 'expense' THEN -amount ELSE amount END) = 0
       AND SUM(CASE WHEN type = 'expense' THEN -amount_eur ELSE amount_eur END) <> 0
    ORDER BY account_id, currency
    """
)


async def main(account_id: int | None) -> None:
    async with async_session() as session:
        mismatches = (
            await session.execute(_SIGN_MISMATCH_QUERY, {"account_id": account_id})
        ).all()
        print(f"{len(mismatches)} row(s) with amount/amount_eur SIGN MISMATCH (real bug, would need a backfill):")
        for row in mismatches:
            print(
                f"  id={row.id} account_id={row.account_id} date={row.date} type={row.type} "
                f"amount={row.amount} {row.currency} amount_eur={row.amount_eur}"
            )

        print()
        drifted = (
            await session.execute(_ZERO_NATIVE_NONZERO_EUR_QUERY, {"account_id": account_id})
        ).all()
        print(f"{len(drifted)} (account, currency) group(s) net to zero natively but not in EUR (likely FX-rate drift, not a bug):")
        for row in drifted:
            print(
                f"  account_id={row.account_id} currency={row.currency} n={row.n} "
                f"native_total={row.native_total} eur_total={row.eur_total}"
            )


if __name__ == "__main__":
    account_id = int(sys.argv[1]) if len(sys.argv) > 1 else None
    asyncio.run(main(account_id))
