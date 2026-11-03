"""One-off maintenance script: fill finance.import_batches.closing_balance for ActivoBank
card statement PDFs imported before the parser started reading the statement's own
"Saldo em Dívida", by re-parsing each batch's stored PDF.

Only touches batches of the card PDF providers whose closing_balance is NULL and whose
stored file is still on disk; every other batch is left alone. Does not recompute
account balances -- run backfill_account_balances.py afterwards (it anchors on the
latest closing_balance).

Usage (from backend/, with the venv active):
    python scripts/backfill_card_statement_closing_balance.py
"""
import asyncio
from pathlib import Path

from sqlalchemy import select

import app.main  # noqa: F401 -- loads every tables.py so SQLAlchemy can configure relationships
from app.config import get_settings
from app.db.session import async_session
from app.features.finance.imports.tables import ImportBatch
from app.integrations.activobank.card_pdf_statement_parser import ActivoBankCardPdfStatementParser

_PROVIDERS = ("activobank_card_pdf", "activobank_card_pdf_full")


async def main() -> None:
    root = Path(get_settings().statement_storage_dir)
    parser = ActivoBankCardPdfStatementParser()
    async with async_session() as session:
        batches = (
            await session.execute(
                select(ImportBatch).where(
                    ImportBatch.provider.in_(_PROVIDERS),
                    ImportBatch.closing_balance.is_(None),
                    ImportBatch.stored_file.is_not(None),
                )
            )
        ).scalars().all()
        updated = 0
        for batch in batches:
            path = root / batch.stored_file
            if not path.is_file():
                print(f"  batch_id={batch.id} stored file missing, skipped")
                continue
            closing_balance = parser.parse(path.read_bytes()).closing_balance
            if closing_balance is None:
                print(f"  batch_id={batch.id} no closing balance found, skipped")
                continue
            batch.closing_balance = closing_balance
            updated += 1
            print(f"  batch_id={batch.id} period_end={batch.period_end} closing_balance -> {closing_balance}")
        await session.commit()
        print(f"Updated {updated} of {len(batches)} batch(es).")


if __name__ == "__main__":
    asyncio.run(main())
