"""Parser for Revolut account-statement CSV exports.

Format notes:
- UTF-8, ``,``-delimited, single header row:
  ``Type,Product,Started Date,Completed Date,Description,Amount,Fee,Currency,State,Balance``
- One export can contain SEVERAL currencies mixed together (Revolut's multi-currency
  wallet), typically grouped into per-currency blocks. Alfred models one currency per
  account, so this parser is instantiated once per currency (see registry.py) and
  filters to only the rows matching its currency — the user picks the matching
  provider/account at upload time, auto-detection can't disambiguate which currency
  they mean.
- Only ``State == "COMPLETED"`` rows are kept; PENDING/REVERTED rows never actually
  moved money (empty Completed Date and Balance confirm this).
- ``Type`` classifies the row structurally, which lets us set the transaction type
  directly instead of relying on the sign-based expense/income default:
    - "Exchange": the user's own money moving between their own Revolut currency
      balances — always a transfer, in both directions/currencies.
    - "Topup": money entering from an external card not tracked as an Alfred
      account — treated as a transfer (not income) so it doesn't inflate earnings.
    - "Transfer" to "Revolut Bank UAB ...": Revolut's own entity name, most likely an
      internal sweep of a foreign-currency e-money balance into the core account —
      treated as a transfer, but flagged for review since this is a guess.
    - "Transfer to <person>": a real payment to someone else — left as a normal
      expense (the default sign-based inference already gets this right).
    - "Card Payment" / "ATM" / "Rev Payment" / "Card Refund": ordinary
      expense/income, sign-based inference already correct.
- ``Completed Date`` is used as the posting date (when it actually affected the
  balance); ``Started Date`` as the value date.
- The ``Fee`` column is informational only in the observed export (always 0.00);
  ``Amount`` already reflects the net effect on the balance, so Fee is not applied.
"""
from __future__ import annotations

import csv
import io
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from app.shared.statement import ParsedRow, ParsedStatement, decode

_HEADER = "Type,Product,Started Date,Completed Date,Description,Amount,Fee,Currency,State,Balance"
_REVOLUT_ENTITY_HINT = "Revolut Bank UAB"


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
        return Decimal(cleaned)
    except InvalidOperation:
        return None


class RevolutStatementParser:
    """One instance per currency; register a separate provider per currency held."""

    def __init__(self, currency: str) -> None:
        self._currency = currency.upper()

    @property
    def provider(self) -> str:
        return f"revolut_{self._currency.lower()}"

    @property
    def currency(self) -> str:
        return self._currency

    def can_parse(self, filename: str, content: bytes) -> bool:
        if not filename.lower().endswith(".csv"):
            return False
        text = decode(content)
        lines = text.splitlines()
        if not lines or lines[0].strip() != _HEADER:
            return False
        # A Revolut export can hold several currencies at once; auto-detect can't
        # disambiguate which one the user means, but at least rule out currencies
        # that aren't present in the file at all.
        return f",{self._currency}," in text

    def parse(self, content: bytes) -> ParsedStatement:
        text = decode(content)
        reader = csv.DictReader(io.StringIO(text))

        rows: list[ParsedRow] = []
        for record in reader:
            if (record.get("Currency") or "").strip().upper() != self._currency:
                continue
            if (record.get("State") or "").strip().upper() != "COMPLETED":
                continue

            completed = _parse_datetime(record.get("Completed Date") or "")
            started = _parse_datetime(record.get("Started Date") or "")
            amount = _parse_amount(record.get("Amount") or "")
            balance = _parse_amount(record.get("Balance") or "")
            if completed is None or amount is None:
                continue

            row_type = (record.get("Type") or "").strip()
            description = (record.get("Description") or "").strip()
            suggested_type, flag_reason = self._classify(row_type, description)

            rows.append(
                ParsedRow(
                    date_posted=completed,
                    date_value=started or completed,
                    raw_description=description,
                    amount=amount,
                    balance_after=balance,
                    suggested_type=suggested_type,
                    flag_reason=flag_reason,
                )
            )

        dates = [r.date_posted for r in rows]
        closing_balance = rows[-1].balance_after if rows else None
        return ParsedStatement(
            provider=self.provider,
            account_number=None,
            currency=self._currency,
            period_start=min(dates) if dates else None,
            period_end=max(dates) if dates else None,
            closing_balance=closing_balance,
            rows=rows,
        )

    @staticmethod
    def _classify(row_type: str, description: str) -> tuple[str | None, str | None]:
        if row_type == "Exchange":
            return "transfer", None
        if row_type == "Topup":
            return "transfer", None
        if row_type == "Transfer" and _REVOLUT_ENTITY_HINT in description:
            return "transfer", "uncertain_transfer"
        return None, None
