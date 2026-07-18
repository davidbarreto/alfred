"""Parser for Wise multi-currency account CSV exports.

Format notes:
- UTF-8, ``,``-delimited, single header row (some columns quoted):
  ``ID,Status,Direction,"Created on","Finished on","Source fee amount",
  "Source fee currency","Target fee amount","Target fee currency","Source
  name","Source amount (after fees)","Source currency","Target
  name","Target amount (after fees)","Target currency","Exchange
  rate",Reference,Batch,"Created by",Category,Note``
- Only ``Status == "COMPLETED"`` rows are kept; pending/cancelled rows never
  actually moved money.
- Unlike Revolut, a currency conversion is ONE row carrying both legs
  (source currency/amount going out, target currency/amount coming in),
  not two separate rows. This parser splits such a row into two
  ``ParsedRow`` entries so each currency's balance is affected correctly --
  the import service then routes each currency to its own Alfred account,
  same as Revolut's multi-currency handling.
- "Source name" == "Target name" identifies a self-transfer (moving your
  own money), as opposed to a real payment to/from a third party:
    - Self-transfer, differing currencies: a currency conversion -- two
      legs, both ``suggested_type="transfer"`` (mirrors Revolut's
      ``Exchange``).
    - Self-transfer, same currency (e.g. Category "Money added"): an
      external top-up or withdrawal -- treated as a transfer, not
      income/expense, because it's assumed to be funded from / sent to an
      account already tracked elsewhere in Alfred (mirrors Revolut's
      ``Topup``). Direction ("IN"/"OUT") gives the sign.
    - Not a self-transfer: a real payment. "OUT" is the common case
      (card purchase or payment to someone else) -- one leg, the Source
      side, left to the default sign-based expense inference. "IN" from a
      third party (someone paying you) is inferred symmetrically using the
      Target side, since no such row was available to confirm against --
      flag this for review if it doesn't match a real export.
- Amounts in the export are unsigned magnitudes ("after fees" already
  applied); this parser assigns the sign itself based on the above rules.
- ``Finished on`` is used as the posting date; ``Created on`` as the value
  date. No running balance or account metadata in this export.
"""
from __future__ import annotations

import csv
import io
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from app.shared.statement import ParsedRow, ParsedStatement, decode

_PROVIDER = "wise"
_HEADER = (
    'ID,Status,Direction,"Created on","Finished on","Source fee amount",'
    '"Source fee currency","Target fee amount","Target fee currency","Source name",'
    '"Source amount (after fees)","Source currency","Target name",'
    '"Target amount (after fees)","Target currency","Exchange rate",'
    'Reference,Batch,"Created by",Category,Note'
)


def _parse_datetime(raw: str) -> date | None:
    try:
        return datetime.strptime(raw.strip(), "%Y-%m-%d %H:%M:%S").date()
    except ValueError:
        return None


def _parse_amount(raw: str) -> Decimal | None:
    cleaned = raw.strip()
    if not cleaned:
        return None
    try:
        return abs(Decimal(cleaned))
    except InvalidOperation:
        return None


class WiseStatementParser:

    @property
    def provider(self) -> str:
        return _PROVIDER

    def can_parse(self, filename: str, content: bytes) -> bool:
        if not filename.lower().endswith(".csv"):
            return False
        head = decode(content[:1024])
        first_line = head.splitlines()[0].strip() if head else ""
        return first_line == _HEADER

    def parse(self, content: bytes) -> ParsedStatement:
        text = decode(content)
        reader = csv.DictReader(io.StringIO(text))

        rows: list[ParsedRow] = []
        for record in reader:
            if (record.get("Status") or "").strip().upper() != "COMPLETED":
                continue

            finished = _parse_datetime(record.get("Finished on") or "")
            created = _parse_datetime(record.get("Created on") or "")
            if finished is None:
                continue

            source_name = (record.get("Source name") or "").strip()
            target_name = (record.get("Target name") or "").strip()
            source_currency = (record.get("Source currency") or "").strip().upper()
            target_currency = (record.get("Target currency") or "").strip().upper()
            source_amount = _parse_amount(record.get("Source amount (after fees)") or "")
            target_amount = _parse_amount(record.get("Target amount (after fees)") or "")
            direction = (record.get("Direction") or "").strip().upper()

            if source_amount is None or target_amount is None or not source_currency or not target_currency:
                continue

            date_value = created or finished
            is_self = bool(source_name) and source_name == target_name

            if is_self and source_currency != target_currency:
                rows.append(
                    ParsedRow(
                        date_posted=finished,
                        date_value=date_value,
                        raw_description=f"Currency exchange to {target_currency}",
                        amount=-source_amount,
                        currency=source_currency,
                        suggested_type="transfer",
                    )
                )
                rows.append(
                    ParsedRow(
                        date_posted=finished,
                        date_value=date_value,
                        raw_description=f"Currency exchange from {source_currency}",
                        amount=target_amount,
                        currency=target_currency,
                        suggested_type="transfer",
                    )
                )
            elif is_self:
                description = (record.get("Category") or "").strip() or "Wise transfer"
                if direction == "IN":
                    rows.append(
                        ParsedRow(
                            date_posted=finished,
                            date_value=date_value,
                            raw_description=description,
                            amount=target_amount,
                            currency=target_currency,
                            suggested_type="transfer",
                        )
                    )
                else:
                    rows.append(
                        ParsedRow(
                            date_posted=finished,
                            date_value=date_value,
                            raw_description=description,
                            amount=-source_amount,
                            currency=source_currency,
                            suggested_type="transfer",
                        )
                    )
            elif direction == "IN":
                rows.append(
                    ParsedRow(
                        date_posted=finished,
                        date_value=date_value,
                        raw_description=source_name,
                        amount=target_amount,
                        currency=target_currency,
                    )
                )
            else:
                rows.append(
                    ParsedRow(
                        date_posted=finished,
                        date_value=date_value,
                        raw_description=target_name,
                        amount=-source_amount,
                        currency=source_currency,
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
