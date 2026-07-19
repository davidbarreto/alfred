"""Parser for Revolut account-statement CSV exports.

Format notes:
- UTF-8, ``,``-delimited, single header row:
  ``Type,Product,Started Date,Completed Date,Description,Amount,Fee,Currency,State,Balance``
- One export can contain SEVERAL currencies mixed together (Revolut's multi-currency
  wallet), typically grouped into per-currency blocks. Unlike every other parser here,
  this one does NOT filter to a single currency -- it parses every row and tags each
  with its own currency (ParsedRow.currency). The import service handles routing each
  currency's rows to the right Alfred account (see ImportService.preview_grouped).
- Only ``State == "COMPLETED"`` rows are kept; PENDING/REVERTED rows never actually
  moved money (empty Completed Date and Balance confirm this).
- ``Type`` classifies the row structurally, which lets us set the transaction type
  directly instead of relying on the sign-based expense/income default:
    - "Exchange": the user's own money moving between their own Revolut currency
      balances -- always a transfer. (No counterpart account is set: reliably pairing
      the two legs of one conversion isn't attempted here -- see the import plan notes.)
    - "Topup": money entering from an external card not tracked as an Alfred
      account -- treated as a transfer (not income) so it doesn't inflate earnings.
    - "Transfer" to "Revolut Bank UAB ...": Revolut's own entity name, most likely an
      internal sweep of a foreign-currency e-money balance into the core account --
      treated as a transfer, but flagged for review since this is a guess.
    - "Transfer to <person>": a real payment to someone else -- left as a normal
      expense (the default sign-based inference already gets this right).
    - "Card Payment" / "ATM" / "Rev Payment" / "Card Refund": ordinary
      expense/income, sign-based inference already correct.
- ``Completed Date`` is used as the posting date (when it actually affected the
  balance); ``Started Date`` as the value date. The raw ``Completed Date`` string
  (with its time-of-day) is also kept on ``ParsedRow.posted_at``: the dedup hash
  needs it because a same-day, same-amount, same-description pair can otherwise
  collide on ``balance_after`` too, e.g. two top-ups on the same day that both left
  the balance at the same figure because an Exchange in between spent it back down
  to zero.
- The ``Fee`` column is informational only in the observed export (always 0.00);
  ``Amount`` already reflects the net effect on the balance, so Fee is not applied.
"""
from __future__ import annotations

import csv
import io
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from app.shared.statement import ParsedRow, ParsedStatement, decode

_PROVIDER = "revolut"
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


def _classify(row_type: str, description: str) -> tuple[str | None, str | None]:
    if row_type == "Exchange":
        return "transfer", None
    if row_type == "Topup":
        return "transfer", None
    if row_type == "Transfer" and _REVOLUT_ENTITY_HINT in description:
        return "transfer", "uncertain_transfer"
    return None, None


class RevolutStatementParser:

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
            if (record.get("State") or "").strip().upper() != "COMPLETED":
                continue

            completed_raw = (record.get("Completed Date") or "").strip()
            completed = _parse_datetime(completed_raw)
            started = _parse_datetime(record.get("Started Date") or "")
            amount = _parse_amount(record.get("Amount") or "")
            balance = _parse_amount(record.get("Balance") or "")
            currency = (record.get("Currency") or "").strip().upper()
            if completed is None or amount is None or not currency:
                continue

            row_type = (record.get("Type") or "").strip()
            description = (record.get("Description") or "").strip()
            suggested_type, flag_reason = _classify(row_type, description)

            rows.append(
                ParsedRow(
                    date_posted=completed,
                    date_value=started or completed,
                    raw_description=description,
                    amount=amount,
                    currency=currency,
                    balance_after=balance,
                    suggested_type=suggested_type,
                    flag_reason=flag_reason,
                    posted_at=completed_raw or None,
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
