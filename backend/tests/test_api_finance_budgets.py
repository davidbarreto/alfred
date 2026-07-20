import pytest
from datetime import date, datetime
from decimal import Decimal
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock
from app.features.finance.budgets.schemas import BudgetTargetRead, CategoryBudgetStatus

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
        assert called_with == date(2026, 6, 1)

    def test_invalid_year_month_returns_422(self, client):
        assert client.get("/finance/budgets/status?year_month=not-a-date", headers=AUTH).status_code == 422

    def test_requires_auth(self, client):
        assert client.get("/finance/budgets/status").status_code == 403
