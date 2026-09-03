"""Read-only diagnostic: find likely-duplicate transactions across all Revolut
accounts by content (date, bank_description, amount, balance_after) -- two rows
matching on all four almost certainly represent the same real transaction imported
twice. deduplication_hash has a UNIQUE DB constraint, so if both rows exist, their
hashes must differ despite representing the same event; this also reports whether
either side has a NULL balance_after, which would point at the per-file occurrence-
counter disambiguator (see _compute_dedup_hash) as the source of the instability --
that counter depends on a row's position among same-key rows in the file, which
isn't stable across two import runs of overlapping-but-differently-windowed exports.

Makes no changes.

Usage (from backend/, with the venv active):
    python scripts/diagnose_revolut_duplicates.py
"""
import asyncio

from sqlalchemy import text

from app.db.session import async_session

_QUERY = text(
    """
    SELECT t.date, t.bank_description, t.amount, t.balance_after,
           a.id AS account_id, a.name AS account_name,
           array_agg(t.id ORDER BY t.id) AS txn_ids,
           array_agg(t.deduplication_hash ORDER BY t.id) AS hashes,
           count(*) AS occurrences
    FROM finance.transactions t
    JOIN finance.accounts a ON a.id = t.account_id
    WHERE a.name ILIKE 'Revolut%'
    GROUP BY t.date, t.bank_description, t.amount, t.balance_after, a.id, a.name
    HAVING count(*) > 1
    ORDER BY a.name, t.date
    """
)


async def main() -> None:
    async with async_session() as session:
        rows = (await session.execute(_QUERY)).all()
        if not rows:
            print("No content-duplicate groups found across Revolut accounts.")
            return
        for row in rows:
            null_balance = row.balance_after is None
            print(
                f"  account={row.account_name!r} date={row.date} amount={row.amount} "
                f"balance_after={row.balance_after}{' (NULL!)' if null_balance else ''} "
                f"desc={row.bank_description!r} occurrences={row.occurrences} "
                f"txn_ids={list(row.txn_ids)} hashes={[h[:12] + '...' for h in row.hashes]}"
            )
        print(f"\n{len(rows)} content-duplicate group(s) found.")


if __name__ == "__main__":
    asyncio.run(main())
