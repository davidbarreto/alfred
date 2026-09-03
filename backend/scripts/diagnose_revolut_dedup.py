"""Read-only diagnostic: parse a Revolut CSV with the real parser, compute each row's
deduplication_hash exactly as import preview would, and report which of those hashes
already exist in the DB. Reproduces "why doesn't re-importing this file get flagged
as duplicates" without needing to go through the API/portal.

Makes no changes.

Usage (from backend/, with the venv active):
    python scripts/diagnose_revolut_dedup.py <path-to-csv> <account_id>
"""
import asyncio
import sys
from pathlib import Path

from sqlalchemy import text

from app.db.session import async_session
from app.features.finance.imports.service import _compute_dedup_hash
from app.integrations.revolut.statement_parser import RevolutStatementParser

_EXISTS_QUERY = text(
    "SELECT 1 FROM finance.transactions WHERE deduplication_hash = :hash LIMIT 1"
)


async def main(csv_path: str, account_id: int) -> None:
    content = Path(csv_path).read_bytes()
    parser = RevolutStatementParser()
    statement = parser.parse(content)

    async with async_session() as session:
        matched = 0
        unmatched = 0
        for occurrence, row in enumerate(statement.rows, start=1):
            dedup_hash = _compute_dedup_hash(account_id, row, occurrence)
            exists = (await session.execute(_EXISTS_QUERY, {"hash": dedup_hash})).first() is not None
            if exists:
                matched += 1
            else:
                unmatched += 1
                print(
                    f"  NOT FOUND: date={row.date_posted} amount={row.amount} "
                    f"currency={row.currency} balance_after={row.balance_after} "
                    f"posted_at={row.posted_at!r} desc={row.raw_description!r} hash={dedup_hash}"
                )
        print(f"\n{matched} row(s) matched an existing hash, {unmatched} did not.")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python scripts/diagnose_revolut_dedup.py <path-to-csv> <account_id>")
        sys.exit(1)
    asyncio.run(main(sys.argv[1], int(sys.argv[2])))
