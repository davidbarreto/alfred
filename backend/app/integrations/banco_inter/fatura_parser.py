"""Parser for Banco Inter (BR) credit-card invoice PDFs (fatura).

Format notes:
- Text-based PDF; transactions live under a ``Despesas da fatura`` section,
  grouped per card (``CARTÃO 2306****6588``)
- Row shape: ``12 de out. 2025 RI HAPPY BRINQUEDOS LO (Parcela 08 de 10) - R$ 57,04``;
  the bill payment carries a ``+``: ``15 de mai. 2026 PAGTO DEBITO AUTOMATICO - + R$ 388,41``
- Charges are normalized to negative amounts, the payment to a positive inflow,
  tagged ``suggested_type="transfer"`` -- paying off your own card is never
  income, it's your own money clearing debt already counted as spend when
  each underlying charge posted. Link its counterpart_account_id (via a rule
  matching the description) to whichever tracked account actually funds the
  auto-debit so it nets to zero instead of counting as spend a second time.
- Installment rows print the ORIGINAL purchase date; rows dated before the
  previous billing month are re-dated to the 1st of the fatura (vencimento)
  month so monthly spending reflects cash flow. The printed date is kept as
  ``date_value`` (still part of the dedup hash) and the row is flagged for
  review on import
- Some exports are prefixed with null bytes; parsing starts at the ``%PDF`` marker
- No running balance; dedup relies on the occurrence-counter fallback

Installment ("Parcela M de N") purchases:
- Same self-contained-row model as Nubank (see NubankCardStatementParser):
  every row IS the real, already-amortized charge, so N (total installments)
  is read directly off a single row's ``(Parcela M de N)`` suffix instead of
  a schedule table. There's no bank-issued plan reference either, so the
  merchant text with the suffix stripped doubles as plan_ref, and
  original_amount stays None -- the import service skips the lump-sum
  match/supersede step entirely in that case. The row's own raw_description
  keeps the ``(Parcela M de N)`` suffix; only the plan signal's description
  is stripped.
"""
from __future__ import annotations

import io
import logging
import re
from datetime import date

from app.shared.statement import ParsedInstallmentPlanSignal, ParsedRow, ParsedStatement
from app.shared.statement import parse_european_amount as parse_amount

logger = logging.getLogger(__name__)

_PROVIDER = "banco_inter_card"

_MONTHS = {
    "jan": 1, "fev": 2, "mar": 3, "abr": 4, "mai": 5, "jun": 6,
    "jul": 7, "ago": 8, "set": 9, "out": 10, "nov": 11, "dez": 12,
}
_ROW_RE = re.compile(
    r"^(\d{1,2}) de ([a-zç]{3})\.? (?:de )?(\d{4})\s+(.+?)\s*-\s*(\+\s*)?R\$\s*([\d.,]+)\s*$"
)
_CARD_RE = re.compile(r"CART.O\s+(\d{4}\*+\d{4})")
_VENCIMENTO_RE = re.compile(r"Data de Vencimento\s*\n?\s*(\d{2})/(\d{2})/(\d{4})")
_INSTALLMENT_RE = re.compile(r"^(.*?)\s*\(Parcela\s+(\d+)\s+de\s+(\d+)\)\s*$", re.IGNORECASE)


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
        logger.warning("Inter fatura PDF extraction failed: error=%s", exc)
        return None


def _parse_text(text: str) -> list[ParsedRow]:
    rows: list[ParsedRow] = []
    in_expenses = False
    for line in text.splitlines():
        line = line.strip()
        if "Despesas da fatura" in line:
            in_expenses = True
            continue
        if not in_expenses:
            continue
        match = _ROW_RE.match(line)
        if match is None:
            continue
        day, month_name, year, description, plus, raw_amount = match.groups()
        month = _MONTHS.get(month_name.lower())
        amount = parse_amount(raw_amount)
        if month is None or amount is None:
            continue
        row_date = date(int(year), month, int(day))
        rows.append(
            ParsedRow(
                date_posted=row_date,
                date_value=row_date,
                raw_description=description.strip(),
                amount=amount if plus else -amount,
                currency="BRL",
                balance_after=None,
                suggested_type="transfer" if plus else None,
            )
        )
    return rows


def _redate_old_rows(rows: list[ParsedRow], vencimento: date | None) -> None:
    """Move rows older than the previous billing month to the 1st of the fatura month.

    Inter prints installments with the original purchase date; without this,
    every parcela of a purchase would stack on that single past date.
    """
    if vencimento is None:
        return
    if vencimento.month == 1:
        cutoff = date(vencimento.year - 1, 12, 1)
    else:
        cutoff = date(vencimento.year, vencimento.month - 1, 1)
    fatura_month_start = vencimento.replace(day=1)
    for row in rows:
        if row.date_posted < cutoff:
            row.date_posted = fatura_month_start
            row.flag_reason = "redated_installment"


def _installment_plan_signals(rows: list[ParsedRow]) -> list[ParsedInstallmentPlanSignal]:
    """One signal per distinct merchant text carrying a "(Parcela M de N)" suffix in
    this statement -- deduplicated since the same ongoing plan can post more than one
    installment within a single export. N is read straight off whichever row is seen
    first; every row sharing this plan is expected to report the same N."""
    totals: dict[str, int] = {}
    for row in rows:
        match = _INSTALLMENT_RE.match(row.raw_description)
        if match is None:
            continue
        base_description = match.group(1).strip()
        total_installments = int(match.group(3))
        totals.setdefault(base_description, total_installments)
    return [
        ParsedInstallmentPlanSignal(
            plan_ref=description,
            description=description,
            original_amount=None,
            total_installments=total,
        )
        for description, total in totals.items()
    ]


class BancoInterFaturaParser:

    @property
    def provider(self) -> str:
        return _PROVIDER

    def can_parse(self, filename: str, content: bytes) -> bool:
        if not filename.lower().endswith(".pdf") or b"%PDF" not in content[:1_000_000]:
            return False
        text = _pdf_text(content)
        return text is not None and "Despesas da fatura" in text

    def parse(self, content: bytes) -> ParsedStatement:
        text = _pdf_text(content) or ""
        rows = _parse_text(text)

        vencimento: date | None = None
        match = _VENCIMENTO_RE.search(text)
        if match:
            day, month, year = (int(g) for g in match.groups())
            vencimento = date(year, month, day)
        _redate_old_rows(rows, vencimento)

        card_match = _CARD_RE.search(text)
        return ParsedStatement(
            provider=_PROVIDER,
            account_number=card_match.group(1) if card_match else None,
            currency="BRL",
            period_start=None,
            period_end=vencimento,
            closing_balance=None,
            rows=rows,
            installment_plans_opened=_installment_plan_signals(rows),
        )
