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
    installment_juros: Decimal | None = None
    installment_duty: Decimal | None = None
    """Interest / stamp duty for this specific installment, when the parser can read
    them directly from a per-installment schedule (e.g. ActivoBank's own Capital/Juros/
    IS breakdown). None for every other parser and for any non-installment row."""
    note: str | None = None
    """Pre-filled note for the transaction, editable by the user at review time (see
    ImportPreviewRow.note). Used by ActivoBank's Capital-installment rows to record the
    bank's own installment reference (e.g. "Installment 00019/3") -- the row's own
    plan/position within its plan, which isn't otherwise recoverable once imported since
    the total installment count for a plan can't always be inferred from a single row."""


@dataclass
class ParsedInstallmentPlanSignal:
    """An installment ("fracionado") plan present in a statement's own installment
    schedule table -- not a transaction itself, but a signal for the import service to
    get-or-create the plan (see ImportService.ensure_plan_for_ref) and, if its original
    lump-sum purchase transaction hasn't been matched yet, try to find and supersede it.

    Derived entirely from the schedule table, which always shows a plan's full
    remaining tail in one statement (confirmed against real exports: a plan already a
    few months in still lists every remaining installment through completion, not just
    the next one or two) -- so this resolves the same way whether the statement covers
    the plan's opening month or one much later, with no dependency on catching the
    one-time "Fracionada xN" purchase line in a different section of the same PDF.
    """

    plan_ref: str
    """The bank's own plan reference (e.g. "00024") -- the row's own Plano prefix.
    Used as the auto-created ImportRule's match pattern instead of the bare
    description, since the description alone matches both future installment rows AND
    the original full-price purchase, which would wrongly tag the original as a
    captured installment if it's imported (e.g. via CSV) after this plan exists.

    Providers with no bank-issued reference (e.g. Nubank's "Parcela M/N" card CSV)
    use the normalized merchant description itself as plan_ref instead -- the same
    identity the manual "New plan" form already relies on, with the same known
    limitation: two genuinely separate plans for the same merchant text collide."""
    description: str
    original_amount: Decimal | None
    """The full, unamortized purchase price ("Valor Transação"), constant across every
    row sharing this plan_ref -- used to match a plan's original lump-sum transaction
    by (account, description, amount) in any future import, regardless of order. None
    for a provider whose installment rows never had a separate one-time original
    purchase to begin with (e.g. Nubank -- each "Parcela M/N" row already is the real,
    already-amortized charge) -- the import service skips the match/placeholder step
    entirely in that case, see ImportService._apply_one_installment_plan_action."""
    total_installments: int
    """max(position) across every row sharing this plan_ref within this one statement
    -- the schedule table's remaining-tail guarantee (see class docstring) makes this
    reliable however far into the plan's life this particular statement is. For a
    provider without a schedule table, read directly off a single row instead (e.g.
    Nubank's own "M/N" suffix)."""


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
    installment_plans_opened: list[ParsedInstallmentPlanSignal] = field(default_factory=list)


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
