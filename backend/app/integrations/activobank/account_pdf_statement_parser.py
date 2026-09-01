"""Parser for ActivoBank (PT) "Extrato Combinado" PDFs, current/checking account only.

Manual-select backup for the CSV export (`ActivoBankStatementParser`), which stays the
primary/routine import path -- descriptions in this PDF are identical to the CSV's, so
the import service's existing dedup hash (date_posted, date_value, description, amount,
balance_after) already prevents double-importing a period covered by both. This parser
is never auto-detected (see `can_parse`); the user picks it explicitly from the import
UI's provider dropdown when they want to import (or backfill) from the PDF instead.

Format notes:
- Text-based PDF; each statement bundles several account sections (``CONTA SIMPLES``
  the checking account, ``CONTA POUPEUP`` a savings pocket, plus a card balance summary
  with no movements) -- only the ``CONTA SIMPLES`` section is parsed.
- Row shape once assembled: ``6.02 6.02 COMPRA 8597 MOLETE PADARIAS SAO MAM CONTACTLESS
  0.84 2 692.70`` (Data Lanc., Data Valor, description, one amount, running balance).
  Dates carry no year (``M.DD``); the year is read off the section's own
  ``EXTRATO DE yyyy/mm/dd A yyyy/mm/dd`` period line.
- DEBITO and CREDITO are two separate columns in the rendered PDF, but pypdf's text
  extraction linearizes both into one whitespace-joined amount with no way to tell which
  column it came from -- so the sign is derived from the running-balance delta instead
  (``balance_after - previous_balance``), which reconciles exactly against every
  statement's own printed ``SALDO FINAL`` (verified against real exports).
- pypdf splits the transaction row that happens to fall right after a page break: the
  two dates land alone on their own line, and the rest of the row (description, amount,
  balance) lands on the very next content line, after the header/footer boilerplate for
  the new page. ``_iter_row_lines`` re-joins these before the row regex ever sees them.
- ``A TRANSPORTAR`` / ``TRANSPORTE`` lines are page-continuation running-total markers,
  not real movements -- skipped like ``SALDO INICIAL``/``SALDO FINAL``.
"""
from __future__ import annotations

import io
import logging
import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation

from app.shared.statement import ParsedRow, ParsedStatement

logger = logging.getLogger(__name__)

_PROVIDER = "activobank_account_pdf"
_ANCHOR = "EXTRATO COMBINADO"
_SECTION_START = "CONTA SIMPLES N."
_SECTION_END = "SALDO FINAL"

_AMOUNT = r"\d{1,3}(?: \d{3})*\.\d{2}"
_BOILERPLATE_PREFIXES = ("Banco ActivoBank", "Capital Social", "DATA", "LANC.", "VALOR DESCRITIVO")
_ROW_RE = re.compile(rf"^(\d{{1,2}}\.\d{{2}}) (\d{{1,2}}\.\d{{2}}) (.+?) ({_AMOUNT}) ({_AMOUNT})-?$")
_TAIL_RE = re.compile(rf"^(.+?) ({_AMOUNT}) ({_AMOUNT})-?$")
_BARE_DATES_RE = re.compile(r"^(\d{1,2}\.\d{2}) (\d{1,2}\.\d{2})$")
_SALDO_INICIAL_RE = re.compile(rf"^SALDO INICIAL ({_AMOUNT})-?")
_PERIOD_RE = re.compile(r"EXTRATO DE (\d{4})/(\d{2})/(\d{2}) A (\d{4})/(\d{2})/(\d{2})")
_ACCOUNT_RE = re.compile(rf"^{re.escape(_SECTION_START)}\s*(\d+)?")
_ACCOUNT_CONTINUATION_RE = re.compile(r"^(\d+) MOEDA: EUR")


def _pdf_text(content: bytes) -> str | None:
    from pypdf import PdfReader

    marker = content.find(b"%PDF")
    if marker < 0:
        return None
    try:
        reader = PdfReader(io.BytesIO(content[marker:]))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception as exc:
        logger.warning("ActivoBank account PDF extraction failed: error=%s", exc)
        return None


def _parse_amount(raw: str) -> Decimal | None:
    try:
        return Decimal(raw.replace(" ", ""))
    except InvalidOperation:
        return None


def _resolve_date(month_day: str, period_start: date | None, period_end: date | None) -> date | None:
    parts = month_day.split(".")
    if len(parts) != 2:
        return None
    try:
        month, day = int(parts[0]), int(parts[1])
    except ValueError:
        return None
    if period_end is not None and month == period_end.month:
        year = period_end.year
    elif period_start is not None:
        year = period_start.year
    elif period_end is not None:
        year = period_end.year
    else:
        return None
    try:
        return date(year, month, day)
    except ValueError:
        return None


@dataclass
class _Section:
    account_number: str | None
    period_start: date | None
    period_end: date | None
    lines: list[str]


def _extract_section(text: str) -> _Section | None:
    lines = [line.strip() for line in text.splitlines()]
    start = next((i for i, line in enumerate(lines) if line.startswith(_SECTION_START)), None)
    if start is None:
        return None
    end = next((i for i in range(start, len(lines)) if lines[i].startswith(_SECTION_END)), None)
    if end is None:
        return None

    account_match = _ACCOUNT_RE.match(lines[start])
    account_number = account_match.group(1) if account_match else None
    if account_number is None and start + 1 < len(lines):
        continuation = _ACCOUNT_CONTINUATION_RE.match(lines[start + 1])
        if continuation:
            account_number = continuation.group(1)

    period_start: date | None = None
    period_end: date | None = None
    period_match = next((_PERIOD_RE.search(line) for line in lines[start:end] if _PERIOD_RE.search(line)), None)
    if period_match:
        sy, sm, sd, ey, em, ed = (int(g) for g in period_match.groups())
        period_start = date(sy, sm, sd)
        period_end = date(ey, em, ed)

    return _Section(account_number=account_number, period_start=period_start, period_end=period_end, lines=lines[start : end + 1])


def _iter_row_lines(lines: list[str]) -> tuple[list[str], Decimal | None]:
    """Reassemble page-break-split rows; returns (row_lines, opening_balance)."""
    row_lines: list[str] = []
    pending_dates: tuple[str, str] | None = None
    opening_balance: Decimal | None = None

    for line in lines:
        if not line:
            continue
        if any(line.startswith(prefix) for prefix in _BOILERPLATE_PREFIXES):
            continue
        if "EXT. N." in line and "PAG:" in line:
            continue
        if line.startswith(_SECTION_START) or _ACCOUNT_CONTINUATION_RE.match(line):
            continue
        if line.startswith("EXTRATO DE"):
            continue

        saldo_match = _SALDO_INICIAL_RE.match(line)
        if saldo_match:
            opening_balance = _parse_amount(saldo_match.group(1))
            continue
        if line.startswith("A TRANSPORTAR") or line.startswith("TRANSPORTE"):
            continue
        if line.startswith(_SECTION_END) or line.startswith("SALDO DISPONIVEL"):
            continue

        bare_dates_match = _BARE_DATES_RE.match(line)
        if bare_dates_match:
            pending_dates = bare_dates_match.groups()
            continue

        if _ROW_RE.match(line):
            row_lines.append(line)
            pending_dates = None
            continue

        if pending_dates is not None and _TAIL_RE.match(line):
            row_lines.append(f"{pending_dates[0]} {pending_dates[1]} {line}")
            pending_dates = None
            continue

        pending_dates = None

    return row_lines, opening_balance


def _parse_rows(section: _Section) -> list[ParsedRow]:
    row_lines, balance = _iter_row_lines(section.lines)
    if balance is None:
        return []

    rows: list[ParsedRow] = []
    for line in row_lines:
        match = _ROW_RE.match(line)
        if match is None:
            continue
        posted_raw, value_raw, description, amount_raw, balance_raw = match.groups()

        date_posted = _resolve_date(posted_raw, section.period_start, section.period_end)
        date_value = _resolve_date(value_raw, section.period_start, section.period_end)
        balance_after = _parse_amount(balance_raw)
        if date_posted is None or balance_after is None:
            continue

        signed_amount = balance_after - balance
        balance = balance_after

        rows.append(
            ParsedRow(
                date_posted=date_posted,
                date_value=date_value or date_posted,
                raw_description=description.strip(),
                amount=signed_amount,
                currency="EUR",
                balance_after=balance_after,
            )
        )

    return rows


class ActivoBankAccountPdfStatementParser:

    @property
    def provider(self) -> str:
        return _PROVIDER

    def can_parse(self, filename: str, content: bytes) -> bool:
        # Never auto-detected -- backup path for the CSV export, selected manually from
        # the import UI's provider dropdown (see module docstring).
        return False

    def parse(self, content: bytes) -> ParsedStatement:
        text = _pdf_text(content) or ""
        section = _extract_section(text)
        if section is None:
            return ParsedStatement(
                provider=_PROVIDER,
                account_number=None,
                currency="EUR",
                period_start=None,
                period_end=None,
                closing_balance=None,
            )

        rows = _parse_rows(section)
        return ParsedStatement(
            provider=_PROVIDER,
            account_number=section.account_number,
            currency="EUR",
            period_start=section.period_start,
            period_end=section.period_end,
            closing_balance=rows[-1].balance_after if rows else None,
            rows=rows,
        )
