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
    balance_after: Decimal | None = None
    flag_for_review: bool = False


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
