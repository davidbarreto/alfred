"""Pure planning for bulk edits of transactions: given the rows and the change, work out
which writes to make, the balance effect of any account move, and what each row looked
like before (for Undo). No DB access: TransactionBulkEditService loads the rows and
hands the plan to TransactionRepository.apply_bulk_write."""
from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal

from app.features.finance.transactions.schemas import (
    TransactionBulkChanges,
    TransactionBulkEditRevertItem,
)
from app.features.finance.transactions.service import _account_delta


@dataclass(frozen=True)
class BulkRow:
    """The parts of a transaction a bulk edit reads. Tag names are normalized."""

    id: int
    account_id: int
    type: str
    amount: Decimal
    category_id: int | None
    merchant: str | None
    tags: frozenset[str]
    linked_counterpart_id: int | None = None
    """The other leg when this row is half of a confirmed transfer pair (not an
    auto-mirror): moving it to another account clears the link on both legs, as
    TransactionService.update does for a single edit."""


@dataclass
class BulkWrite:
    """Every write a bulk edit makes, grouped by target value so each group is one UPDATE."""

    add_tags: dict[str, list[int]] = field(default_factory=lambda: defaultdict(list))
    remove_tags: dict[str, list[int]] = field(default_factory=lambda: defaultdict(list))
    categories: dict[int | None, list[int]] = field(default_factory=lambda: defaultdict(list))
    merchants: dict[str | None, list[int]] = field(default_factory=lambda: defaultdict(list))
    accounts: dict[int, list[int]] = field(default_factory=lambda: defaultdict(list))
    unlink_ids: set[int] = field(default_factory=set)
    balance_deltas: dict[int, Decimal] = field(default_factory=lambda: defaultdict(Decimal))
    """Signed change per account id from moving transactions between accounts."""
    unlinked_pairs: set[frozenset[int]] = field(default_factory=set)

    def is_empty(self) -> bool:
        return not (self.add_tags or self.remove_tags or self.categories or self.merchants or self.accounts)

    @property
    def category_count(self) -> int:
        return sum(len(ids) for ids in self.categories.values())

    @property
    def merchant_count(self) -> int:
        return sum(len(ids) for ids in self.merchants.values())

    @property
    def account_count(self) -> int:
        return sum(len(ids) for ids in self.accounts.values())


class _Builder:
    """Records one write per field that actually changes; each method returns whether it did."""

    def __init__(self) -> None:
        self.write = BulkWrite()
        self.changed: set[int] = set()

    def add_tag(self, row: BulkRow, name: str) -> bool:
        if name in row.tags:
            return False
        self.write.add_tags[name].append(row.id)
        self.changed.add(row.id)
        return True

    def remove_tag(self, row: BulkRow, name: str) -> bool:
        if name not in row.tags:
            return False
        self.write.remove_tags[name].append(row.id)
        self.changed.add(row.id)
        return True

    def set_category(self, row: BulkRow, category_id: int | None) -> bool:
        if row.category_id == category_id:
            return False
        self.write.categories[category_id].append(row.id)
        self.changed.add(row.id)
        return True

    def set_merchant(self, row: BulkRow, merchant: str | None) -> bool:
        if row.merchant == merchant:
            return False
        self.write.merchants[merchant].append(row.id)
        self.changed.add(row.id)
        return True

    def move(self, row: BulkRow, account_id: int) -> bool:
        if row.account_id == account_id:
            return False
        self.write.accounts[account_id].append(row.id)
        delta = _account_delta(row.type, row.amount)
        self.write.balance_deltas[row.account_id] -= delta
        self.write.balance_deltas[account_id] += delta
        if row.linked_counterpart_id is not None:
            self.write.unlink_ids.update((row.id, row.linked_counterpart_id))
            self.write.unlinked_pairs.add(frozenset((row.id, row.linked_counterpart_id)))
        self.changed.add(row.id)
        return True


@dataclass
class BulkEditPlan:
    write: BulkWrite
    revert: list[TransactionBulkEditRevertItem]
    """One item per transaction that changes; the rows already matching are left out."""


def plan_bulk_edit(rows: list[BulkRow], changes: TransactionBulkChanges) -> BulkEditPlan:
    builder = _Builder()
    revert: list[TransactionBulkEditRevertItem] = []
    target_category = None if changes.clear_category else changes.category_id
    sets_category = changes.clear_category or changes.category_id is not None
    for row in rows:
        item = TransactionBulkEditRevertItem(id=row.id)
        item.added_tags = [name for name in changes.add_tags if builder.add_tag(row, name)]
        item.removed_tags = [name for name in changes.remove_tags if builder.remove_tag(row, name)]
        if sets_category and builder.set_category(row, target_category):
            item.restore.append("category")
            item.category_id = row.category_id
        if changes.merchant is not None and builder.set_merchant(row, changes.merchant):
            item.restore.append("merchant")
            item.merchant = row.merchant
        if changes.account_id is not None and builder.move(row, changes.account_id):
            item.restore.append("account")
            item.account_id = row.account_id
        if row.id in builder.changed:
            revert.append(item)
    return BulkEditPlan(write=builder.write, revert=revert)


def plan_revert(rows: list[BulkRow], items: list[TransactionBulkEditRevertItem]) -> tuple[BulkWrite, int]:
    """The writes that undo a bulk edit, from each row's current state; returns them with
    the number of transactions that change. Rows deleted since are skipped."""
    by_id = {row.id: row for row in rows}
    builder = _Builder()
    for item in items:
        row = by_id.get(item.id)
        if row is None:
            continue
        for name in item.added_tags:
            builder.remove_tag(row, name)
        for name in item.removed_tags:
            builder.add_tag(row, name)
        if "category" in item.restore:
            builder.set_category(row, item.category_id)
        if "merchant" in item.restore:
            builder.set_merchant(row, item.merchant)
        if "account" in item.restore and item.account_id is not None:
            builder.move(row, item.account_id)
    return builder.write, len(builder.changed)
