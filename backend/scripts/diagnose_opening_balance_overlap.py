"""Read-only diagnostic: for each account, show its opening_balance/opening_balance_date
alongside the earliest transaction on record and how many transactions predate that
date. backfill_account_balances.py currently sums ALL transactions on top of
opening_balance regardless of date -- if opening_balance was captured at a point that
already reflects earlier history (e.g. a snapshot taken after years of activity, with
that same history later bulk-imported from statements), every pre-opening_balance_date
transaction gets double-counted on top of a balance that already includes its effect.

Makes no changes.

Usage (from backend/, with the venv active):
    python scripts/diagnose_opening_balance_overlap.py
"""
import asyncio

from sqlalchemy import text

from app.db.session import async_session

_QUERY = text(
    """
    SELECT
        a.id, a.name, a.opening_balance, a.opening_balance_date,
        MIN(t.date) AS earliest_txn_date,
        COUNT(*) FILTER (
            WHERE a.opening_balance_date IS NOT NULL AND t.date < a.opening_balance_date
        ) AS txns_before_opening_balance_date,
        COALESCE(SUM(
            CASE WHEN t.type = 'income' THEN t.amount ELSE -t.amount END
        ) FILTER (
            WHERE a.opening_balance_date IS NOT NULL AND t.date < a.opening_balance_date
        ), 0) AS pre_opening_net_effect
    FROM finance.accounts a
    LEFT JOIN finance.transactions t ON t.account_id = a.id
    GROUP BY a.id, a.name, a.opening_balance, a.opening_balance_date
    ORDER BY a.id
    """
)


async def main() -> None:
    async with async_session() as session:
        result = await session.execute(_QUERY)
        for row in result.all():
            print(
                f"  account_id={row.id} name={row.name!r} opening_balance={row.opening_balance} "
                f"opening_balance_date={row.opening_balance_date} earliest_txn_date={row.earliest_txn_date} "
                f"txns_before_opening_balance_date={row.txns_before_opening_balance_date} "
                f"pre_opening_net_effect={row.pre_opening_net_effect}"
            )


if __name__ == "__main__":
    asyncio.run(main())
