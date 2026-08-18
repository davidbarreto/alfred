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

Installment ("Parcela M/N") purchases:
- Unlike ActivoBank, there's no separate schedule table and no bank-issued
  plan reference -- every row IS a real, already-amortized charge (title
  ends ``" - Parcela M/N"``), so N (total installments) is read directly off
  a single row instead of inferred from a schedule table's remaining tail.
- No original lump-sum purchase to find/supersede either -- the normalized
  merchant title (the text before " - Parcela") doubles as both plan_ref and
  original_amount=None signals that to the import service (see
  ImportService._apply_one_installment_plan_action), which skips the
  match/placeholder step entirely in that case.
- Using the bare merchant text as plan_ref (no numeric ref available) carries
  the same known limitation as the manual "New plan" form: two genuinely
  separate plans for the same merchant text collide into one.
"""
from __future__ import annotations

import csv
import io
import re
from datetime import date

from app.shared.statement import ParsedInstallmentPlanSignal, ParsedRow, ParsedStatement, decode
from app.shared.statement import parse_european_amount as parse_amount

_PROVIDER = "nubank_card"
_HEADER = ("date", "title", "amount")
_INSTALLMENT_RE = re.compile(r"^(.*?)\s*-\s*Parcela\s+(\d+)/(\d+)$", re.IGNORECASE)


def _parse_iso_date(raw: str) -> date | None:
    try:
        return date.fromisoformat(raw.strip())
    except ValueError:
        return None


def _installment_plan_signals(rows: list[ParsedRow]) -> list[ParsedInstallmentPlanSignal]:
    """One signal per distinct merchant text carrying a "Parcela M/N" suffix in this
    statement -- deduplicated since the same ongoing plan can post more than one
    installment within a single export. N is read straight off whichever row is seen
    first; every row sharing this plan is expected to report the same N."""
    totals: dict[str, int] = {}
    for row in rows:
        match = _INSTALLMENT_RE.match(row.raw_description)
        if match is None:
            continue
        base_description = match.group(1).strip()
        total_installments = int(match.group(3))
        totals.setdefault(base_description, total_installments)
    return [
        ParsedInstallmentPlanSignal(
            plan_ref=description,
            description=description,
            original_amount=None,
            total_installments=total,
        )
        for description, total in totals.items()
    ]


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
            title = record[1].strip()
            rows.append(
                ParsedRow(
                    date_posted=row_date,
                    date_value=row_date,
                    raw_description=title,
                    amount=-amount,
                    currency="BRL",
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
            installment_plans_opened=_installment_plan_signals(rows),
        )
