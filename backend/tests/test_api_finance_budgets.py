import pytest
from datetime import date
from decimal import Decimal
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock
from app.features.finance.budgets.schemas import BudgetRead, BudgetRemainingResponse

AUTH = {"Authorization": "Bearer test-api-token"}


def _budget_read(**kwargs):
    defaults = dict(
        id=1, name="Monthly Groceries", category_id=1,
        amount=Decimal("300.00"), period="monthly",
        starts_at=None, ends_at=None,
    )
    defaults.update(kwargs)
    return BudgetRead(**defaults)


def _remaining_response(**kwargs):
    defaults = dict(
        budget_id=1, budget_name="Monthly Groceries",
        budget_amount=Decimal("300.00"), spent=Decimal("120.00"),
        remaining=Decimal("180.00"), period="monthly",
        from_date=date(2026, 6, 1), to_date=date(2026, 6, 30),
    )
    defaults.update(kwargs)
    return BudgetRemainingResponse(**defaults)


@pytest.fixture
def mock_service():
    svc = AsyncMock()
    svc.get.return_value = _budget_read()
    svc.list.return_value = [_budget_read()]
    svc.create.return_value = _budget_read(id=2)
    svc.update.return_value = _budget_read(amount=Decimal("350.00"))
    svc.delete.return_value = True
    svc.remaining.return_value = [_remaining_response()]
    return svc


@pytest.fixture
def client(mock_service):
    from app.main import app
    from app.dependencies import get_budget_service
    app.dependency_overrides[get_budget_service] = lambda: mock_service
    yield TestClient(app)
    app.dependency_overrides.clear()


class TestListBudgets:
    def test_returns_list(self, client):
        response = client.get("/finance/budgets/", headers=AUTH)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert data[0]["name"] == "Monthly Groceries"

    def test_requires_auth(self, client):
        assert client.get("/finance/budgets/").status_code == 403

    def test_period_filter_passed_to_service(self, client, mock_service):
        client.get("/finance/budgets/?period=monthly", headers=AUTH)
        filters = mock_service.list.call_args[0][0]
        assert filters.period == "monthly"

    def test_invalid_period_returns_422(self, client):
        assert client.get("/finance/budgets/?period=invalid", headers=AUTH).status_code == 422


class TestGetBudget:
    def test_found_returns_200(self, client):
        response = client.get("/finance/budgets/1", headers=AUTH)
        assert response.status_code == 200
        assert response.json()["id"] == 1

    def test_not_found_returns_404(self, client, mock_service):
        mock_service.get.return_value = None
        response = client.get("/finance/budgets/999", headers=AUTH)
        assert response.status_code == 404
        assert response.json()["detail"] == "Budget not found"

    def test_requires_auth(self, client):
        assert client.get("/finance/budgets/1").status_code == 403


class TestBudgetRemaining:
    def test_returns_list_of_remaining(self, client):
        response = client.get("/finance/budgets/remaining", headers=AUTH)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert data[0]["spent"] == "120.00"
        assert data[0]["remaining"] == "180.00"

    def test_period_and_category_passed_to_service(self, client, mock_service):
        client.get("/finance/budgets/remaining?period=this month&category_id=2", headers=AUTH)
        mock_service.remaining.assert_called_once_with(period="this month", category_id=2)

    def test_requires_auth(self, client):
        assert client.get("/finance/budgets/remaining").status_code == 403


class TestCreateBudget:
    def test_creates_and_returns_201(self, client):
        payload = {"name": "Transport", "amount": "150.00", "period": "monthly"}
        response = client.post("/finance/budgets/", json=payload, headers=AUTH)
        assert response.status_code == 201

    def test_missing_required_fields_returns_422(self, client):
        assert client.post("/finance/budgets/", json={}, headers=AUTH).status_code == 422

    def test_requires_auth(self, client):
        assert client.post("/finance/budgets/", json={}).status_code == 403


class TestUpdateBudget:
    def test_updates_and_returns_200(self, client):
        response = client.patch("/finance/budgets/1", json={"amount": "350.00"}, headers=AUTH)
        assert response.status_code == 200
        assert response.json()["amount"] == "350.00"

    def test_not_found_returns_404(self, client, mock_service):
        mock_service.update.return_value = None
        assert client.patch("/finance/budgets/999", json={"name": "X"}, headers=AUTH).status_code == 404

    def test_requires_auth(self, client):
        assert client.patch("/finance/budgets/1", json={}).status_code == 403


class TestDeleteBudget:
    def test_deletes_returns_204(self, client):
        assert client.delete("/finance/budgets/1", headers=AUTH).status_code == 204

    def test_not_found_returns_404(self, client, mock_service):
        mock_service.delete.return_value = False
        assert client.delete("/finance/budgets/999", headers=AUTH).status_code == 404

    def test_requires_auth(self, client):
        assert client.delete("/finance/budgets/1").status_code == 403

    def test_service_called_with_correct_id(self, client, mock_service):
        client.delete("/finance/budgets/7", headers=AUTH)
        mock_service.delete.assert_called_once_with(7)
