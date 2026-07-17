"""Shared parsing helpers for ActivoBank CSV exports (account and card)."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation


def decode(content: bytes) -> str:
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    return content.decode("cp1252", errors="replace")


def parse_amount(raw: str) -> Decimal | None:
    cleaned = raw.strip().replace("\xa0", "").replace(" ", "").replace(".", "").replace(",", ".")
    if not cleaned:
        return None
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return None


def parse_date(raw: str) -> date | None:
    try:
        return datetime.strptime(raw.strip(), "%d/%m/%Y").date()
    except ValueError:
        return None
