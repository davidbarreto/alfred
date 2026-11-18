import logging
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.features.finance.transactions.bulk_edit_service import (
    InvalidBulkEditError,
    TransactionBulkEditService,
)
from app.features.finance.transactions.schemas import (
    BULK_EDIT_MAX,
    TransactionBulkChanges,
    TransactionBulkEditPreviewRequest,
    TransactionBulkEditRequest,
    TransactionBulkEditRevertItem,
    TransactionBulkRevertRequest,
    TransactionQuery,
)


def _tag(name):
    tag = MagicMock()
    tag.name = name
    return tag


def _txn(id=1, account_id=1, type="expense", amount="50.00", category_id=None, merchant="Shop",
         tags=(), counterpart_transaction_id=None, source="import"):
    t = MagicMock()
    t.id = id
    t.account_id = account_id
    t.type = type
    t.amount = Decimal(amount)
    t.category_id = category_id
    t.merchant = merchant
    t.tags = [_tag(n) for n in tags]
    t.counterpart_transaction_id = counterpart_transaction_id
    t.source = source
    # Fields TransactionRead needs for the preview sample.
    t.date = "2026-11-01T10:00:00"
    t.currency = "EUR"
    t.amount_eur = Decimal(amount)
    t.description = None
    t.bank_description = None
    t.note = None
    t.counterpart_account_id = None
    t.balance_after = None
    t.installment_plan_id = None
    t.import_batch_id = None
    t.created_at = "2026-11-01T10:00:00"
    return t


@pytest.fixture
def service():
    svc = TransactionBulkEditService.__new__(TransactionBulkEditService)
    svc._repo = AsyncMock()
    svc._repo.get_filtered_sum.return_value = (Decimal("-100.00"), 2)
    svc._repo.get_auto_transfer_ids.return_value = set()
    svc._account_repo = AsyncMock()
    svc._category_repo = AsyncMock()
    svc._tag_repo = AsyncMock()
    svc._tag_repo.get_tags.return_value = [_tag("travel")]
    svc._settings = AsyncMock()
    svc._settings.get_cycle_start_day.return_value = 1
    return svc


def _preview_request(changes=None, **filters):
    return TransactionBulkEditPreviewRequest(
        filters=TransactionQuery(**(filters or {"search": "uber"})),
        changes=changes or TransactionBulkChanges(add_tags=["travel"]),
    )


class TestPreview:
    async def test_refuses_without_filters(self, service):
        with pytest.raises(InvalidBulkEditError, match="at least one filter"):
            await service.preview(TransactionBulkEditPreviewRequest(
                filters=TransactionQuery(), changes=TransactionBulkChanges(add_tags=["x"]),
            ))
        service._repo.list_matching.assert_not_awaited()

    async def test_refuses_too_many_matches(self, service):
        service._repo.get_filtered_sum.return_value = (Decimal("0"), BULK_EDIT_MAX + 1)
        with pytest.raises(InvalidBulkEditError, match=str(BULK_EDIT_MAX + 1)):
            await service.preview(_preview_request())

    async def test_passes_every_filter_through(self, service):
        service._repo.list_matching.return_value = []
        await service.preview(_preview_request(search="uber", tags=["work"], min_amount="5", account_id=3))
        filters = service._repo.list_matching.call_args.args[0]
        assert (filters.search, filters.tags, filters.min_amount, filters.account_id) == ("uber", ["work"], Decimal("5"), 3)

    async def test_reports_counts_ids_sample_and_new_tags(self, service):
        service._repo.list_matching.return_value = [
            _txn(id=1, tags={"travel"}), _txn(id=2), _txn(id=3, type="transfer", amount="-5", counterpart_transaction_id=8),
        ]
        preview = await service.preview(_preview_request(TransactionBulkChanges(add_tags=["travel", "lisbon"])))

        assert preview.match_count == 3 and preview.transaction_ids == [1, 2, 3]
        assert preview.change_count == 3
        assert [(t.name, t.count, t.new) for t in preview.add_tags] == [("travel", 2, False), ("lisbon", 3, True)]
        assert preview.linked_transfer_count == 1
        assert [t.id for t in preview.sample] == [1, 2, 3]

    async def test_sample_is_capped_at_five(self, service):
        service._repo.list_matching.return_value = [_txn(id=i) for i in range(1, 9)]
        preview = await service.preview(_preview_request())
        assert [t.id for t in preview.sample] == [1, 2, 3, 4, 5] and preview.match_count == 8
        assert preview.total == Decimal("-100.00") and preview.currency == "EUR"
        service._repo.apply_bulk_write.assert_not_awaited()

    async def test_move_across_several_accounts_is_refused(self, service):
        service._repo.list_matching.return_value = [_txn(id=1, account_id=1), _txn(id=2, account_id=2)]
        service._account_repo.get.return_value = MagicMock()
        with pytest.raises(InvalidBulkEditError, match="2 accounts"):
            await service.preview(_preview_request(TransactionBulkChanges(account_id=3)))

    async def test_unknown_category_is_refused(self, service):
        service._category_repo.get.return_value = None
        with pytest.raises(InvalidBulkEditError, match="Category 9 not found"):
            await service.preview(_preview_request(TransactionBulkChanges(category_id=9)))

    async def test_counts_the_confirmed_links_a_move_breaks_but_not_mirrors(self, service):
        service._account_repo.get.return_value = MagicMock()
        service._repo.get_auto_transfer_ids.return_value = {21}
        service._repo.list_matching.return_value = [
            _txn(id=1, type="transfer", amount="-5", counterpart_transaction_id=20),
            _txn(id=2, type="transfer", amount="-5", counterpart_transaction_id=21),
            _txn(id=3, type="transfer", amount="-5", counterpart_transaction_id=22, source="auto_transfer"),
        ]
        preview = await service.preview(_preview_request(TransactionBulkChanges(account_id=2)))
        assert preview.unlink_count == 1 and preview.account_count == 3


class TestApply:
    async def test_moving_adjusts_both_account_balances(self, service):
        # The old bulk move rewrote account_id with a bare UPDATE and left both stored balances stale.
        service._account_repo.get.return_value = MagicMock()
        service._repo.get_many.return_value = [_txn(id=1, amount="50.00"), _txn(id=2, type="income", amount="20.00")]

        result = await service.apply(TransactionBulkEditRequest(
            transaction_ids=[1, 2], changes=TransactionBulkChanges(account_id=2),
        ))

        assert result.changed_count == 2
        service._repo.apply_bulk_write.assert_awaited_once()
        calls = {c.args for c in service._account_repo.adjust_balance.await_args_list}
        assert calls == {(1, Decimal("30.00")), (2, Decimal("-30.00"))}

    async def test_returns_what_undo_needs(self, service):
        service._repo.get_many.return_value = [_txn(id=1, category_id=4)]
        result = await service.apply(TransactionBulkEditRequest(
            transaction_ids=[1], changes=TransactionBulkChanges(clear_category=True, add_tags=["travel"]),
        ))
        item = result.revert[0]
        assert (item.id, item.restore, item.category_id, item.added_tags) == (1, ["category"], 4, ["travel"])

    async def test_nothing_to_change_writes_nothing(self, service):
        service._repo.get_many.return_value = [_txn(id=1, tags={"travel"})]
        result = await service.apply(TransactionBulkEditRequest(
            transaction_ids=[1], changes=TransactionBulkChanges(add_tags=["travel"]),
        ))
        assert result.changed_count == 0
        service._repo.apply_bulk_write.assert_not_awaited()
        service._account_repo.adjust_balance.assert_not_awaited()

    async def test_tag_only_edit_leaves_balances_alone(self, service):
        service._repo.get_many.return_value = [_txn(id=1)]
        await service.apply(TransactionBulkEditRequest(
            transaction_ids=[1], changes=TransactionBulkChanges(add_tags=["travel"]),
        ))
        service._account_repo.adjust_balance.assert_not_awaited()

    async def test_logs_counts_and_change_kinds_without_amounts(self, service, caplog):
        service._repo.get_many.return_value = [_txn(id=1, amount="123.45")]
        with caplog.at_level(logging.INFO):
            await service.apply(TransactionBulkEditRequest(
                transaction_ids=[1], changes=TransactionBulkChanges(merchant="Uber"),
            ))
        message = next(m for m in caplog.messages if "bulk-edited" in m)
        assert "changed=1" in message and "merchant" in message and "123.45" not in message


class TestRevert:
    async def test_moves_back_and_restores_balances(self, service):
        service._account_repo.get.return_value = MagicMock()
        service._repo.get_many.return_value = [_txn(id=1, account_id=2, amount="50.00")]

        result = await service.revert(TransactionBulkRevertRequest(items=[
            TransactionBulkEditRevertItem(id=1, restore=["account"], account_id=1),
        ]))

        assert result.reverted_count == 1
        calls = {c.args for c in service._account_repo.adjust_balance.await_args_list}
        assert calls == {(2, Decimal("50.00")), (1, Decimal("-50.00"))}

    async def test_refuses_a_deleted_account(self, service):
        service._account_repo.get.return_value = None
        with pytest.raises(InvalidBulkEditError, match="Account 1 not found"):
            await service.revert(TransactionBulkRevertRequest(items=[
                TransactionBulkEditRevertItem(id=1, restore=["account"], account_id=1),
            ]))
        service._repo.apply_bulk_write.assert_not_awaited()
