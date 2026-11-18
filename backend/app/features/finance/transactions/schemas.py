from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Annotated, Any, Literal, Optional, TypeAlias
from fastapi import Query
from pydantic import BaseModel, Field, field_validator, model_validator

from app.features.finance import cycle
from app.shared.tags import normalize_tag_name
from app.shared.timezone import local_today

TransactionType: TypeAlias = Literal["expense", "income", "transfer"]

# Sentinel AnalyticsFilters.currency value meaning "sum amount_eur across every
# currency" instead of filtering to one native currency.
GLOBAL_CURRENCY = "GLOBAL"


def resolve_period(
    period: str | None,
    from_date: date | None,
    to_date: date | None,
    cycle_start_day: int = 1,
) -> tuple[date, date]:
    """Resolve a period keyword or explicit dates into a concrete [from, to] range."""
    if from_date and to_date:
        return from_date, to_date

    today = local_today()

    if period:
        p = period.lower().strip()
        if p in ("this month", "current month"):
            return cycle.current_cycle_range(today, cycle_start_day)
        if p in ("last month", "previous month"):
            return cycle.previous_cycle_range(today, cycle_start_day)
        if p in ("this week", "current week"):
            start = today - timedelta(days=today.weekday())
            return start, start + timedelta(days=6)
        if p in ("last week", "previous week"):
            start_of_week = today - timedelta(days=today.weekday())
            start = start_of_week - timedelta(days=7)
            return start, start_of_week - timedelta(days=1)
        if p in ("this quarter", "current quarter"):
            quarter_start_month = ((today.month - 1) // 3) * 3 + 1
            start = today.replace(month=quarter_start_month, day=1)
            if quarter_start_month + 3 > 12:
                end = date(start.year + 1, 1, 1) - timedelta(days=1)
            else:
                end = start.replace(month=quarter_start_month + 3, day=1) - timedelta(days=1)
            return start, end
        if p in ("this semester", "current semester"):
            semester_start_month = 1 if today.month <= 6 else 7
            start = today.replace(month=semester_start_month, day=1)
            if semester_start_month == 1:
                end = today.replace(month=6, day=30)
            else:
                end = today.replace(month=12, day=31)
            return start, end
        if p in ("this year", "current year"):
            return today.replace(month=1, day=1), today.replace(month=12, day=31)
        if p in ("last year", "previous year"):
            y = today.year - 1
            return date(y, 1, 1), date(y, 12, 31)
        if p == "today":
            return today, today
        if p == "yesterday":
            y = today - timedelta(days=1)
            return y, y

    # default: current month
    return cycle.current_cycle_range(today, cycle_start_day)


class TransferMatchCandidate(BaseModel):
    """A transaction offered as a possible transfer counterpart, plus the effective
    amount actually used to match it when it's an installment-plan anchor (own amount
    zeroed -- see TransactionRepository.create_placeholder_for_plan). plan_original_amount
    is set only in that case, since the row's own `amount` field is always 0.00 for an
    anchor and would otherwise look like an unrelated, misleading match to the user.
    """

    id: int
    account_id: int
    date: datetime
    amount: Decimal
    currency: str = "EUR"
    amount_eur: Decimal | None = None
    type: TransactionType
    description: str | None = None
    bank_description: str | None = None
    note: str | None = None
    merchant: str | None = None
    source: str | None = None
    plan_original_amount: Decimal | None = None

    model_config = {"from_attributes": True}


class TransactionBase(BaseModel):
    account_id: int
    date: datetime
    amount: Decimal
    currency: str = "EUR"
    type: TransactionType
    category_id: int | None = None
    description: str | None = None
    bank_description: str | None = None
    note: str | None = None
    merchant: str | None = None
    source: str | None = None
    counterpart_account_id: int | None = None
    counterpart_transaction_id: int | None = None
    """Set once this transfer is confirmed as matching a specific other transaction --
    counterpart_account_id alone can be an unconfirmed rule/user guess. Two ways this
    gets set: TransactionService.link_transfer (a user-confirmed Find Match), or an
    auto-generated mirror row (see Account.auto_mirror_transfers) -- a mirror always
    points back at the source leg that spawned it (Transaction.source == "auto_transfer"
    identifies the mirror side), and the source leg points at its mirror in return. Not
    directly user-editable when it points at/from a mirror. Spend totals and net-worth
    treat a transfer as a genuine internal move only once this is set."""
    balance_after: Decimal | None = None
    """The account's running balance immediately after this transaction, when the
    source statement reports one (e.g. ActivoBank checking, Banco Inter, Revolut).
    Not user-editable -- set only by statement imports."""
    installment_plan_id: int | None = None
    """Links this transaction to an installment plan (see finance.installment_plans),
    set by a matching ImportRule during import. Not user-editable -- not on
    TransactionUpdate, which is the public PATCH surface."""
    tags: list[str] = []
    """Free-form context labels (e.g. "Travel", "Work"), orthogonal to category_id --
    unlike category (exclusive, one per transaction), a transaction can carry several.
    Resolved get-or-create by name (see TransactionRepository._resolve_tags), same
    pattern as organizer.tasks' tags field."""


class TransactionCreate(TransactionBase):
    deduplication_hash: str | None = None
    import_batch_id: int | None = None


class TransactionUpdate(BaseModel):
    account_id: int | None = None
    date: datetime | None = None
    amount: Decimal | None = None
    currency: str | None = None
    type: TransactionType | None = None
    category_id: int | None = None
    description: str | None = None
    note: str | None = None
    merchant: str | None = None
    counterpart_account_id: int | None = None
    counterpart_transaction_id: int | None = None
    tags: list[str] | None = None


class TransactionRead(TransactionBase):
    id: int
    import_batch_id: int | None = None
    amount_eur: Decimal | None = None
    created_at: datetime

    model_config = {"from_attributes": True}

    @field_validator("tags", mode="before")
    @classmethod
    def coerce_tags(cls, v: Any) -> list[str]:
        return [item.name if hasattr(item, "name") else item for item in v]


TransactionSort: TypeAlias = Literal[
    "date_desc", "date_asc", "amount_desc", "amount_asc", "name_asc", "name_desc"
]

TransactionTagsMode: TypeAlias = Literal["all", "any", "none"]
"""How the transaction list combines its tag filter. The analytics filters
(AnalyticsFilters) take only "all" / "any"."""


class TransactionFilters:
    def __init__(
        self,
        limit: Annotated[int, Query(ge=1)] = 100,
        offset: Annotated[int, Query(ge=0)] = 0,
        type: Annotated[TransactionType | None, Query()] = None,
        category_id: Annotated[int | None, Query()] = None,
        uncategorized: Annotated[bool, Query()] = False,
        account_id: Annotated[int | None, Query()] = None,
        merchant: Annotated[str | None, Query()] = None,
        search: Annotated[str | None, Query()] = None,
        from_date: Annotated[date | None, Query()] = None,
        to_date: Annotated[date | None, Query()] = None,
        period: Annotated[str | None, Query()] = None,
        currency: Annotated[str | None, Query()] = None,
        min_amount: Annotated[Decimal | None, Query(ge=0)] = None,
        max_amount: Annotated[Decimal | None, Query(ge=0)] = None,
        installment_plan_id: Annotated[int | None, Query()] = None,
        unconfirmed_transfer: Annotated[bool, Query()] = False,
        tags: Annotated[list[str] | None, Query()] = None,
        tags_mode: Annotated[TransactionTagsMode, Query()] = "all",
        sort: Annotated[TransactionSort, Query()] = "date_desc",
    ) -> None:
        self.limit = limit
        self.offset = offset
        self.type = type
        self.category_id = category_id
        self.uncategorized = uncategorized
        self.account_id = account_id
        self.merchant = merchant
        self.tags = tags
        """Tag names to filter by -- combined per tags_mode. See
        TransactionRepository._filter_conditions."""
        self.tags_mode = tags_mode
        """"all" (default): a transaction must carry every tag in `tags` (AND) --
        e.g. ["Travel", "Barcelona"] means both. "any": carrying at least one is
        enough (OR). "none": it must carry none of them (untagged ones match)."""
        self.search = search
        """Free-text match against any of description / merchant / bank_description
        (the name given by the user and the raw name from the import file), unlike
        `merchant` which only matches the merchant column. Used by the portal's
        transaction search and the manual transfer-link search (see
        TransactionService.search_link_candidates)."""
        self.from_date = from_date
        self.to_date = to_date
        self.period = period
        self.currency = currency.upper() if currency is not None else None
        self.min_amount = min_amount
        self.max_amount = max_amount
        """Inclusive bounds on the absolute amount (sign ignored, so 50 matches both a
        -50 transfer and a 50 expense). Compared in the filtered currency, or in EUR
        when no currency is set (same basis as the filtered sum)."""
        self.installment_plan_id = installment_plan_id
        self.unconfirmed_transfer = unconfirmed_transfer
        self.sort = sort


class TransactionCurrencySum(BaseModel):
    currency: str
    total: Decimal
    transaction_count: int


class TransactionSumResponse(BaseModel):
    total: Decimal
    transaction_count: int
    currency: str
    by_currency: list[TransactionCurrencySum] = []


BULK_EDIT_MAX = 2000
"""Most transactions one bulk edit (preview or apply) handles."""

BulkRestoreField: TypeAlias = Literal["category", "merchant", "account"]


class TransactionQuery(BaseModel):
    """The transaction list's filters as a request body: the fields of TransactionFilters
    minus paging and sort, so a bulk edit hits exactly what the list shows (a test keeps
    the two in step). Read by the same _filter_conditions as the list."""

    type: TransactionType | None = None
    category_id: int | None = None
    uncategorized: bool = False
    account_id: int | None = None
    merchant: str | None = None
    search: str | None = None
    from_date: date | None = None
    to_date: date | None = None
    period: str | None = None
    currency: str | None = None
    min_amount: Decimal | None = Field(default=None, ge=0)
    max_amount: Decimal | None = Field(default=None, ge=0)
    installment_plan_id: int | None = None
    unconfirmed_transfer: bool = False
    tags: list[str] | None = None
    tags_mode: TransactionTagsMode = "all"

    @field_validator("merchant", "search", "period", "currency", mode="before")
    @classmethod
    def _blank_is_unset(cls, v: Any) -> Any:
        return None if isinstance(v, str) and not v.strip() else v

    @field_validator("currency")
    @classmethod
    def _upper_currency(cls, v: str | None) -> str | None:
        return v.upper() if v is not None else None

    def is_empty(self) -> bool:
        """True when no filter is set, i.e. the query would match every transaction."""
        return not any(
            getattr(self, name) for name in type(self).model_fields if name != "tags_mode"
        )


class TransactionBulkChanges(BaseModel):
    """What a bulk edit changes; fields left unset are not touched. Tag names are
    normalized like everywhere else (trimmed, lowercase)."""

    add_tags: list[str] = []
    remove_tags: list[str] = []
    category_id: int | None = None
    clear_category: bool = False
    account_id: int | None = None
    """Move to this account. Only allowed when every transaction is on one account."""
    merchant: str | None = None
    """Rename the merchant to this; blank means no change."""

    @field_validator("add_tags", "remove_tags")
    @classmethod
    def _normalize_tags(cls, v: list[str]) -> list[str]:
        names: list[str] = []
        for name in (normalize_tag_name(n) for n in v):
            if name and name not in names:
                names.append(name)
        return names

    @field_validator("merchant")
    @classmethod
    def _strip_merchant(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return v.strip() or None

    @model_validator(mode="after")
    def _check(self) -> "TransactionBulkChanges":
        if self.clear_category and self.category_id is not None:
            raise ValueError("Choose a category or clear it, not both")
        overlap = set(self.add_tags) & set(self.remove_tags)
        if overlap:
            raise ValueError(f"Tags both added and removed: {', '.join(sorted(overlap))}")
        if not self.kinds():
            raise ValueError("Choose at least one change")
        return self

    def kinds(self) -> list[str]:
        """Names of the changes requested, for logging and summaries."""
        kinds = []
        if self.add_tags:
            kinds.append("add_tags")
        if self.remove_tags:
            kinds.append("remove_tags")
        if self.category_id is not None or self.clear_category:
            kinds.append("category")
        if self.merchant is not None:
            kinds.append("merchant")
        if self.account_id is not None:
            kinds.append("account")
        return kinds


class TransactionBulkEditPreviewRequest(BaseModel):
    filters: TransactionQuery
    changes: TransactionBulkChanges


class TransactionBulkTagCount(BaseModel):
    name: str
    count: int
    """How many of the matched transactions this tag would be added to (or removed from)."""
    new: bool = False
    """The tag does not exist yet and would be created."""


class TransactionBulkEditPreview(BaseModel):
    """What a bulk edit would do to the transactions matching the filters, without
    changing anything. transaction_ids is what the apply call then sends, so a
    transaction imported in between is never edited unseen."""

    match_count: int
    change_count: int
    """Matched transactions at least one change applies to (the rest already match)."""
    transaction_ids: list[int]
    sample: list[TransactionRead]
    add_tags: list[TransactionBulkTagCount] = []
    remove_tags: list[TransactionBulkTagCount] = []
    category_count: int = 0
    merchant_count: int = 0
    account_count: int = 0
    linked_transfer_count: int = 0
    """Matched transactions that are one leg of a linked transfer: the other leg is never changed."""
    unlink_count: int = 0
    """Confirmed transfer links an account move breaks, as editing one leg's account does."""
    total: Decimal
    currency: str
    """Currency of total: the filtered currency, or EUR when the filters span every currency."""


class TransactionBulkEditRequest(BaseModel):
    transaction_ids: list[int] = Field(min_length=1, max_length=BULK_EDIT_MAX)
    changes: TransactionBulkChanges


class TransactionBulkEditRevertItem(BaseModel):
    """One transaction's state before a bulk edit, as much as Undo needs: the fields
    named in `restore` go back to the values here, added tags come off and removed
    ones go back on. A transfer link the edit broke is not restored."""

    id: int
    restore: list[BulkRestoreField] = []
    category_id: int | None = None
    merchant: str | None = None
    account_id: int | None = None
    added_tags: list[str] = []
    removed_tags: list[str] = []

    @model_validator(mode="after")
    def _account_needs_a_value(self) -> "TransactionBulkEditRevertItem":
        if "account" in self.restore and self.account_id is None:
            raise ValueError("account_id is required to restore the account")
        return self


class TransactionBulkEditResult(BaseModel):
    changed_count: int
    unlink_count: int = 0
    revert: list[TransactionBulkEditRevertItem]
    """Pass back to POST /finance/transactions/bulk-edit/revert to undo this edit."""


class TransactionBulkRevertRequest(BaseModel):
    items: list[TransactionBulkEditRevertItem] = Field(min_length=1, max_length=BULK_EDIT_MAX)


class TransactionBulkRevertResult(BaseModel):
    reverted_count: int


class TransferLinkRequest(BaseModel):
    """Links two independently-imported transfer legs as counterparts of each other
    (see TransactionRepository.get_transfer_match_candidates) -- both transactions must
    already exist and be unmatched; no new rows are created and no balances change,
    since each leg already reflects its own account's true balance from its own
    statement import."""
    counterpart_transaction_id: int


# --- Analytics response models ---

class SpendingReportResponse(BaseModel):
    total: Decimal
    currency: str
    from_date: date
    to_date: date
    transaction_count: int


class CategorySpendingItem(BaseModel):
    category_id: int | None
    category_name: str | None
    total: Decimal
    transaction_count: int


class SpendingByCategoryResponse(BaseModel):
    items: list[CategorySpendingItem]
    from_date: date
    to_date: date
    currency: str


class SpendingOverTimeItem(BaseModel):
    period: str
    total: Decimal


class SpendingOverTimeResponse(BaseModel):
    items: list[SpendingOverTimeItem]
    from_date: date
    to_date: date
    currency: str
    group_by: str


class UnmatchedTransferAccount(BaseModel):
    id: int
    name: str


class TransactionCountItem(BaseModel):
    period: str
    count: int
    unmatched_transfer_count: int = 0
    """Count of this period's transactions that are transfers with no confirmed
    counterpart (see TransactionRepository.get_transaction_counts) -- a signal the
    counterpart account's statement for this period may still be missing."""
    unmatched_transfer_accounts: list[UnmatchedTransferAccount] = []
    """The account(s), per counterpart_account_id, those unresolved transfers point
    at -- an unconfirmed guess, but usually enough to tell which statement to import
    next. Empty when a dangling transfer never got a counterpart account guess."""


class TransactionCoverageResponse(BaseModel):
    items: list[TransactionCountItem]
    from_date: date
    to_date: date
    group_by: str
    account_id: int | None


class AccountSpendingItem(BaseModel):
    account_id: int | None
    account_name: str | None
    total: Decimal
    transaction_count: int


class SpendingByAccountResponse(BaseModel):
    items: list[AccountSpendingItem]
    from_date: date
    to_date: date
    currency: str


class IncomeExpenseOverTimeItem(BaseModel):
    period: str
    income: Decimal
    expense: Decimal


class IncomeExpenseOverTimeResponse(BaseModel):
    items: list[IncomeExpenseOverTimeItem]
    from_date: date
    to_date: date
    currency: str
    group_by: str


class NetWorthHistoryItem(BaseModel):
    period: str
    total: Decimal


class NetWorthHistoryResponse(BaseModel):
    items: list[NetWorthHistoryItem]
    from_date: date | None
    to_date: date
    currency: str
    group_by: str


class NetWorthFilters:
    """Unlike AnalyticsFilters, net worth is a running balance, not a period
    total -- from_date only trims which buckets are returned (the running
    total itself is always reconstructed from the full transaction history up
    to to_date), and there's no category/merchant/top_n narrowing.
    """

    def __init__(
        self,
        from_date: Annotated[date | None, Query()] = None,
        to_date: Annotated[date | None, Query()] = None,
        currency: Annotated[str, Query()] = "EUR",
    ) -> None:
        self.from_date = from_date
        self.to_date = to_date or local_today()
        self.currency = currency.upper()


class SpendingAverageResponse(BaseModel):
    average_per_day: Decimal
    total: Decimal
    days: int
    from_date: date
    to_date: date


class SpendingTopResponse(BaseModel):
    transactions: list[TransactionRead]
    from_date: date
    to_date: date
    top_n: int


class TransactionBackfillEurResponse(BaseModel):
    updated_count: int
    failed_count: int
    remaining_count: int


class BalanceForecastResponse(BaseModel):
    current_balance: Decimal
    projected_income: Decimal
    projected_expenses: Decimal
    projected_balance: Decimal
    currency: str
    forecast_to: date


class AnalyticsFilters:
    def __init__(
        self,
        period: Annotated[str | None, Query()] = None,
        from_date: Annotated[date | None, Query()] = None,
        to_date: Annotated[date | None, Query()] = None,
        category_id: Annotated[int | None, Query()] = None,
        account_id: Annotated[int | None, Query()] = None,
        merchant: Annotated[str | None, Query()] = None,
        top_n: Annotated[int, Query(ge=1, le=50)] = 5,
        currency: Annotated[str, Query()] = "EUR",
        tags: Annotated[list[str] | None, Query()] = None,
        tags_mode: Annotated[Literal["all", "any"], Query()] = "all",
    ) -> None:
        self.period = period
        self.from_date = from_date
        self.to_date = to_date
        self.category_id = category_id
        self.account_id = account_id
        self.merchant = merchant
        self.top_n = top_n
        self.currency = currency.upper()
        self.tags = tags
        self.tags_mode = tags_mode
