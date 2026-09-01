from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import Query
from pydantic import BaseModel, Field

from app.features.finance.transactions.schemas import TransactionType

RuleMode = Literal["auto", "suggest"]
RuleSort = Literal["recent", "precedence"]
SuggestionSource = Literal["rule_auto", "rule_suggest", "knn", "llm"]
RowStatus = Literal["new", "duplicate"]
DuplicateReason = Literal["already_imported", "repeated_in_file"]
ReviewReason = Literal[
    "uncategorized",
    "rule_suggested",
    "ai_suggested",
    "similarity_suggested",
    "redated_installment",
    "uncertain_transfer",
    "installment_capital",
]


class ImportRuleCreate(BaseModel):
    pattern: str
    amount: Decimal | None = None
    mode: RuleMode = "auto"
    description: str | None = None
    merchant: str | None = None
    category_id: int | None = None
    transfer_account_id: int | None = None
    installment_plan_id: int | None = None


class ImportRuleUpdate(BaseModel):
    pattern: str | None = None
    amount: Decimal | None = None
    mode: RuleMode | None = None
    description: str | None = None
    merchant: str | None = None
    category_id: int | None = None
    transfer_account_id: int | None = None
    installment_plan_id: int | None = None


class ImportRuleRead(ImportRuleCreate):
    id: int
    position: int
    created_at: datetime

    model_config = {"from_attributes": True}


class ImportRuleFilters:
    def __init__(
        self,
        limit: Annotated[int, Query(ge=1, le=200)] = 20,
        offset: Annotated[int, Query(ge=0)] = 0,
        pattern: Annotated[str | None, Query()] = None,
        mode: Annotated[RuleMode | None, Query()] = None,
        category_id: Annotated[int | None, Query()] = None,
        sort: Annotated[RuleSort, Query()] = "recent",
    ) -> None:
        self.limit = limit
        self.offset = offset
        self.pattern = pattern
        self.mode = mode
        self.category_id = category_id
        self.sort = sort


class ImportRuleReorderRequest(BaseModel):
    rule_ids: list[int]


class ImportBatchFilters:
    def __init__(
        self,
        limit: Annotated[int, Query(ge=1, le=200)] = 20,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> None:
        self.limit = limit
        self.offset = offset
    """The rules currently shown, in their new desired match-precedence order. Each rule
    keeps the position "slot" it already occupied -- only reassigned among each other --
    so rules outside this set are unaffected."""


class ImportPreviewRow(BaseModel):
    date_posted: date
    date_value: date
    bank_description: str
    amount: Decimal
    balance_after: Decimal | None = None
    type: TransactionType
    status: RowStatus
    duplicate_reason: DuplicateReason | None = None
    deduplication_hash: str
    description: str | None = None
    note: str | None = None
    """Pre-filled by the parser (e.g. ActivoBank's own installment reference), editable
    by the user before commit -- see ImportCommitRow.note, which carries whatever value
    the user leaves in the review form's note input."""
    merchant: str | None = None
    category_id: int | None = None
    category_name: str | None = None
    counterpart_account_id: int | None = None
    transfer_pair_key: str | None = None
    """Carries ParsedRow.transfer_pair_key through to commit so a same-event
    currency-exchange pair (see ImportService._link_transfer_pairs) can be confirmed
    -- counterpart_transaction_id set on both legs -- once both are actually inserted,
    instead of left as an unconfirmed counterpart_account_id guess."""
    suggestion_source: SuggestionSource | None = None
    confidence: float | None = None
    needs_review: bool = False
    review_reasons: list[ReviewReason] = Field(default_factory=list)
    installment_plan_id: int | None = None
    """Set by a matching ImportRule (see _apply_rules) -- links this row's eventual
    transaction to an installment plan (a real captured installment, inserted at its
    own amount). Independent of installment_juros/duty below, which only ever come
    from the ActivoBank PDF parser's own Capital-installment rows."""
    installment_juros: Decimal | None = None
    installment_duty: Decimal | None = None
    supersedes_installment_plan_id: int | None = None
    """Set when this row itself IS an open plan's original lump-sum purchase (matched
    by account+description+amount against TransactionRepository.find_open_plan_match)
    -- at commit, insert at €0.00 with a note instead of its real amount, and delete
    the plan's placeholder transaction if it had one. Mutually exclusive in practice
    with installment_plan_id (a row is either a future installment or the original
    purchase, never both)."""


class InstallmentPlanActionPreview(BaseModel):
    """An installment plan (from the ActivoBank PDF's own schedule table) touched by
    this import, shown separately from the row table since it doesn't insert a row
    itself -- it gets-or-creates a plan (+ matching rule) and, if not already tracked,
    tries to find and zero an already-imported lump-sum transaction, or falls back to
    a placeholder if none exists yet."""
    plan_ref: str
    description: str
    total_installments: int
    original_amount: Decimal | None
    """None for a provider with no separate original lump-sum purchase (e.g. Nubank) --
    see ParsedInstallmentPlanSignal.original_amount."""
    already_tracked: bool
    """True if this plan_ref already exists in the DB (from a prior import) -- commit
    is then a no-op for this action, since matching/placeholder handling only ever
    happens once, right when a plan is first created."""
    matched_transaction_id: int | None = None
    matched_transaction_summary: str | None = None


class ImportPreviewResponse(BaseModel):
    provider: str
    account_id: int
    source_file: str | None = None
    stored_file: str | None = None
    currency: str
    account_number: str | None = None
    period_start: date | None = None
    period_end: date | None = None
    closing_balance: Decimal | None = None
    rows: list[ImportPreviewRow]
    new_count: int
    duplicate_count: int
    needs_review_count: int
    installment_plan_actions: list[InstallmentPlanActionPreview] = Field(default_factory=list)


class ImportCommitRow(BaseModel):
    date_posted: date
    bank_description: str
    amount: Decimal
    type: TransactionType
    deduplication_hash: str
    balance_after: Decimal | None = None
    description: str | None = None
    merchant: str | None = None
    note: str | None = None
    category_id: int | None = None
    counterpart_account_id: int | None = None
    transfer_pair_key: str | None = None
    save_rule: bool = False
    rule_pattern: str | None = None
    rule_mode: RuleMode = "auto"
    rule_match_amount: bool = False
    force: bool = False
    """User confirmed this row (flagged as a likely duplicate at preview time) is
    genuinely a new transaction and should be imported despite the flag."""
    installment_plan_id: int | None = None
    installment_juros: Decimal | None = None
    installment_duty: Decimal | None = None
    supersedes_installment_plan_id: int | None = None


class InstallmentPlanActionCommit(BaseModel):
    plan_ref: str
    description: str
    total_installments: int
    original_amount: Decimal | None = None
    already_tracked: bool = False
    """Defaults False since the portal only ever sends actionable (not-yet-tracked)
    actions -- an already-tracked plan needs no action at commit time, so its checkbox
    and hidden fields aren't rendered at all (see _finance_import_review.html)."""
    matched_transaction_id: int | None = None


class ImportCommitRequest(BaseModel):
    account_id: int
    provider: str
    source_file: str | None = None
    stored_file: str | None = None
    currency: str = "EUR"
    period_start: date | None = None
    period_end: date | None = None
    closing_balance: Decimal | None = None
    rows: list[ImportCommitRow]
    installment_plan_actions: list[InstallmentPlanActionCommit] = Field(default_factory=list)


class ImportCommitResponse(BaseModel):
    batch_id: int
    inserted: int
    skipped_duplicates: int
    rules_created: int


# --- Multi-currency (grouped) import: Revolut today, any future multi-wallet bank later.
# Kept fully separate from the single-account flow above -- ImportPreviewRow/ImportRuleRead
# are reused, but the account is resolved per currency instead of once for the whole file.

class CurrencyCandidateAccount(BaseModel):
    id: int
    name: str


class CurrencyDetection(BaseModel):
    currency: str
    row_count: int
    auto_account_id: int | None = None
    """Pre-filled only when exactly one existing account has this currency."""
    candidate_accounts: list[CurrencyCandidateAccount] = Field(default_factory=list)
    """Every account with this currency, for the picker. Empty means none exist yet --
    the user must create one before this currency can be imported."""


class DetectCurrenciesResponse(BaseModel):
    provider: str
    currencies: list[CurrencyDetection]


class ImportCurrencyGroup(BaseModel):
    currency: str
    account_id: int
    account_name: str
    period_start: date | None = None
    period_end: date | None = None
    closing_balance: Decimal | None = None
    rows: list[ImportPreviewRow]
    new_count: int
    duplicate_count: int
    needs_review_count: int


class ImportPreviewGroupedResponse(BaseModel):
    provider: str
    source_file: str | None = None
    stored_file: str | None = None
    groups: list[ImportCurrencyGroup]
    new_count: int
    duplicate_count: int
    needs_review_count: int


class ImportCommitGroupedRow(ImportCommitRow):
    currency: str


class ImportCommitGroupedRequest(BaseModel):
    provider: str
    source_file: str | None = None
    stored_file: str | None = None
    account_map: dict[str, int]
    """currency -> target account_id, covering every currency present in rows."""
    rows: list[ImportCommitGroupedRow]


class ImportCommitBatchResult(BaseModel):
    batch_id: int
    currency: str
    account_id: int
    inserted: int
    skipped_duplicates: int


class ImportCommitGroupedResponse(BaseModel):
    batches: list[ImportCommitBatchResult]
    total_inserted: int
    total_skipped_duplicates: int
    rules_created: int


class ImportBatchRead(BaseModel):
    id: int
    account_id: int
    provider: str
    source_file: str | None = None
    stored_file: str | None = None
    period_start: date | None = None
    period_end: date | None = None
    closing_balance: Decimal | None = None
    inserted_count: int
    duplicate_count: int
    created_at: datetime

    model_config = {"from_attributes": True}
