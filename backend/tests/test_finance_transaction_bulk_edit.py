from decimal import Decimal

from app.features.finance.transactions.bulk_edit import BulkRow, plan_bulk_edit, plan_revert
from app.features.finance.transactions.schemas import TransactionBulkChanges


def _row(id=1, account_id=1, type="expense", amount="50.00", category_id=None, merchant="Shop",
         tags=(), linked_counterpart_id=None) -> BulkRow:
    return BulkRow(
        id=id, account_id=account_id, type=type, amount=Decimal(amount), category_id=category_id,
        merchant=merchant, tags=frozenset(tags), linked_counterpart_id=linked_counterpart_id,
    )


class TestPlanTags:
    def test_adds_only_where_missing(self):
        plan = plan_bulk_edit([_row(id=1), _row(id=2, tags={"travel"})], TransactionBulkChanges(add_tags=["Travel"]))
        assert dict(plan.write.add_tags) == {"travel": [1]}
        assert [item.id for item in plan.revert] == [1]
        assert plan.revert[0].added_tags == ["travel"]

    def test_removes_only_where_present(self):
        plan = plan_bulk_edit([_row(id=1, tags={"work"}), _row(id=2)], TransactionBulkChanges(remove_tags=["work"]))
        assert dict(plan.write.remove_tags) == {"work": [1]}
        assert plan.revert[0].removed_tags == ["work"]

    def test_rows_that_already_match_are_left_out(self):
        plan = plan_bulk_edit([_row(tags={"travel"}, category_id=3)], TransactionBulkChanges(add_tags=["travel"], category_id=3))
        assert plan.write.is_empty() and plan.revert == []


class TestPlanFields:
    def test_sets_category_and_remembers_the_old_one(self):
        plan = plan_bulk_edit([_row(id=1, category_id=2), _row(id=2, category_id=None)], TransactionBulkChanges(category_id=5))
        assert dict(plan.write.categories) == {5: [1, 2]}
        assert [(i.restore, i.category_id) for i in plan.revert] == [(["category"], 2), (["category"], None)]

    def test_clears_category(self):
        plan = plan_bulk_edit([_row(category_id=2)], TransactionBulkChanges(clear_category=True))
        assert dict(plan.write.categories) == {None: [1]}

    def test_renames_merchant(self):
        plan = plan_bulk_edit([_row(merchant="UBER *TRIP 1"), _row(id=2, merchant="Uber")], TransactionBulkChanges(merchant="Uber"))
        assert dict(plan.write.merchants) == {"Uber": [1]}
        assert plan.revert[0].merchant == "UBER *TRIP 1"


class TestPlanAccountMove:
    def test_moves_the_balance_effect_between_accounts(self):
        rows = [_row(id=1, type="expense", amount="50.00"), _row(id=2, type="income", amount="20.00")]
        plan = plan_bulk_edit(rows, TransactionBulkChanges(account_id=2))
        assert dict(plan.write.accounts) == {2: [1, 2]}
        # Expense -50 and income +20 leave account 1 (net -30 there, so +30 back) and land on account 2.
        assert plan.write.balance_deltas == {1: Decimal("30.00"), 2: Decimal("-30.00")}
        assert all(item.account_id == 1 and item.restore == ["account"] for item in plan.revert)

    def test_breaks_a_confirmed_transfer_link_on_both_legs(self):
        plan = plan_bulk_edit([_row(id=1, type="transfer", amount="-10", linked_counterpart_id=9)], TransactionBulkChanges(account_id=2))
        assert plan.write.unlink_ids == {1, 9}
        assert len(plan.write.unlinked_pairs) == 1

    def test_other_changes_never_touch_links(self):
        plan = plan_bulk_edit([_row(linked_counterpart_id=9)], TransactionBulkChanges(add_tags=["x"], category_id=1))
        assert plan.write.unlink_ids == set()

    def test_rows_already_on_the_target_account_do_not_move(self):
        plan = plan_bulk_edit([_row(account_id=2)], TransactionBulkChanges(account_id=2))
        assert plan.write.is_empty() and not plan.write.balance_deltas


class TestPlanRevert:
    def test_undoes_every_change_from_the_current_state(self):
        before = [_row(id=1, category_id=2, merchant="Old", tags={"work"}, account_id=1)]
        changes = TransactionBulkChanges(add_tags=["travel"], remove_tags=["work"], category_id=5, merchant="New", account_id=2)
        plan = plan_bulk_edit(before, changes)
        after = [_row(id=1, category_id=5, merchant="New", tags={"travel"}, account_id=2)]

        write, reverted = plan_revert(after, plan.revert)

        assert reverted == 1
        assert dict(write.remove_tags) == {"travel": [1]}
        assert dict(write.add_tags) == {"work": [1]}
        assert dict(write.categories) == {2: [1]}
        assert dict(write.merchants) == {"Old": [1]}
        assert dict(write.accounts) == {1: [1]}
        assert write.balance_deltas == {2: Decimal("50.00"), 1: Decimal("-50.00")}

    def test_skips_deleted_rows(self):
        plan = plan_bulk_edit([_row(id=1)], TransactionBulkChanges(add_tags=["travel"]))
        write, reverted = plan_revert([], plan.revert)
        assert reverted == 0 and write.is_empty()

    def test_a_row_changed_again_since_is_only_reverted_where_it_differs(self):
        plan = plan_bulk_edit([_row(id=1)], TransactionBulkChanges(add_tags=["travel"]))
        # The tag was already taken off by hand: nothing left to undo.
        write, reverted = plan_revert([_row(id=1)], plan.revert)
        assert reverted == 0 and write.is_empty()
