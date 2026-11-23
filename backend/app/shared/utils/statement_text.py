"""Reading bank statement exports: file decoding and European-format amounts."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation


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
