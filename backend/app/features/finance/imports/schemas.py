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
]


class ImportRuleCreate(BaseModel):
    pattern: str
    amount: Decimal | None = None
    mode: RuleMode = "auto"
    description: str | None = None
    merchant: str | None = None
    category_id: int | None = None
    transfer_account_id: int | None = None


class ImportRuleUpdate(BaseModel):
    pattern: str | None = None
    amount: Decimal | None = None
    mode: RuleMode | None = None
    description: str | None = None
    merchant: str | None = None
    category_id: int | None = None
    transfer_account_id: int | None = None


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
    merchant: str | None = None
    category_id: int | None = None
    category_name: str | None = None
    counterpart_account_id: int | None = None
    suggestion_source: SuggestionSource | None = None
    confidence: float | None = None
    needs_review: bool = False
    review_reasons: list[ReviewReason] = Field(default_factory=list)


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


class ImportCommitRow(BaseModel):
    date_posted: date
    bank_description: str
    amount: Decimal
    type: TransactionType
    deduplication_hash: str
    description: str | None = None
    merchant: str | None = None
    note: str | None = None
    category_id: int | None = None
    counterpart_account_id: int | None = None
    save_rule: bool = False
    rule_pattern: str | None = None
    rule_mode: RuleMode = "auto"
    rule_match_amount: bool = False


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
