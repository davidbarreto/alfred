from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.assistant.commands.handlers.finance import handle_finance
from app.features.finance.budgets.schemas import CategoryBudgetStatus, TagBudgetStatus


async def _budget_status(arguments, budget_service, category_service=None):
    return await handle_finance(
        "budget_status",
        arguments,
        transaction_service=AsyncMock(),
        account_service=AsyncMock(),
        budget_service=budget_service,
        recurring_service=AsyncMock(),
        category_service=category_service or AsyncMock(),
    )


@pytest.fixture
def budget_service():
    svc = AsyncMock()
    svc.get_status.return_value = [
        CategoryBudgetStatus(
            category_id=1, category_name="Restaurant", year_month=date(2026, 7, 1),
            limit_amount=Decimal("300.00"), spent=Decimal("40.00"),
        )
    ]
    svc.get_tag_status.return_value = [
        TagBudgetStatus(
            tag_id=5, tag_name="Travel", year_month=date(2026, 7, 1),
            limit_amount=Decimal("1500.00"), spent=Decimal("200.00"),
        )
    ]
    return svc


class TestBudgetStatus:
    async def test_lists_category_budgets_followed_by_tag_budgets(self, budget_service):
        result = await _budget_status({}, budget_service)

        assert [r.get("category_name") or r.get("tag_name") for r in result] == ["Restaurant", "Travel"]

    async def test_category_filter_returns_only_that_category(self, budget_service):
        category = MagicMock()
        category.id = 1
        category.name = "Restaurant"
        category_service = MagicMock()
        category_service.list = AsyncMock(return_value=[category])

        result = await _budget_status({"category": "Restaurant"}, budget_service, category_service)

        assert [r["category_id"] for r in result] == [1]
        budget_service.get_tag_status.assert_not_called()
