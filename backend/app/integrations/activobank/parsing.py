"""Date parsing helper shared by the ActivoBank account and card parsers."""
from __future__ import annotations

from datetime import date, datetime


def parse_date(raw: str) -> date | None:
    try:
        return datetime.strptime(raw.strip(), "%d/%m/%Y").date()
    except ValueError:
        return None
