import pytest
from decimal import Decimal
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock
from app.features.finance.recurring_transactions.schemas import ProcessResult, RecurringTransactionRead

AUTH = {"Authorization": "Bearer test-api-token"}


def _rt_read(**kwargs):
    defaults = dict(
        id=1, account_id=1, category_id=None,
        type="expense", amount=Decimal("9.99"), currency="EUR",
        merchant="Streaming Service",
        recurrence_rule="FREQ=MONTHLY", active=True,
        last_occurrence_date=None,
    )
    defaults.update(kwargs)
    return RecurringTransactionRead(**defaults)


@pytest.fixture
def mock_service():
    svc = AsyncMock()
    svc.get.return_value = _rt_read()
    svc.list.return_value = [_rt_read()]
    svc.create.return_value = _rt_read(id=2)
    svc.update.return_value = _rt_read(amount=Decimal("12.99"))
    svc.delete.return_value = True
    return svc


@pytest.fixture
def client(mock_service):
    from app.main import app
    from app.dependencies import get_recurring_transaction_service
    app.dependency_overrides[get_recurring_transaction_service] = lambda: mock_service
    yield TestClient(app)
    app.dependency_overrides.clear()


class TestListRecurring:
    def test_returns_list(self, client):
        response = client.get("/finance/recurring-transactions/", headers=AUTH)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert data[0]["merchant"] == "Streaming Service"

    def test_requires_auth(self, client):
        assert client.get("/finance/recurring-transactions/").status_code == 403

    def test_active_filter_passed_to_service(self, client, mock_service):
        client.get("/finance/recurring-transactions/?active=true", headers=AUTH)
        filters = mock_service.list.call_args[0][0]
        assert filters.active is True

    def test_type_filter_passed_to_service(self, client, mock_service):
        client.get("/finance/recurring-transactions/?type=income", headers=AUTH)
        filters = mock_service.list.call_args[0][0]
        assert filters.type == "income"

    def test_invalid_type_returns_422(self, client):
        assert client.get("/finance/recurring-transactions/?type=INVALID", headers=AUTH).status_code == 422


class TestGetRecurring:
    def test_found_returns_200(self, client):
        response = client.get("/finance/recurring-transactions/1", headers=AUTH)
        assert response.status_code == 200
        assert response.json()["id"] == 1

    def test_not_found_returns_404(self, client, mock_service):
        mock_service.get.return_value = None
        response = client.get("/finance/recurring-transactions/999", headers=AUTH)
        assert response.status_code == 404
        assert response.json()["detail"] == "Recurring transaction not found"

    def test_requires_auth(self, client):
        assert client.get("/finance/recurring-transactions/1").status_code == 403


class TestCreateRecurring:
    def test_creates_and_returns_201(self, client):
        payload = {
            "account_id": 1,
            "type": "expense",
            "amount": "9.99",
            "recurrence_rule": "monthly",
        }
        response = client.post("/finance/recurring-transactions/", json=payload, headers=AUTH)
        assert response.status_code == 201

    def test_missing_required_fields_returns_422(self, client):
        assert client.post("/finance/recurring-transactions/", json={}, headers=AUTH).status_code == 422

    def test_invalid_type_returns_422(self, client):
        payload = {"account_id": 1, "type": "INVALID", "amount": "10", "recurrence_rule": "monthly"}
        assert client.post("/finance/recurring-transactions/", json=payload, headers=AUTH).status_code == 422

    def test_requires_auth(self, client):
        assert client.post("/finance/recurring-transactions/", json={}).status_code == 403


class TestUpdateRecurring:
    def test_updates_and_returns_200(self, client):
        response = client.patch(
            "/finance/recurring-transactions/1", json={"amount": "12.99"}, headers=AUTH
        )
        assert response.status_code == 200
        assert response.json()["amount"] == "12.99"

    def test_not_found_returns_404(self, client, mock_service):
        mock_service.update.return_value = None
        assert client.patch(
            "/finance/recurring-transactions/999", json={"active": False}, headers=AUTH
        ).status_code == 404

    def test_requires_auth(self, client):
        assert client.patch("/finance/recurring-transactions/1", json={}).status_code == 403


class TestDeleteRecurring:
    def test_deletes_returns_204(self, client):
        assert client.delete("/finance/recurring-transactions/1", headers=AUTH).status_code == 204

    def test_not_found_returns_404(self, client, mock_service):
        mock_service.delete.return_value = False
        assert client.delete("/finance/recurring-transactions/999", headers=AUTH).status_code == 404

    def test_requires_auth(self, client):
        assert client.delete("/finance/recurring-transactions/1").status_code == 403

    def test_service_called_with_correct_id(self, client, mock_service):
        client.delete("/finance/recurring-transactions/3", headers=AUTH)
        mock_service.delete.assert_called_once_with(3)


class TestProcessRecurring:
    def test_returns_process_result(self, client, mock_service):
        mock_service.process.return_value = ProcessResult(created=3, deactivated=1)
        response = client.post("/finance/recurring-transactions/process", headers=AUTH)
        assert response.status_code == 200
        data = response.json()
        assert data["created"] == 3
        assert data["deactivated"] == 1

    def test_calls_service_process(self, client, mock_service):
        mock_service.process.return_value = ProcessResult(created=0, deactivated=0)
        client.post("/finance/recurring-transactions/process", headers=AUTH)
        mock_service.process.assert_called_once()

    def test_requires_auth(self, client):
        assert client.post("/finance/recurring-transactions/process").status_code == 403
