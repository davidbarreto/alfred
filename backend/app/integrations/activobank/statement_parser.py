"""Parser for ActivoBank (PT) account-history CSV exports.

Format notes:
- Windows-1252 encoded, ``;``-delimited
- Preamble rows before the header: account number, currency, type, date range
- Header row: ``Data Lanc.;Data Valor;Descrição;Valor;Saldo``
- Dates ``dd/mm/yyyy``; amounts European style (``-1 200,00``)
"""
from __future__ import annotations

import csv
import io
import re
from datetime import date

from app.integrations.activobank.parsing import parse_date as _parse_date
from app.shared.statement import ParsedRow, ParsedStatement
from app.shared.statement import decode as _decode
from app.shared.statement import parse_european_amount as _parse_amount

_PROVIDER = "activobank"
_HEADER_FIRST_COL = "data lanc"
_ACCOUNT_RE = re.compile(r"CONTA N.MERO\s+(\d+)", re.IGNORECASE)


class ActivoBankStatementParser:

    @property
    def provider(self) -> str:
        return _PROVIDER

    def can_parse(self, filename: str, content: bytes) -> bool:
        if not filename.lower().endswith(".csv"):
            return False
        head = _decode(content[:2048]).upper()
        # "RICO DE CONTA" matches HISTÓRICO/HISTORICO DE CONTA regardless of accents
        return "RICO DE CONTA" in head and ";" in head

    def parse(self, content: bytes) -> ParsedStatement:
        text = _decode(content)
        reader = csv.reader(io.StringIO(text), delimiter=";")

        account_number: str | None = None
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
                match = _ACCOUNT_RE.search(first)
                if match:
                    account_number = match.group(1)
                if first.lower().startswith("moeda") and len(record) > 1 and record[1].strip():
                    currency = record[1].strip()
                if first.lower().startswith("data de") and len(record) > 1:
                    period_start = _parse_date(record[1])
                if first.lower().startswith("data at") and len(record) > 1:
                    period_end = _parse_date(record[1])
                if first.lower().startswith(_HEADER_FIRST_COL):
                    in_body = True
                continue

            if len(record) < 4:
                continue
            date_posted = _parse_date(record[0])
            date_value = _parse_date(record[1])
            amount = _parse_amount(record[3])
            if date_posted is None or amount is None:
                continue
            balance_after = _parse_amount(record[4]) if len(record) > 4 else None
            rows.append(
                ParsedRow(
                    date_posted=date_posted,
                    date_value=date_value or date_posted,
                    raw_description=record[2].strip(),
                    amount=amount,
                    currency=currency,
                    balance_after=balance_after,
                )
            )

        closing_balance = rows[-1].balance_after if rows else None
        return ParsedStatement(
            provider=_PROVIDER,
            account_number=account_number,
            currency=currency,
            period_start=period_start,
            period_end=period_end,
            closing_balance=closing_balance,
            rows=rows,
        )
