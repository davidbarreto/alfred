"""Read-only diagnostic: find transfer rows whose counterpart_account_id is only an
unconfirmed guess (counterpart_transaction_id IS NULL) but where a real transaction
already exists on the counterpart account that plausibly IS that same leg -- i.e. the
transfer was actually imported on both sides, just never explicitly Find Match-linked.

Those rows still trigger the synthetic counterpart-credit in
TransactionService/ImportService and backfill_account_balances.py (see the recent
fix), which is only safe when NO real second leg exists. If a real, unlinked
counterpart transaction is sitting right there, that credit double-counts the
transfer on top of the counterpart's own real leg -- explaining balances still being
wrong after the confirmed-pair fix.

This makes no changes. It only reports candidates for manual review / linking via
Find Match in the portal.

Usage (from backend/, with the venv active):
    python scripts/diagnose_unconfirmed_transfer_guesses.py
"""
import asyncio

from sqlalchemy import text

from app.db.session import async_session

_QUERY = text(
    """
    SELECT
        t.id AS txn_id, a.name AS account_name, t.date, t.amount, t.currency,
        t.bank_description, ca.name AS counterpart_account_name,
        c.id AS candidate_id, c.amount AS candidate_amount, c.currency AS candidate_currency,
        c.bank_description AS candidate_description, c.date AS candidate_date
    FROM finance.transactions t
    JOIN finance.accounts a ON a.id = t.account_id
    JOIN finance.accounts ca ON ca.id = t.counterpart_account_id
    LEFT JOIN finance.transactions c
        ON c.account_id = t.counterpart_account_id
       AND c.counterpart_transaction_id IS NULL
       AND c.id != t.id
       AND ABS(c.date - t.date) <= INTERVAL '3 days'
    WHERE t.type = 'transfer'
      AND t.counterpart_account_id IS NOT NULL
      AND t.counterpart_transaction_id IS NULL
    ORDER BY t.account_id, t.date
    """
)


async def main() -> None:
    async with async_session() as session:
        result = await session.execute(_QUERY)
        rows = result.all()
        unmatched = 0
        with_candidate = 0
        for row in rows:
            if row.candidate_id is None:
                unmatched += 1
                continue
            with_candidate += 1
            print(
                f"  txn_id={row.txn_id} account={row.account_name!r} date={row.date} "
                f"amount={row.amount} {row.currency} desc={row.bank_description!r} "
                f"-> counterpart_account={row.counterpart_account_name!r} "
                f"CANDIDATE txn_id={row.candidate_id} date={row.candidate_date} "
                f"amount={row.candidate_amount} {row.candidate_currency} "
                f"desc={row.candidate_description!r}"
            )
        print(f"\n{with_candidate} unconfirmed-guess row(s) have a plausible unlinked counterpart already in the ledger.")
        print(f"{unmatched} unconfirmed-guess row(s) have no candidate nearby (guess with no second row -- credit is legitimate for these).")


if __name__ == "__main__":
    asyncio.run(main())
