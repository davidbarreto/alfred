"""One-off maintenance script: recompute finance.transactions.deduplication_hash for
already-committed Revolut/Wise transactions under the current hash formula.

Background (see _compute_dedup_hash / _normalize_posted_at in
app/features/finance/imports/service.py): Revolut's own CSV export renders
"Completed Date"/"Started Date" in a timezone that drifts between exports of the
same historical period -- confirmed by diffing two real exports of the same
account months apart, where every row's hour shifted by exactly 1 while
minute:second stayed identical. The dedup hash folds in that raw timestamp
(added 2026-07-19, commit c879550, to fix a different bug: same-day/same-amount/
same-balance rows coinciding) to disambiguate intra-day collisions, so any
already-committed row's hash silently went stale the moment its source period
was re-exported -- the whole re-import showed up as "not a duplicate" even
though nothing had actually changed. The fix normalizes away the hour before
hashing; this script re-parses each Revolut/Wise import's originally-stored
file (import_batches.stored_file) and updates existing transactions' hashes
from whichever earlier formula they were written under to the current one, so
future re-imports of the same period converge instead of re-flagging
everything as new.

Two earlier formulas are checked, oldest first:
1. Pre-2026-07-19 (no posted_at component at all).
2. 2026-07-19 to now (raw, un-normalized posted_at).

A transaction already on the current formula is left untouched (idempotent --
safe to re-run, e.g. after a new Revolut/Wise import is committed).

Read-write: updates finance.transactions.deduplication_hash in place. Does not
touch amounts, balances, or any other column.

Usage (from backend/, with the venv active):
    python scripts/backfill_revolut_wise_dedup_hashes.py
"""
import asyncio
import hashlib
from collections import defaultdict

from sqlalchemy import select

import app.main  # noqa: F401 -- see backfill_account_balances.py for why this import is needed
from app.config import get_settings
from app.db.session import async_session
from app.features.finance.accounts.tables import Account
from app.features.finance.imports.registry import get_parser
from app.features.finance.imports.service import GROUPED_PROVIDERS, _compute_dedup_hash
from app.features.finance.imports.tables import ImportBatch
from app.features.finance.transactions.tables import Transaction
from app.integrations.file_storage.client import LocalFileStorage
from app.shared.statement import ParsedRow


def _legacy_hashes(account_id: int, row: ParsedRow) -> tuple[str, str]:
    """The two dedup-hash formulas that predate the current (hour-normalized) one."""
    disambiguator = str(row.balance_after) if row.balance_after is not None else "occ:1"
    base = [
        str(account_id),
        row.date_posted.isoformat(),
        row.date_value.isoformat(),
        row.raw_description,
        str(row.amount),
        disambiguator,
    ]
    pre_posted_at = hashlib.sha256("|".join(base).encode("utf-8")).hexdigest()
    raw_posted_at = hashlib.sha256(
        "|".join(base + [row.posted_at or ""]).encode("utf-8")
    ).hexdigest()
    return pre_posted_at, raw_posted_at


async def main() -> None:
    files = LocalFileStorage(get_settings().statement_storage_dir)

    async with async_session() as session:
        batches = (
            await session.execute(
                select(ImportBatch).where(ImportBatch.provider.in_(GROUPED_PROVIDERS))
            )
        ).scalars().all()
        accounts = {a.id: a for a in (await session.execute(select(Account))).scalars().all()}

        by_file: dict[str, list[ImportBatch]] = defaultdict(list)
        for batch in batches:
            if batch.stored_file:
                by_file[batch.stored_file].append(batch)

        updated = 0
        missing_files = 0
        for stored_file, batch_group in by_file.items():
            content = await files.read(stored_file)
            if content is None:
                print(f"  SKIP missing file on disk: {stored_file}")
                missing_files += 1
                continue

            parser = get_parser(batch_group[0].provider)
            if parser is None:
                continue
            statement = parser.parse(content)

            rows_by_currency: dict[str, list[ParsedRow]] = defaultdict(list)
            for row in statement.rows:
                rows_by_currency[row.currency].append(row)

            for account_id in {b.account_id for b in batch_group}:
                account = accounts.get(account_id)
                if account is None:
                    continue
                for row in rows_by_currency.get(account.currency, []):
                    new_hash = _compute_dedup_hash(account_id, row, 1)
                    pre_posted_at, raw_posted_at = _legacy_hashes(account_id, row)
                    txn = (
                        await session.execute(
                            select(Transaction).where(
                                Transaction.account_id == account_id,
                                Transaction.deduplication_hash.in_([pre_posted_at, raw_posted_at]),
                            )
                        )
                    ).scalar_one_or_none()
                    if txn is None or txn.deduplication_hash == new_hash:
                        continue
                    print(
                        f"  txn id={txn.id} account_id={account_id} "
                        f"{txn.deduplication_hash[:12]}... -> {new_hash[:12]}..."
                    )
                    txn.deduplication_hash = new_hash
                    updated += 1

        await session.commit()
        print(f"Updated {updated} transaction(s); {missing_files} stored file(s) missing on disk.")


if __name__ == "__main__":
    asyncio.run(main())
