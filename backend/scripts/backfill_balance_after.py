"""One-off maintenance script: backfill Transaction.balance_after for
transactions imported before that column existed, by re-parsing the original
statement file and matching each row to its existing DB transaction via
deduplication_hash.

Only safe for statement formats that report a running balance (activobank,
banco_inter, revolut) -- for those, the hash's disambiguator is the reported
balance itself (see imports/service.py::_compute_dedup_hash), so re-parsing
the same file reproduces an identical, unique hash per real transaction. This
script refuses card-format files (activobank_card, nubank_card,
coverflex_card, wise) on purpose: they have no balance_after, so their dedup
hash relies on a per-file occurrence counter that isn't guaranteed to
reproduce identically across separate parses, and a hash "match" there
wouldn't reliably map to the same real transaction.

Idempotent: rows that already have balance_after set are left untouched, and
unmatched rows are reported but not treated as an error (they just mean that
row isn't in the DB under this account, e.g. a transaction imported into a
different account or not imported yet).

Usage (from backend/, with the venv active):
    python scripts/backfill_balance_after.py <account_id> <file1.csv> [file2.csv ...]
    python scripts/backfill_balance_after.py <account_id> <provider> [provider ...]

A bare provider name (e.g. "activobank") that isn't itself an existing file or
directory is resolved against settings.statement_storage_dir -- the same
directory the import pipeline saves uploads to (STATEMENT_STORAGE_DIR env
var, e.g. /srv/data/alfred/statements) -- as
<statement_storage_dir>/<provider>/*.csv.
"""
import asyncio
import sys
from pathlib import Path

from app.config import get_settings
from app.db.session import async_session
from app.features.finance.imports.registry import detect_parser
from app.features.finance.imports.service import _compute_dedup_hash
from app.features.finance.transactions.repository import TransactionRepository

_SAFE_PROVIDERS = {"activobank", "banco_inter", "revolut"}


async def _backfill_file(session, account_id: int, path: Path) -> None:
    content = path.read_bytes()
    parser = detect_parser(path.name, content)
    if parser is None:
        print(f"  SKIP {path.name}: no parser matched this file")
        return
    if parser.provider not in _SAFE_PROVIDERS:
        print(
            f"  SKIP {path.name}: provider={parser.provider} does not report a "
            "running balance -- refusing (dedup hash isn't stable enough to match by)"
        )
        return

    statement = parser.parse(content)
    repo = TransactionRepository(session)
    matched = updated = already_set = unmatched = skipped_no_balance = 0
    for row in statement.rows:
        if row.balance_after is None:
            skipped_no_balance += 1
            continue
        # occurrence is only used as a disambiguator when balance_after is None,
        # so the value passed here is irrelevant.
        dedup_hash = _compute_dedup_hash(account_id, row, 1)
        txn = await repo.get_by_dedup_hash(dedup_hash)
        if txn is None:
            unmatched += 1
            continue
        matched += 1
        if txn.balance_after is not None:
            already_set += 1
            continue
        txn.balance_after = row.balance_after
        updated += 1
    await session.commit()
    print(
        f"  {path.name} (provider={parser.provider}): "
        f"matched={matched} updated={updated} already_set={already_set} "
        f"unmatched={unmatched} no_balance_in_file={skipped_no_balance}"
    )


def _expand_paths(args: list[str]) -> list[Path]:
    """Each arg can be a file, a directory (globbed for *.csv, non-recursive), or a
    bare provider name (e.g. "activobank") resolved against
    settings.statement_storage_dir/<provider>/ -- the same directory the import
    pipeline itself saves uploads to.
    """
    base_dir = Path(get_settings().statement_storage_dir)
    files: list[Path] = []
    for arg in args:
        path = Path(arg)
        if not path.exists():
            provider_dir = base_dir / arg
            if provider_dir.is_dir():
                path = provider_dir
            else:
                print(f"  SKIP {arg}: not a file, directory, or known provider under {base_dir}")
                continue
        if path.is_dir():
            files.extend(sorted(path.glob("*.csv")))
        else:
            files.append(path)
    return files


async def main() -> None:
    if len(sys.argv) < 3:
        print(
            "Usage: python scripts/backfill_balance_after.py <account_id> <file_or_dir_or_provider> [...]\n"
            "  e.g. python scripts/backfill_balance_after.py 5 activobank\n"
            "  e.g. python scripts/backfill_balance_after.py 5 /srv/data/alfred/statements/activobank\n"
            "Note: revolut is a multi-currency (grouped) provider -- if your Revolut "
            "files cover more than one Alfred account, run this once per account_id "
            "against just that account's files, not the whole provider directory."
        )
        raise SystemExit(1)
    account_id = int(sys.argv[1])
    paths = _expand_paths(sys.argv[2:])
    if not paths:
        print("No files found.")
        return
    async with async_session() as session:
        for path in paths:
            await _backfill_file(session, account_id, path)


if __name__ == "__main__":
    asyncio.run(main())
