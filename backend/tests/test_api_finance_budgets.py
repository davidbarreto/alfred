import pytest
from datetime import date, datetime
from decimal import Decimal
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock
from app.features.finance.budgets.schemas import (
    BudgetTargetRead, CategoryAverageSpend, BudgetHistoryCycle, CategoryBudgetStatus, CurrentPeriodResponse,
    TagBudgetStatus,
)

AUTH = {"Authorization": "Bearer test-api-token"}


def _target_read(**kwargs):
    defaults = dict(
        id=1, category_id=1, amount=Decimal("300.00"),
        effective_from=datetime(2026, 7, 1), effective_to=None,
    )
    defaults.update(kwargs)
    return BudgetTargetRead(**defaults)


def _status(**kwargs):
    defaults = dict(
        category_id=1, category_name="Groceries", year_month=date(2026, 7, 1),
        limit_amount=Decimal("300.00"), spent=Decimal("120.00"),
    )
    defaults.update(kwargs)
    return CategoryBudgetStatus(**defaults)


@pytest.fixture
def mock_service():
    svc = AsyncMock()
    svc.list_current_targets.return_value = [_target_read()]
    svc.set_target.return_value = _target_read(amount=Decimal("350.00"))
    svc.set_targets_bulk.return_value = [_target_read()]
    svc.get_status.return_value = [_status()]
    svc.get_average_spend.return_value = [
        CategoryAverageSpend(category_id=1, category_name="Groceries", average=Decimal("150.00"), months=3)
    ]
    return svc


@pytest.fixture
def client(mock_service):
    from app.main import app
    from app.dependencies import get_budget_target_service
    app.dependency_overrides[get_budget_target_service] = lambda: mock_service
    yield TestClient(app)
    app.dependency_overrides.clear()


class TestListBudgetTargets:
    def test_returns_list(self, client):
        response = client.get("/finance/budgets/targets", headers=AUTH)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert data[0]["category_id"] == 1

    def test_requires_auth(self, client):
        assert client.get("/finance/budgets/targets").status_code == 403


class TestSetBudgetTargetsBulk:
    def test_sets_and_returns_200(self, client):
        payload = {"targets": [{"category_id": 1, "amount": "300.00"}, {"category_id": 2, "amount": None}]}
        response = client.put("/finance/budgets/targets", json=payload, headers=AUTH)
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_passes_items_to_service(self, client, mock_service):
        payload = {"targets": [{"category_id": 1, "amount": "300.00"}]}
        client.put("/finance/budgets/targets", json=payload, headers=AUTH)
        items = mock_service.set_targets_bulk.call_args[0][0]
        assert items[0].category_id == 1
        assert items[0].amount == Decimal("300.00")

    def test_requires_auth(self, client):
        assert client.put("/finance/budgets/targets", json={"targets": []}).status_code == 403


class TestSetBudgetTarget:
    def test_sets_and_returns_200(self, client):
        response = client.put("/finance/budgets/targets/1", json={"amount": "350.00"}, headers=AUTH)
        assert response.status_code == 200
        assert response.json()["amount"] == "350.00"

    def test_clear_returns_null(self, client, mock_service):
        mock_service.set_target.return_value = None
        response = client.put("/finance/budgets/targets/1", json={"amount": None}, headers=AUTH)
        assert response.status_code == 200
        assert response.json() is None

    def test_requires_auth(self, client):
        assert client.put("/finance/budgets/targets/1", json={}).status_code == 403


class TestBudgetStatus:
    def test_returns_list(self, client):
        response = client.get("/finance/budgets/status", headers=AUTH)
        assert response.status_code == 200
        data = response.json()
        assert data[0]["category_name"] == "Groceries"
        assert data[0]["spent"] == "120.00"

    def test_year_month_passed_to_service(self, client, mock_service):
        client.get("/finance/budgets/status?year_month=2026-06", headers=AUTH)
        called_with = mock_service.get_status.call_args[0][0]
        assert called_with == "2026-06"

    def test_invalid_year_month_returns_422(self, client, mock_service):
        mock_service.get_status.side_effect = ValueError("year_month must be in YYYY-MM format")
        assert client.get("/finance/budgets/status?year_month=not-a-date", headers=AUTH).status_code == 422

    def test_requires_auth(self, client):
        assert client.get("/finance/budgets/status").status_code == 403


class TestBudgetAverages:
    def test_returns_averages_with_default_months(self, client, mock_service):
        response = client.get("/finance/budgets/averages", headers=AUTH)
        assert response.status_code == 200
        assert response.json()[0]["average"] == "150.00"
        mock_service.get_average_spend.assert_awaited_once_with(12)

    def test_rejects_out_of_range_months(self, client):
        assert client.get("/finance/budgets/averages?months=0", headers=AUTH).status_code == 422

    def test_requires_auth(self, client):
        assert client.get("/finance/budgets/averages").status_code == 403


class TestCurrentPeriod:
    def test_returns_label_and_range(self, client, mock_service):
        mock_service.get_period.return_value = CurrentPeriodResponse(
            year_month="2026-10", from_date=date(2026, 10, 25), to_date=date(2026, 11, 24)
        )

        response = client.get("/finance/budgets/current-period?year_month=2026-10", headers=AUTH)

        assert response.status_code == 200
        assert response.json() == {"year_month": "2026-10", "from_date": "2026-10-25", "to_date": "2026-11-24"}
        mock_service.get_period.assert_awaited_once_with("2026-10")

    def test_invalid_year_month_returns_422(self, client, mock_service):
        mock_service.get_period.side_effect = ValueError("bad")

        response = client.get("/finance/budgets/current-period?year_month=nope", headers=AUTH)

        assert response.status_code == 422

    def test_requires_auth(self, client):
        assert client.get("/finance/budgets/current-period").status_code == 403


class TestBudgetHistory:
    def test_returns_cycles_with_default_count(self, client, mock_service):
        mock_service.get_history.return_value = [
            BudgetHistoryCycle(
                year_month="2026-10", from_date=date(2026, 10, 25), to_date=date(2026, 11, 24), items=[_status()]
            )
        ]

        response = client.get("/finance/budgets/history", headers=AUTH)

        assert response.status_code == 200
        body = response.json()
        assert body[0]["year_month"] == "2026-10"
        assert body[0]["items"][0]["category_name"] == "Groceries"
        mock_service.get_history.assert_awaited_once_with(6)

    def test_rejects_out_of_range_cycles(self, client):
        assert client.get("/finance/budgets/history?cycles=0", headers=AUTH).status_code == 422
        assert client.get("/finance/budgets/history?cycles=25", headers=AUTH).status_code == 422

    def test_requires_auth(self, client):
        assert client.get("/finance/budgets/history").status_code == 403


class TestTagBudgets:
    def test_tag_status_returns_items(self, client, mock_service):
        mock_service.get_tag_status.return_value = [
            TagBudgetStatus(
                tag_id=5, tag_name="Travel", year_month=date(2026, 7, 1),
                limit_amount=Decimal("1500.00"), spent=Decimal("200.00"), overlap_count=1,
            )
        ]
        response = client.get("/finance/budgets/tag-status?year_month=2026-07", headers=AUTH)
        assert response.status_code == 200
        item = response.json()[0]
        assert (item["tag_name"], item["overlap_count"]) == ("Travel", 1)
        mock_service.get_tag_status.assert_awaited_once_with("2026-07")

    def test_tag_status_rejects_bad_month(self, client, mock_service):
        mock_service.get_tag_status.side_effect = ValueError
        assert client.get("/finance/budgets/tag-status?year_month=nope", headers=AUTH).status_code == 422

    def test_set_tag_target(self, client, mock_service):
        mock_service.set_tag_target.return_value = _target_read(category_id=None, tag_id=5, amount=Decimal("1500.00"))
        response = client.put("/finance/budgets/tag-targets/5", json={"amount": "1500.00"}, headers=AUTH)
        assert response.status_code == 200
        assert response.json()["tag_id"] == 5
        mock_service.set_tag_target.assert_awaited_once_with(5, Decimal("1500.00"))

    def test_set_tag_target_unknown_tag_is_404(self, client, mock_service):
        from app.features.finance.budgets.service import BudgetTagNotFoundError
        mock_service.set_tag_target.side_effect = BudgetTagNotFoundError(99)
        assert client.put("/finance/budgets/tag-targets/99", json={"amount": "10"}, headers=AUTH).status_code == 404

    def test_bulk_forwards_tag_targets(self, client, mock_service):
        client.put(
            "/finance/budgets/targets",
            json={"targets": [], "tag_targets": [{"tag_id": 5, "amount": "100"}]},
            headers=AUTH,
        )
        tag_items = mock_service.set_targets_bulk.call_args.args[1]
        assert tag_items[0].tag_id == 5

    def test_requires_auth(self, client):
        assert client.get("/finance/budgets/tag-status").status_code == 403
