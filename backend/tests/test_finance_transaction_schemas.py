import inspect

import pytest
from pydantic import ValidationError

from app.features.finance.transactions.schemas import (
    TransactionBulkChanges,
    TransactionBulkEditRevertItem,
    TransactionFilters,
    TransactionQuery,
)


class TestTransactionQuery:
    def test_carries_every_list_filter(self):
        # The old bulk move had its own short field list and silently ignored the
        # search, tag and amount filters the list was showing. Keep the two in step.
        list_params = set(inspect.signature(TransactionFilters.__init__).parameters) - {"self", "limit", "offset", "sort"}
        assert set(TransactionQuery.model_fields) == list_params

    def test_is_empty_without_filters(self):
        assert TransactionQuery().is_empty()
        assert TransactionQuery(tags_mode="any").is_empty()
        assert TransactionQuery(tags_mode="none").is_empty()

    @pytest.mark.parametrize("field,value", [
        ("search", "uber"), ("tags", ["travel"]), ("min_amount", "10"), ("uncategorized", True),
        ("unconfirmed_transfer", True), ("account_id", 1),
    ])
    def test_any_filter_makes_it_non_empty(self, field, value):
        assert not TransactionQuery(**{field: value}).is_empty()

    def test_blank_text_filters_count_as_unset(self):
        query = TransactionQuery(search="  ", merchant="", currency="")
        assert query.is_empty() and query.currency is None

    def test_currency_is_uppercased(self):
        assert TransactionQuery(currency="usd").currency == "USD"


class TestTransactionBulkChanges:
    def test_tag_names_are_normalized_and_deduplicated(self):
        changes = TransactionBulkChanges(add_tags=[" Travel", "travel", ""], remove_tags=["Work"])
        assert changes.add_tags == ["travel"] and changes.remove_tags == ["work"]

    def test_needs_at_least_one_change(self):
        with pytest.raises(ValidationError, match="at least one change"):
            TransactionBulkChanges(merchant="   ")

    def test_rejects_setting_and_clearing_the_category(self):
        with pytest.raises(ValidationError, match="not both"):
            TransactionBulkChanges(category_id=1, clear_category=True)

    def test_rejects_a_tag_both_added_and_removed(self):
        with pytest.raises(ValidationError, match="both added and removed"):
            TransactionBulkChanges(add_tags=["Travel"], remove_tags=["travel"])

    def test_kinds_lists_the_requested_changes(self):
        changes = TransactionBulkChanges(add_tags=["a"], clear_category=True, account_id=2, merchant="M")
        assert changes.kinds() == ["add_tags", "category", "merchant", "account"]


class TestRevertItem:
    def test_restoring_the_account_needs_one(self):
        with pytest.raises(ValidationError):
            TransactionBulkEditRevertItem(id=1, restore=["account"])
