"""Parser for Banco Inter (BR) checking-account CSV exports (Extrato Conta Corrente).

Format notes:
- UTF-8, ``;``-delimited
- Preamble: title line, ``Conta ;<number>``, ``Período ;dd/mm/yyyy a dd/mm/yyyy``,
  ``Saldo ;<current balance>``
- Header row: ``Data Lançamento;Histórico;Descrição;Valor;Saldo``
- Rows are newest-first; each row carries the running balance after it
- Brazilian amounts (``1.300,00``); normal sign convention (negative = out)
- Two description columns (Histórico + Descrição) are joined into one
"""
from __future__ import annotations

import csv
import io
import re
from datetime import date, datetime
from decimal import Decimal

from app.shared.statement import ParsedRow, ParsedStatement, decode
from app.shared.statement import parse_european_amount as parse_amount

_PROVIDER = "banco_inter"
_PERIOD_RE = re.compile(r"(\d{2}/\d{2}/\d{4})\s+a\s+(\d{2}/\d{2}/\d{4})")


def _parse_date(raw: str) -> date | None:
    try:
        return datetime.strptime(raw.strip(), "%d/%m/%Y").date()
    except ValueError:
        return None


class BancoInterStatementParser:

    @property
    def provider(self) -> str:
        return _PROVIDER

    def can_parse(self, filename: str, content: bytes) -> bool:
        if not filename.lower().endswith(".csv"):
            return False
        head = decode(content[:2048]).upper()
        return "EXTRATO CONTA CORRENTE" in head

    def parse(self, content: bytes) -> ParsedStatement:
        text = decode(content)
        reader = csv.reader(io.StringIO(text), delimiter=";")

        account_number: str | None = None
        period_start: date | None = None
        period_end: date | None = None
        closing_balance: Decimal | None = None
        rows: list[ParsedRow] = []
        in_body = False

        for record in reader:
            if not record or all(not cell.strip() for cell in record):
                continue
            first = record[0].strip()

            if not in_body:
                lowered = first.lower()
                if lowered.startswith("conta") and len(record) > 1 and record[1].strip().isdigit():
                    account_number = record[1].strip()
                if lowered.startswith("per") and len(record) > 1:
                    match = _PERIOD_RE.search(record[1])
                    if match:
                        period_start = _parse_date(match.group(1))
                        period_end = _parse_date(match.group(2))
                if lowered.startswith("saldo") and len(record) > 1:
                    closing_balance = parse_amount(record[1])
                if lowered.startswith("data lan"):
                    in_body = True
                continue

            if len(record) < 4:
                continue
            row_date = _parse_date(record[0])
            amount = parse_amount(record[3])
            if row_date is None or amount is None:
                continue
            parts = [record[1].strip(), record[2].strip()]
            description = " - ".join(p for p in parts if p)
            balance_after = parse_amount(record[4]) if len(record) > 4 else None
            rows.append(
                ParsedRow(
                    date_posted=row_date,
                    date_value=row_date,
                    raw_description=description,
                    amount=amount,
                    balance_after=balance_after,
                )
            )

        return ParsedStatement(
            provider=_PROVIDER,
            account_number=account_number,
            currency="BRL",
            period_start=period_start,
            period_end=period_end,
            closing_balance=closing_balance,
            rows=rows,
        )
