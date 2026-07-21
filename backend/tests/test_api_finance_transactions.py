import pytest
from datetime import date, datetime
from decimal import Decimal
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock
from app.features.finance.accounts.schemas import AccountRead
from app.features.finance.transactions.schemas import (
    BalanceForecastResponse,
    CategorySpendingItem,
    SpendingAverageResponse,
    SpendingByCategoryResponse,
    SpendingReportResponse,
    SpendingTopResponse,
    TransactionBackfillEurResponse,
    TransactionRead,
)
from app.features.finance.transactions.service import InvalidBulkMoveError

AUTH = {"Authorization": "Bearer test-api-token"}


def _txn_read(**kwargs):
    defaults = dict(
        id=1, account_id=1, date=datetime(2026, 6, 12, 10, 0),
        amount=Decimal("45.50"), currency="EUR", type="expense",
        category_id=1, description="Test", merchant="Shop",
        source=None, created_at=datetime(2026, 6, 12, 10, 0),
    )
    defaults.update(kwargs)
    return TransactionRead(**defaults)


def _account_read(**kwargs):
    defaults = dict(
        id=1, name="Checking", type="checking",
        currency="EUR", balance=Decimal("1000.00"), is_active=True,
    )
    defaults.update(kwargs)
    return AccountRead(**defaults)


@pytest.fixture
def mock_txn_service():
    svc = AsyncMock()
    svc.get.return_value = _txn_read()
    svc.list.return_value = [_txn_read()]
    svc.create.return_value = _txn_read(id=2)
    svc.update.return_value = _txn_read(merchant="Updated Shop")
    svc.delete.return_value = True
    svc.spending_report.return_value = SpendingReportResponse(
        total=Decimal("200.00"), currency="EUR",
        from_date=date(2026, 6, 1), to_date=date(2026, 6, 30),
        transaction_count=4,
    )
    svc.income_report.return_value = SpendingReportResponse(
        total=Decimal("2000.00"), currency="EUR",
        from_date=date(2026, 6, 1), to_date=date(2026, 6, 30),
        transaction_count=1,
    )
    svc.spending_average.return_value = SpendingAverageResponse(
        average_per_day=Decimal("10.00"), total=Decimal("300.00"),
        days=30, from_date=date(2026, 6, 1), to_date=date(2026, 6, 30),
    )
    svc.spending_top.return_value = SpendingTopResponse(
        transactions=[_txn_read()],
        from_date=date(2026, 6, 1), to_date=date(2026, 6, 30), top_n=5,
    )
    svc.balance_forecast.return_value = (Decimal("0"), Decimal("0"), date(2026, 6, 30))
    svc.bulk_move_account.return_value = 12
    svc.backfill_amount_eur.return_value = TransactionBackfillEurResponse(
        updated_count=3, failed_count=1, remaining_count=1,
    )
    svc.spending_by_category.return_value = SpendingByCategoryResponse(
        items=[
            CategorySpendingItem(
                category_id=1,
                category_name="Groceries",
                total=Decimal("150.00"),
                transaction_count=3,
            )
        ],
        from_date=date(2026, 6, 1),
        to_date=date(2026, 6, 30),
        currency="EUR",
    )
    return svc


@pytest.fixture
def mock_account_service():
    svc = AsyncMock()
    svc.list.return_value = [_account_read()]
    return svc


@pytest.fixture
def mock_recurring_service():
    svc = AsyncMock()
    svc.list.return_value = []
    return svc


@pytest.fixture
def client(mock_txn_service, mock_account_service, mock_recurring_service):
    from app.main import app
    from app.dependencies import (
        get_transaction_service,
        get_account_service,
        get_recurring_transaction_service,
    )
    app.dependency_overrides[get_transaction_service] = lambda: mock_txn_service
    app.dependency_overrides[get_account_service] = lambda: mock_account_service
    app.dependency_overrides[get_recurring_transaction_service] = lambda: mock_recurring_service
    yield TestClient(app)
    app.dependency_overrides.clear()


class TestListTransactions:
    def test_returns_list(self, client):
        response = client.get("/finance/transactions/", headers=AUTH)
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_requires_auth(self, client):
        assert client.get("/finance/transactions/").status_code == 403

    def test_type_filter_passed_to_service(self, client, mock_txn_service):
        client.get("/finance/transactions/?type=expense", headers=AUTH)
        filters = mock_txn_service.list.call_args[0][0]
        assert filters.type == "expense"

    def test_limit_filter_passed_to_service(self, client, mock_txn_service):
        client.get("/finance/transactions/?limit=20", headers=AUTH)
        filters = mock_txn_service.list.call_args[0][0]
        assert filters.limit == 20

    def test_offset_filter_passed_to_service(self, client, mock_txn_service):
        client.get("/finance/transactions/?offset=40", headers=AUTH)
        filters = mock_txn_service.list.call_args[0][0]
        assert filters.offset == 40

    def test_offset_defaults_to_zero(self, client, mock_txn_service):
        client.get("/finance/transactions/", headers=AUTH)
        filters = mock_txn_service.list.call_args[0][0]
        assert filters.offset == 0

    def test_invalid_type_returns_422(self, client):
        assert client.get("/finance/transactions/?type=INVALID", headers=AUTH).status_code == 422


class TestGetTransaction:
    def test_found_returns_200(self, client):
        response = client.get("/finance/transactions/1", headers=AUTH)
        assert response.status_code == 200
        assert response.json()["id"] == 1

    def test_not_found_returns_404(self, client, mock_txn_service):
        mock_txn_service.get.return_value = None
        response = client.get("/finance/transactions/999", headers=AUTH)
        assert response.status_code == 404
        assert response.json()["detail"] == "Transaction not found"


class TestCreateTransaction:
    def test_creates_and_returns_201(self, client):
        payload = {
            "account_id": 1,
            "date": "2026-06-12T10:00:00",
            "amount": "45.50",
            "currency": "EUR",
            "type": "expense",
        }
        response = client.post("/finance/transactions/", json=payload, headers=AUTH)
        assert response.status_code == 201

    def test_requires_auth(self, client):
        assert client.post("/finance/transactions/", json={}).status_code == 403

    def test_missing_required_fields_returns_422(self, client):
        assert client.post("/finance/transactions/", json={}, headers=AUTH).status_code == 422

    def test_invalid_type_returns_422(self, client):
        payload = {"account_id": 1, "date": "2026-06-12T10:00:00", "amount": "10", "type": "INVALID"}
        assert client.post("/finance/transactions/", json=payload, headers=AUTH).status_code == 422


class TestUpdateTransaction:
    def test_updates_and_returns_200(self, client):
        response = client.patch("/finance/transactions/1", json={"merchant": "Updated Shop"}, headers=AUTH)
        assert response.status_code == 200
        assert response.json()["merchant"] == "Updated Shop"

    def test_not_found_returns_404(self, client, mock_txn_service):
        mock_txn_service.update.return_value = None
        assert client.patch("/finance/transactions/999", json={"merchant": "X"}, headers=AUTH).status_code == 404

    def test_requires_auth(self, client):
        assert client.patch("/finance/transactions/1", json={}).status_code == 403


class TestDeleteTransaction:
    def test_deletes_returns_204(self, client):
        assert client.delete("/finance/transactions/1", headers=AUTH).status_code == 204

    def test_not_found_returns_404(self, client, mock_txn_service):
        mock_txn_service.delete.return_value = False
        assert client.delete("/finance/transactions/999", headers=AUTH).status_code == 404

    def test_requires_auth(self, client):
        assert client.delete("/finance/transactions/1").status_code == 403


class TestBulkMoveTransactions:
    def test_returns_moved_count(self, client):
        response = client.post(
            "/finance/transactions/bulk-move",
            json={"account_id": 1, "target_account_id": 2},
            headers=AUTH,
        )
        assert response.status_code == 200
        assert response.json()["moved_count"] == 12

    def test_passes_optional_filters_to_service(self, client, mock_txn_service):
        client.post(
            "/finance/transactions/bulk-move",
            json={"account_id": 1, "target_account_id": 2, "type": "expense", "category_id": 3},
            headers=AUTH,
        )
        request = mock_txn_service.bulk_move_account.call_args[0][0]
        assert request.type == "expense"
        assert request.category_id == 3

    def test_invalid_move_returns_400(self, client, mock_txn_service):
        mock_txn_service.bulk_move_account.side_effect = InvalidBulkMoveError("Target account not found")
        response = client.post(
            "/finance/transactions/bulk-move",
            json={"account_id": 1, "target_account_id": 999},
            headers=AUTH,
        )
        assert response.status_code == 400
        assert response.json()["detail"] == "Target account not found"

    def test_requires_auth(self, client):
        response = client.post(
            "/finance/transactions/bulk-move", json={"account_id": 1, "target_account_id": 2}
        )
        assert response.status_code == 403


class TestBackfillEur:
    def test_returns_backfill_result(self, client):
        response = client.post("/finance/transactions/backfill-eur", headers=AUTH)
        assert response.status_code == 200
        data = response.json()
        assert data == {"updated_count": 3, "failed_count": 1, "remaining_count": 1}

    def test_passes_limit_as_batch_size(self, client, mock_txn_service):
        client.post("/finance/transactions/backfill-eur?limit=50", headers=AUTH)
        mock_txn_service.backfill_amount_eur.assert_called_once_with(batch_size=50)

    def test_requires_auth(self, client):
        assert client.post("/finance/transactions/backfill-eur").status_code == 403


class TestSpendingReport:
    def test_returns_200_with_report_fields(self, client):
        response = client.get("/finance/transactions/report", headers=AUTH)
        assert response.status_code == 200
        data = response.json()
        assert "total" in data
        assert "currency" in data
        assert "transaction_count" in data

    def test_currency_defaults_to_eur(self, client, mock_txn_service):
        client.get("/finance/transactions/report", headers=AUTH)
        filters = mock_txn_service.spending_report.call_args[0][0]
        assert filters.currency == "EUR"

    def test_currency_filter_passed_to_service(self, client, mock_txn_service):
        client.get("/finance/transactions/report?currency=BRL", headers=AUTH)
        filters = mock_txn_service.spending_report.call_args[0][0]
        assert filters.currency == "BRL"

    def test_requires_auth(self, client):
        assert client.get("/finance/transactions/report").status_code == 403


class TestIncomeReport:
    def test_returns_200_with_report_fields(self, client):
        response = client.get("/finance/transactions/income-report", headers=AUTH)
        assert response.status_code == 200
        data = response.json()
        assert "total" in data
        assert "currency" in data
        assert "transaction_count" in data

    def test_currency_filter_passed_to_service(self, client, mock_txn_service):
        client.get("/finance/transactions/income-report?currency=BRL", headers=AUTH)
        filters = mock_txn_service.income_report.call_args[0][0]
        assert filters.currency == "BRL"

    def test_requires_auth(self, client):
        assert client.get("/finance/transactions/income-report").status_code == 403


class TestSpendingAverage:
    def test_returns_200_with_average_fields(self, client):
        response = client.get("/finance/transactions/average", headers=AUTH)
        assert response.status_code == 200
        data = response.json()
        assert "average_per_day" in data
        assert "days" in data

    def test_requires_auth(self, client):
        assert client.get("/finance/transactions/average").status_code == 403


class TestSpendingTop:
    def test_returns_200_with_top_fields(self, client):
        response = client.get("/finance/transactions/top", headers=AUTH)
        assert response.status_code == 200
        data = response.json()
        assert "transactions" in data
        assert "top_n" in data

    def test_requires_auth(self, client):
        assert client.get("/finance/transactions/top").status_code == 403


class TestSpendingByCategory:
    def test_returns_200_with_items(self, client):
        response = client.get("/finance/transactions/by-category", headers=AUTH)
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "from_date" in data
        assert "currency" in data
        assert data["items"][0]["category_name"] == "Groceries"

    def test_items_have_required_fields(self, client):
        response = client.get("/finance/transactions/by-category", headers=AUTH)
        item = response.json()["items"][0]
        assert "category_id" in item
        assert "category_name" in item
        assert "total" in item
        assert "transaction_count" in item

    def test_period_filter_forwarded(self, client, mock_txn_service):
        client.get("/finance/transactions/by-category?period=this+month", headers=AUTH)
        filters = mock_txn_service.spending_by_category.call_args[0][0]
        assert filters.period == "this month"

    def test_requires_auth(self, client):
        assert client.get("/finance/transactions/by-category").status_code == 403


class TestBalanceForecast:
    def test_returns_200_with_forecast_fields(self, client):
        response = client.get("/finance/transactions/forecast", headers=AUTH)
        assert response.status_code == 200
        data = response.json()
        assert "current_balance" in data
        assert "projected_income" in data
        assert "projected_expenses" in data
        assert "projected_balance" in data
        assert data["currency"] == "EUR"

    def test_current_balance_sums_active_accounts(self, client, mock_account_service):
        mock_account_service.list.return_value = [
            _account_read(balance=Decimal("500.00")),
            _account_read(id=2, balance=Decimal("300.00")),
        ]
        response = client.get("/finance/transactions/forecast", headers=AUTH)
        assert response.status_code == 200
        assert response.json()["current_balance"] == "800.00"

    def test_requires_auth(self, client):
        assert client.get("/finance/transactions/forecast").status_code == 403

    def test_global_currency_returns_400(self, client):
        response = client.get("/finance/transactions/forecast?currency=GLOBAL", headers=AUTH)
        assert response.status_code == 400
