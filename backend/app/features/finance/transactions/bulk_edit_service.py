import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.finance.accounts.repository import AccountRepository
from app.features.finance.categories.repository import CategoryRepository
from app.features.finance.settings.service import FinanceSettingsService
from app.features.finance.tags.repository import TagRepository
from app.features.finance.transactions.bulk_edit import BulkRow, BulkWrite, plan_bulk_edit, plan_revert
from app.features.finance.transactions.repository import TransactionRepository
from app.features.finance.transactions.schemas import (
    BULK_EDIT_MAX,
    TransactionBulkChanges,
    TransactionBulkEditPreview,
    TransactionBulkEditPreviewRequest,
    TransactionBulkEditRequest,
    TransactionBulkEditResult,
    TransactionBulkRevertRequest,
    TransactionBulkRevertResult,
    TransactionBulkTagCount,
    TransactionRead,
)
from app.features.finance.transactions.tables import Transaction

logger = logging.getLogger(__name__)

_SAMPLE_SIZE = 5


class InvalidBulkEditError(Exception):
    """A bulk edit that can't run as asked: no filters, too many matches, an unknown
    category or account, or an account move across several accounts."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class TransactionBulkEditService:
    """Change tags, category, merchant or account on many transactions at once: a preview
    over the list's filters, an apply over the ids the preview returned, and an Undo.
    A linked transfer's other leg is never changed."""

    def __init__(self, session: AsyncSession) -> None:
        self._repo = TransactionRepository(session)
        self._account_repo = AccountRepository(session)
        self._category_repo = CategoryRepository(session)
        self._tag_repo = TagRepository(session)
        self._settings = FinanceSettingsService(session)

    async def preview(self, request: TransactionBulkEditPreviewRequest) -> TransactionBulkEditPreview:
        filters, changes = request.filters, request.changes
        if filters.is_empty():
            raise InvalidBulkEditError("Set at least one filter first: a bulk edit never applies to every transaction.")
        cycle_start_day = await self._settings.get_cycle_start_day()
        total, count = await self._repo.get_filtered_sum(filters, cycle_start_day)
        if count > BULK_EDIT_MAX:
            raise InvalidBulkEditError(
                f"{count} transactions match; a bulk edit handles up to {BULK_EDIT_MAX}. Narrow the filters."
            )
        await self._check_targets(changes)
        transactions = await self._repo.list_matching(filters, cycle_start_day, limit=BULK_EDIT_MAX)
        rows = await self._rows(transactions)
        self._check_move(rows, changes)
        plan = plan_bulk_edit(rows, changes)
        known_tags = {tag.name.lower() for tag in await self._tag_repo.get_tags()}
        return TransactionBulkEditPreview(
            match_count=len(rows),
            change_count=len(plan.revert),
            transaction_ids=[row.id for row in rows],
            sample=[TransactionRead.model_validate(t) for t in transactions[:_SAMPLE_SIZE]],
            add_tags=[
                TransactionBulkTagCount(
                    name=name, count=len(plan.write.add_tags.get(name, [])), new=name not in known_tags
                )
                for name in changes.add_tags
            ],
            remove_tags=[
                TransactionBulkTagCount(name=name, count=len(plan.write.remove_tags.get(name, [])))
                for name in changes.remove_tags
            ],
            category_count=plan.write.category_count,
            merchant_count=plan.write.merchant_count,
            account_count=plan.write.account_count,
            linked_transfer_count=sum(1 for t in transactions if t.counterpart_transaction_id is not None),
            unlink_count=len(plan.write.unlinked_pairs),
            total=total,
            currency=filters.currency or "EUR",
        )

    async def apply(self, request: TransactionBulkEditRequest) -> TransactionBulkEditResult:
        changes = request.changes
        await self._check_targets(changes)
        rows = await self._rows(await self._repo.get_many(request.transaction_ids))
        self._check_move(rows, changes)
        plan = plan_bulk_edit(rows, changes)
        await self._write(plan.write)
        logger.info(
            "Transactions bulk-edited: changed=%d of=%d changes=%s unlinked=%d",
            len(plan.revert), len(rows), changes.kinds(), len(plan.write.unlinked_pairs),
        )
        return TransactionBulkEditResult(
            changed_count=len(plan.revert), unlink_count=len(plan.write.unlinked_pairs), revert=plan.revert,
        )

    async def revert(self, request: TransactionBulkRevertRequest) -> TransactionBulkRevertResult:
        for item in request.items:
            if "category" in item.restore and item.category_id is not None:
                await self._require_category(item.category_id)
            if "account" in item.restore and item.account_id is not None:
                await self._require_account(item.account_id)
        rows = await self._rows(await self._repo.get_many([item.id for item in request.items]))
        write, reverted = plan_revert(rows, request.items)
        await self._write(write)
        logger.info("Transactions bulk edit reverted: reverted=%d of=%d", reverted, len(request.items))
        return TransactionBulkRevertResult(reverted_count=reverted)

    async def _write(self, write: BulkWrite) -> None:
        if write.is_empty():
            return
        await self._repo.apply_bulk_write(write)
        # Same rule as a single edit (TransactionService._reconcile_balance): each row moves
        # only its own account's balance, so a move takes its effect off one account and onto the other.
        for account_id, delta in write.balance_deltas.items():
            if delta:
                await self._account_repo.adjust_balance(account_id, delta)

    async def _rows(self, transactions: list[Transaction]) -> list[BulkRow]:
        counterpart_ids = [t.counterpart_transaction_id for t in transactions if t.counterpart_transaction_id]
        mirrors = await self._repo.get_auto_transfer_ids(counterpart_ids)
        return [
            BulkRow(
                id=t.id,
                account_id=t.account_id,
                type=t.type,
                amount=t.amount,
                category_id=t.category_id,
                merchant=t.merchant,
                tags=frozenset(tag.name.lower() for tag in t.tags),
                linked_counterpart_id=(
                    t.counterpart_transaction_id
                    if t.counterpart_transaction_id is not None
                    and t.source != "auto_transfer"
                    and t.counterpart_transaction_id not in mirrors
                    else None
                ),
            )
            for t in transactions
        ]

    async def _check_targets(self, changes: TransactionBulkChanges) -> None:
        if changes.category_id is not None:
            await self._require_category(changes.category_id)
        if changes.account_id is not None:
            await self._require_account(changes.account_id)

    async def _require_category(self, category_id: int) -> None:
        if await self._category_repo.get(category_id) is None:
            raise InvalidBulkEditError(f"Category {category_id} not found")

    async def _require_account(self, account_id: int) -> None:
        if await self._account_repo.get(account_id) is None:
            raise InvalidBulkEditError(f"Account {account_id} not found")

    @staticmethod
    def _check_move(rows: list[BulkRow], changes: TransactionBulkChanges) -> None:
        if changes.account_id is None:
            return
        sources = {row.account_id for row in rows}
        if len(sources) > 1:
            raise InvalidBulkEditError(
                f"These transactions are on {len(sources)} accounts: filter by one account before moving them."
            )
