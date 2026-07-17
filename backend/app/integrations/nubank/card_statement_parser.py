"""Parser for Nubank (BR) credit-card CSV exports.

Format notes:
- UTF-8, ``,``-delimited with a plain ``date,title,amount`` header
- ISO dates (``2025-08-11``); single date column (no separate value date)
- Amounts in Brazilian format, quoted when they contain separators:
  ``"1.187,58"`` (purchase), ``"- 1.237,51"`` (payment received)
- Sign convention is inverted relative to the import convention: purchases
  are positive, the bill payment negative. Amounts are negated here so the
  normalized rows follow the convention (negative = money out).
- No running balance and no account metadata; currency is always BRL.
"""
from __future__ import annotations

import csv
import io
from datetime import date

from app.shared.statement import ParsedRow, ParsedStatement, decode
from app.shared.statement import parse_european_amount as parse_amount

_PROVIDER = "nubank_card"
_HEADER = ("date", "title", "amount")


def _parse_iso_date(raw: str) -> date | None:
    try:
        return date.fromisoformat(raw.strip())
    except ValueError:
        return None


class NubankCardStatementParser:

    @property
    def provider(self) -> str:
        return _PROVIDER

    def can_parse(self, filename: str, content: bytes) -> bool:
        if not filename.lower().endswith(".csv"):
            return False
        first_line = decode(content[:256]).splitlines()[0].strip().lower() if content else ""
        return first_line == ",".join(_HEADER)

    def parse(self, content: bytes) -> ParsedStatement:
        text = decode(content)
        reader = csv.reader(io.StringIO(text), delimiter=",")

        rows: list[ParsedRow] = []
        header_seen = False

        for record in reader:
            if not record or all(not cell.strip() for cell in record):
                continue
            if not header_seen:
                header_seen = True
                continue
            if len(record) < 3:
                continue
            row_date = _parse_iso_date(record[0])
            amount = parse_amount(record[2])
            if row_date is None or amount is None:
                continue
            rows.append(
                ParsedRow(
                    date_posted=row_date,
                    date_value=row_date,
                    raw_description=record[1].strip(),
                    amount=-amount,
                    balance_after=None,
                )
            )

        dates = [r.date_posted for r in rows]
        return ParsedStatement(
            provider=_PROVIDER,
            account_number=None,
            currency="BRL",
            period_start=min(dates) if dates else None,
            period_end=max(dates) if dates else None,
            closing_balance=None,
            rows=rows,
        )
