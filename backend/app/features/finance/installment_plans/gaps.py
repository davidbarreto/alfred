"""Pure gap detection for installment plans -- no DB or IO.

A PDF-imported installment carries its position in its description
(``COMPRA 4681 SHOP (00014/3)``), so a plan's captured transactions can be laid
over the slots 1..total_installments to show which ones are missing. Installments
are monthly and each belongs to one statement month, so a missing slot's expected
month tells the user which statement to import.
"""
import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.features.finance.installment_plans.schemas import InstallmentSlot

_POSITION_RE = re.compile(r"\((\d+)/(\d+)\)\s*$")


@dataclass
class CapturedInstallment:
    position: int
    transaction_id: int
    date: date
    amount: Decimal


def parse_position(description: str | None) -> int | None:
    """Installment position from a trailing ``(<plan_ref>/<position>)``, else None."""
    if not description:
        return None
    match = _POSITION_RE.search(description)
    return int(match.group(2)) if match else None


def _month_index(day: date) -> int:
    return day.year * 12 + day.month - 1


def _format_month(index: int) -> str:
    return f"{index // 12:04d}-{index % 12 + 1:02d}"


def build_slots(
    total_installments: int, captured: list[CapturedInstallment], today: date
) -> list[InstallmentSlot]:
    """One slot per position 1..total, anchored on the captured installment nearest
    to each position (installments are one month apart). Empty when nothing captured
    carries a usable position, e.g. a manually-created plan.

    - ``captured``: the position has a transaction.
    - ``missing``: no transaction, but a later position has one -- it certainly exists.
    - ``overdue``: no transaction, after the last captured one, and its statement month
      is over -- most likely just not imported yet.
    - ``upcoming``: its statement month hasn't ended.
    """
    by_position: dict[int, CapturedInstallment] = {}
    for item in captured:
        if 1 <= item.position <= total_installments:
            by_position.setdefault(item.position, item)
    if not by_position:
        return []

    last_captured = max(by_position)
    current_month = _month_index(today)
    slots: list[InstallmentSlot] = []
    for position in range(1, total_installments + 1):
        item = by_position.get(position)
        if item is not None:
            slots.append(
                InstallmentSlot(
                    position=position,
                    status="captured",
                    expected_month=_format_month(_month_index(item.date)),
                    transaction_date=item.date,
                    amount=item.amount,
                    transaction_id=item.transaction_id,
                )
            )
            continue
        anchor = min(by_position.values(), key=lambda c: abs(c.position - position))
        month = _month_index(anchor.date) + position - anchor.position
        if position < last_captured:
            status = "missing"
        elif month < current_month:
            status = "overdue"
        else:
            status = "upcoming"
        slots.append(InstallmentSlot(position=position, status=status, expected_month=_format_month(month)))
    return slots
