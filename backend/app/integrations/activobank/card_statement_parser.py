"""Parser for ActivoBank (PT) credit-card movement CSV exports.

Format notes (differs from the account-history export):
- UTF-8 with BOM, ``;``-delimited
- Preamble: ``Movimentos a Crédito na Conta Cartão Número <card>``, currency,
  linked account (``Conta à Ordem``), date range
- Header row: ``Data Lanc.;Data Valor;Descrição;Valor;`` — no running balance
- Sign convention is inverted relative to the account export: purchases are
  positive, the monthly payment is negative. Amounts are negated here so the
  normalized rows follow the import convention (negative = money out).
"""
from __future__ import annotations

import csv
import io
import re
from datetime import date

from app.integrations.activobank.parsing import parse_date
from app.shared.statement import ParsedRow, ParsedStatement, decode
from app.shared.statement import parse_european_amount as parse_amount

_PROVIDER = "activobank_card"
_HEADER_FIRST_COL = "data lanc"
_CARD_RE = re.compile(r"CART.O N.MERO\s+(\d+)", re.IGNORECASE)


class ActivoBankCardStatementParser:

    @property
    def provider(self) -> str:
        return _PROVIDER

    def can_parse(self, filename: str, content: bytes) -> bool:
        if not filename.lower().endswith(".csv"):
            return False
        head = decode(content[:2048]).upper()
        return "MOVIMENTOS" in head and "CART" in head and ";" in head

    def parse(self, content: bytes) -> ParsedStatement:
        text = decode(content)
        reader = csv.reader(io.StringIO(text), delimiter=";")

        card_number: str | None = None
        currency = "EUR"
        period_start: date | None = None
        period_end: date | None = None
        rows: list[ParsedRow] = []
        in_body = False

        for record in reader:
            if not record or all(not cell.strip() for cell in record):
                continue
            first = record[0].strip()

            if not in_body:
                match = _CARD_RE.search(first)
                if match:
                    card_number = match.group(1)
                if first.lower().startswith("moeda") and len(record) > 1 and record[1].strip():
                    currency = record[1].strip()
                if first.lower().startswith("data de") and len(record) > 1:
                    period_start = parse_date(record[1])
                if first.lower().startswith("data at") and len(record) > 1:
                    period_end = parse_date(record[1])
                if first.lower().startswith(_HEADER_FIRST_COL):
                    in_body = True
                continue

            if len(record) < 4:
                continue
            date_posted = parse_date(record[0])
            date_value = parse_date(record[1])
            amount = parse_amount(record[3])
            if date_posted is None or amount is None:
                continue
            rows.append(
                ParsedRow(
                    date_posted=date_posted,
                    date_value=date_value or date_posted,
                    raw_description=record[2].strip(),
                    amount=-amount,
                    currency=currency,
                    balance_after=None,
                )
            )

        return ParsedStatement(
            provider=_PROVIDER,
            account_number=card_number,
            currency=currency,
            period_start=period_start,
            period_end=period_end,
            closing_balance=None,
            rows=rows,
        )
