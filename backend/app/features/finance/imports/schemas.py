from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

from app.features.finance.transactions.schemas import TransactionType

RuleMode = Literal["auto", "suggest"]
SuggestionSource = Literal["rule_auto", "rule_suggest", "knn", "llm"]
RowStatus = Literal["new", "duplicate"]
ReviewReason = Literal[
    "uncategorized", "rule_suggested", "ai_suggested", "redated_installment", "uncertain_transfer"
]


class ImportRuleCreate(BaseModel):
    pattern: str
    amount: Decimal | None = None
    mode: RuleMode = "auto"
    description: str | None = None
    merchant: str | None = None
    category_id: int | None = None
    transfer_account_id: int | None = None


class ImportRuleRead(ImportRuleCreate):
    id: int
    created_at: datetime

    model_config = {"from_attributes": True}


class ImportPreviewRow(BaseModel):
    date_posted: date
    date_value: date
    bank_description: str
    amount: Decimal
    balance_after: Decimal | None = None
    type: TransactionType
    status: RowStatus
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
