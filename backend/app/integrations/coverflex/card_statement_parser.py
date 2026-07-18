"""Parser for Coverflex meal-card CSV exports.

Format notes:
- UTF-8, ``,``-delimited, single header row:
  ``id,date,type,status,merchant,amount,currency,is_debit,category,product,
  voucher_count,voucher_amount,rejection_reason``
- ISO dates (``2025-09-29``); single date column (no separate value date).
- Only ``status == "confirmed"`` rows are kept; pending/rejected rows never
  actually moved money (``rejection_reason`` is only populated for those).
- Amounts already follow the import convention (negative = money out): card
  purchases arrive negative, top-ups positive. No sign flip needed, unlike
  Nubank's inverted export.
- ``type == "transfer"`` rows are payroll top-ups: real income the employer
  pays directly onto the card, never recorded as income anywhere else in
  Alfred -- unlike Revolut's card top-ups (money moving from an account
  that's typically already tracked elsewhere), these must NOT be
  suppressed to a transfer or they'd silently understate income. Left to
  the default sign-based inference, same as ``type == "purchase"``.
- No running balance and no account metadata; ``category``/``product``/
  ``voucher_count``/``voucher_amount``/``rejection_reason`` are not surfaced.
"""
from __future__ import annotations

import csv
import io
from datetime import date
from decimal import Decimal, InvalidOperation

from app.shared.statement import ParsedRow, ParsedStatement, decode

_PROVIDER = "coverflex_card"
_HEADER = (
    "id,date,type,status,merchant,amount,currency,is_debit,category,product,"
    "voucher_count,voucher_amount,rejection_reason"
)


def _parse_iso_date(raw: str) -> date | None:
    try:
        return date.fromisoformat(raw.strip())
    except ValueError:
        return None


def _parse_amount(raw: str) -> Decimal | None:
    cleaned = raw.strip()
    if not cleaned:
        return None
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return None


class CoverflexCardStatementParser:

    @property
    def provider(self) -> str:
        return _PROVIDER

    def can_parse(self, filename: str, content: bytes) -> bool:
        if not filename.lower().endswith(".csv"):
            return False
        head = decode(content[:512])
        first_line = head.splitlines()[0].strip() if head else ""
        return first_line == _HEADER

    def parse(self, content: bytes) -> ParsedStatement:
        text = decode(content)
        reader = csv.DictReader(io.StringIO(text))

        rows: list[ParsedRow] = []
        for record in reader:
            if (record.get("status") or "").strip().lower() != "confirmed":
                continue

            row_date = _parse_iso_date(record.get("date") or "")
            amount = _parse_amount(record.get("amount") or "")
            currency = (record.get("currency") or "").strip().upper()
            if row_date is None or amount is None or not currency:
                continue

            rows.append(
                ParsedRow(
                    date_posted=row_date,
                    date_value=row_date,
                    raw_description=(record.get("merchant") or "").strip(),
                    amount=amount,
                    currency=currency,
                    balance_after=None,
                )
            )

        dates = [r.date_posted for r in rows]
        return ParsedStatement(
            provider=_PROVIDER,
            account_number=None,
            currency=rows[0].currency if rows else "EUR",
            period_start=min(dates) if dates else None,
            period_end=max(dates) if dates else None,
            closing_balance=None,
            rows=rows,
        )
