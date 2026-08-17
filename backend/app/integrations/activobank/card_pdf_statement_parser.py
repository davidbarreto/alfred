"""Parser for ActivoBank (PT) credit-card statement PDFs ("Extrato Visa Classic").

Format notes (differs from the account-history and card-CSV exports):
- Text-based PDF; movements live under a ``DETALHE DOS MOVIMENTOS`` section
- Row shape: ``2026/07/06 2026/07/07 COMPRA 4681 KEF FOOD MARSEILLE 1 54.80``
  (date posted, date value, description, amount) -- network markers (``VIS``/
  ``MB``), FX sub-lines, and "Fracionada xN" continuation lines sit on their
  own following line and are simply not matched by the row pattern

Two provider registrations, same parsing code (see ``registry.py``):
- ``activobank_card_pdf`` (``installments_only=True``, the default): only
  emits Capital-installment rows and installment-plan-open signals. Ordinary
  movements (regular COMPRA, fees, payments, transfers) are NOT emitted --
  the user's daily CSV import already covers those, and re-importing them
  from the PDF risks silent duplicates since card-format dedup only matches
  by (date, description, amount) content-key, with no guarantee the CSV and
  PDF exports format descriptions identically.
- ``activobank_card_pdf_full`` (``installments_only=False``): emits every
  movement too -- for the one-off historical backfill of months with no CSV
  import at all. Never auto-detected (``can_parse`` always False); must be
  explicitly selected.

Installment ("fracionado") purchases -- the split-payment plan:
- A fracionado purchase posts its FULL price once in ``DETALHE DOS
  MOVIMENTOS``, flagged by a "Fracionada xN" line right below it. That full
  amount is never actually charged in one go -- it's replaced by the real
  monthly installment. That row is skipped entirely (in both modes), and
  instead recorded as a ``ParsedInstallmentPlanSignal`` (description, amount,
  date, total installments) for the import service to create/track a plan
  and supersede whatever transaction that full price already became
  (typically via the daily CSV import).
- The real monthly charge is Capital + Juros + Imposto do Selo (together
  called "Mensalidade") from ``DETALHE DE TRANSAÇÕES COM PAGAMENTO
  FRACIONADO``. That section is a full projection of ALL remaining
  installments as of this statement (it lists future months too), so only
  the row(s) whose "Data Movimento" falls inside the current statement
  period are kept -- otherwise every future month's statement would re-list
  (and we'd re-import) the same installment again.
- Only the Capital column becomes the row's amount; Juros and Imposto do
  Selo are carried separately as ``installment_juros``/``installment_duty``
  (informational -- the import service accumulates them on the plan, they
  are never inserted as their own transaction here). In ``full`` mode, the
  movements-sourced ``JUROS PAG FRACIONADO``/``IMPOSTO DO SELO`` lines are
  ALSO emitted as ordinary transactions (real fees/interest charges); in
  ``installments_only`` mode they're skipped like every other ordinary
  movement, on the assumption the daily CSV import already has them.

Other rows (full mode only):
- ``PAGAMENTO CARTAO...`` rows (with or without a leading ``>``) are money
  paid into the card, tagged ``suggested_type="transfer"`` and positive --
  paying off your own card is never income, it's your own money clearing
  debt already counted as spend when each underlying charge posted
- ``TRANSFERENCIA CARTAO CREDITO <ref>`` rows send money out of the card to
  another account; also tagged ``suggested_type="transfer"`` but negative
- ``TRANSAÇÕES EM MOEDA DIFERENTE DE EUR`` is a redundant FX summary of
  rows already listed in movements -- skipped in both modes
- No running balance; dedup relies on the occurrence-counter fallback
"""
from __future__ import annotations

import io
import logging
import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation

from app.shared.statement import ParsedInstallmentPlanSignal, ParsedRow, ParsedStatement

logger = logging.getLogger(__name__)

_ANCHOR = "EXTRATO VISA CLASSIC ACTIVOBANK"
_INSTALLMENTS_START = "DETALHE DE TRANSAÇÕES COM PAGAMENTO FRACIONADO"
_MOVEMENTS_START = "DETALHE DOS MOVIMENTOS"
_MOVEMENTS_END = "TRANSAÇÕES EM MOEDA DIFERENTE"

_ROW_RE = re.compile(
    r"^(\d{4}/\d{2}/\d{2}) (\d{4}/\d{2}/\d{2}) (.+?) (\d{1,3}(?: \d{3})*\.\d{2})$"
)
_INSTALLMENT_LINE_RE = re.compile(r"^(\d{4}/\d{2}/\d{2})\s+(.+)$")
_CARD_RE = re.compile(r"Conta Cart.o:\s*([\d-]+)", re.IGNORECASE)
_PERIOD_RE = re.compile(r"Extrato de:\s*(\d{4})/(\d{2})/(\d{2}) a (\d{4})/(\d{2})/(\d{2})")
_FRACIONADA_RE = re.compile(r"^Fracionada x(\d+)", re.IGNORECASE)


def _pdf_text(content: bytes) -> str | None:
    """Extract all page text; tolerates exports prefixed with null bytes."""
    from pypdf import PdfReader

    marker = content.find(b"%PDF")
    if marker < 0:
        return None
    try:
        reader = PdfReader(io.BytesIO(content[marker:]))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception as exc:
        logger.warning("ActivoBank card PDF extraction failed: error=%s", exc)
        return None


def _parse_amount(raw: str) -> Decimal | None:
    try:
        return Decimal(raw.replace(" ", ""))
    except InvalidOperation:
        return None


def _parse_date(raw: str) -> date | None:
    parts = raw.split("/")
    if len(parts) != 3:
        return None
    try:
        return date(int(parts[0]), int(parts[1]), int(parts[2]))
    except ValueError:
        return None


def _within_period(day: date, period_start: date | None, period_end: date | None) -> bool:
    if period_start is None or period_end is None:
        return False
    return period_start <= day <= period_end


def _build_movement_row(description: str, amount: Decimal, date_posted: date, date_value: date) -> ParsedRow:
    description = description.strip()
    if description.startswith(">"):
        description = description[1:].strip()
    desc_upper = description.upper()

    if desc_upper.startswith("PAGAMENTO CARTAO"):
        signed_amount = amount
        suggested_type = "transfer"
    elif desc_upper.startswith("TRANSFERENCIA CARTAO CREDITO"):
        signed_amount = -amount
        suggested_type = "transfer"
    else:
        signed_amount = -amount
        suggested_type = None

    return ParsedRow(
        date_posted=date_posted,
        date_value=date_value,
        raw_description=description,
        amount=signed_amount,
        currency="EUR",
        balance_after=None,
        suggested_type=suggested_type,
    )


@dataclass
class _ParseResult:
    rows: list[ParsedRow]
    installment_plans_opened: list[ParsedInstallmentPlanSignal]


def _parse_text(
    text: str, period_start: date | None, period_end: date | None, installments_only: bool
) -> _ParseResult:
    rows: list[ParsedRow] = []
    plans_opened: list[ParsedInstallmentPlanSignal] = []
    lines = [line.strip() for line in text.splitlines()]
    n = len(lines)
    state = "none"
    i = 0
    while i < n:
        line = lines[i]

        if _INSTALLMENTS_START in line:
            state = "installments"
            i += 1
            continue
        if _MOVEMENTS_START in line:
            state = "movements"
            i += 1
            continue
        if _MOVEMENTS_END in line:
            state = "none"
            i += 1
            continue

        if state == "installments":
            match = _INSTALLMENT_LINE_RE.match(line)
            if match is not None and i + 1 < n:
                row_date = _parse_date(match.group(1))
                description = match.group(2).strip()
                parts = lines[i + 1].split()
                if row_date is not None and len(parts) == 8 and _within_period(
                    row_date, period_start, period_end
                ):
                    capital = _parse_amount(parts[4])
                    juros = _parse_amount(parts[5])
                    imposto_selo = _parse_amount(parts[6])
                    plano = parts[3]
                    if capital is not None:
                        rows.append(
                            ParsedRow(
                                date_posted=row_date,
                                date_value=row_date,
                                raw_description=f"{description} ({plano})",
                                amount=-capital,
                                currency="EUR",
                                balance_after=None,
                                flag_reason="installment_capital",
                                installment_juros=juros,
                                installment_duty=imposto_selo,
                            )
                        )
                i += 2
                continue
            i += 1
            continue

        if state == "movements":
            match = _ROW_RE.match(line)
            if match is None:
                i += 1
                continue

            posted_raw, value_raw, description, amount_raw = match.groups()

            next_line = lines[i + 1] if i + 1 < n else ""
            fracionada_match = _FRACIONADA_RE.match(next_line)
            if fracionada_match is not None:
                date_posted = _parse_date(posted_raw)
                amount = _parse_amount(amount_raw)
                clean_description = description.strip()
                if clean_description.startswith(">"):
                    clean_description = clean_description[1:].strip()
                if date_posted is not None and amount is not None:
                    plans_opened.append(
                        ParsedInstallmentPlanSignal(
                            description=clean_description,
                            amount=-amount,
                            date_posted=date_posted,
                            total_installments=int(fracionada_match.group(1)),
                        )
                    )
                i += 1
                continue

            if installments_only:
                i += 1
                continue

            date_posted = _parse_date(posted_raw)
            date_value = _parse_date(value_raw)
            amount = _parse_amount(amount_raw)
            if date_posted is None or amount is None:
                i += 1
                continue

            rows.append(
                _build_movement_row(description, amount, date_posted, date_value or date_posted)
            )
            i += 1
            continue

        i += 1

    return _ParseResult(rows=rows, installment_plans_opened=plans_opened)


class ActivoBankCardPdfStatementParser:

    def __init__(self, installments_only: bool = True) -> None:
        self._installments_only = installments_only

    @property
    def provider(self) -> str:
        return "activobank_card_pdf" if self._installments_only else "activobank_card_pdf_full"

    def can_parse(self, filename: str, content: bytes) -> bool:
        if not self._installments_only:
            # "Full" backfill mode is never auto-detected -- it must be explicitly
            # selected, since it re-imports ordinary movements the daily CSV import
            # would otherwise already have.
            return False
        if not filename.lower().endswith(".pdf") or b"%PDF" not in content[:1_000_000]:
            return False
        text = _pdf_text(content)
        return text is not None and _ANCHOR in text

    def parse(self, content: bytes) -> ParsedStatement:
        text = _pdf_text(content) or ""

        period_start: date | None = None
        period_end: date | None = None
        period_match = _PERIOD_RE.search(text)
        if period_match:
            sy, sm, sd, ey, em, ed = (int(g) for g in period_match.groups())
            period_start = date(sy, sm, sd)
            period_end = date(ey, em, ed)

        result = _parse_text(text, period_start, period_end, self._installments_only)

        card_match = _CARD_RE.search(text)
        return ParsedStatement(
            provider=self.provider,
            account_number=card_match.group(1) if card_match else None,
            currency="EUR",
            period_start=period_start,
            period_end=period_end,
            closing_balance=None,
            rows=result.rows,
            installment_plans_opened=result.installment_plans_opened,
        )
