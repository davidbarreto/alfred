from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Protocol, runtime_checkable


def decode(content: bytes) -> str:
    """Decode a statement export, tolerating UTF-8 (with BOM) and Windows-1252."""
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    return content.decode("cp1252", errors="replace")


def parse_european_amount(raw: str) -> Decimal | None:
    """Parse ``-1 234,56`` / ``1.234,56`` / ``- 1.237,51`` style amounts."""
    cleaned = raw.strip().replace("\xa0", "").replace(" ", "").replace(".", "").replace(",", ".")
    if not cleaned:
        return None
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return None


@dataclass
class ParsedRow:
    """A single normalized statement line, provider-agnostic."""

    date_posted: date
    date_value: date
    raw_description: str
    amount: Decimal
    currency: str
    """Set by the parser per-row. Almost always identical to ParsedStatement.currency for a
    single-currency export; the one exception is a multi-currency wallet (Revolut) where a
    single file mixes several currencies and each row carries its own."""
    balance_after: Decimal | None = None
    suggested_type: str | None = None
    """Overrides the default sign-based expense/income inference, e.g. "transfer" for a
    structurally-known transfer (a bank's own Type column), when the parser can be certain."""
    flag_reason: str | None = None
    """Set when the parser wants this row flagged for review regardless of category
    confidence (e.g. "redated_installment", "uncertain_transfer"). Surfaced to the user
    as a ReviewReason by the import service."""
    posted_at: str | None = None
    """Raw source timestamp string (date + time), for providers whose export has
    intra-day precision (Revolut, Wise) even though date_posted/date_value are
    date-only. Used only as an extra dedup-hash disambiguator: two same-day,
    same-amount, same-description rows can otherwise collide, e.g. a running balance
    that coincidentally returns to the same value between them."""
    transfer_pair_key: str | None = None
    """Set only when the parser can be certain two rows are the opposing legs of the
    same self-transfer/currency-conversion event (e.g. Wise's own transaction ID for a
    split conversion row). The grouped-import service uses this to auto-link both legs'
    counterpart_account_id once each leg's Alfred account is resolved, without needing
    any FX conversion -- we're only pairing rows, never converting amounts."""


@dataclass
class ParsedStatement:
    """Normalized output of a bank statement parser."""

    provider: str
    account_number: str | None
    currency: str
    period_start: date | None
    period_end: date | None
    closing_balance: Decimal | None
    rows: list[ParsedRow] = field(default_factory=list)


@runtime_checkable
class StatementParser(Protocol):
    """
    Interface for parsing a bank statement export into normalized rows.

    The import service speaks only this interface, so adding a new bank
    requires only a new parser module registered in the parser registry.

    Parsers are pure: bytes in, ParsedStatement out. Deduplication,
    rule application, and persistence are handled downstream and must
    not leak into parser implementations.
    """

    @property
    def provider(self) -> str: ...

    def can_parse(self, filename: str, content: bytes) -> bool: ...

    def parse(self, content: bytes) -> ParsedStatement: ...
