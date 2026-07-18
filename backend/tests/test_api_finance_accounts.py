import pytest
from decimal import Decimal
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock
from app.features.finance.accounts.schemas import AccountRead
from app.features.finance.accounts.service import AccountDeletionBlockedError

AUTH = {"Authorization": "Bearer test-api-token"}


def _account_read(**kwargs):
    defaults = dict(
        id=1, name="Main Checking", type="checking",
        currency="EUR", balance=Decimal("1500.00"),
        institution="My Bank", is_active=True,
    )
    defaults.update(kwargs)
    return AccountRead(**defaults)


@pytest.fixture
def mock_service():
    svc = AsyncMock()
    svc.get.return_value = _account_read()
    svc.list.return_value = [_account_read()]
    svc.create.return_value = _account_read(id=2, name="New Account")
    svc.update.return_value = _account_read(institution="Updated Bank")
    svc.delete.return_value = True
    return svc


@pytest.fixture
def client(mock_service):
    from app.main import app
    from app.dependencies import get_account_service
    app.dependency_overrides[get_account_service] = lambda: mock_service
    yield TestClient(app)
    app.dependency_overrides.clear()


class TestListAccounts:
    def test_returns_list(self, client):
        response = client.get("/finance/accounts/", headers=AUTH)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert data[0]["name"] == "Main Checking"

    def test_requires_auth(self, client):
        assert client.get("/finance/accounts/").status_code == 403

    def test_wrong_token_rejected(self, client):
        assert client.get("/finance/accounts/", headers={"Authorization": "Bearer bad"}).status_code == 401

    def test_is_active_filter_passed_to_service(self, client, mock_service):
        client.get("/finance/accounts/?is_active=true", headers=AUTH)
        filters = mock_service.list.call_args[0][0]
        assert filters.is_active is True

    def test_type_filter_passed_to_service(self, client, mock_service):
        client.get("/finance/accounts/?type=savings", headers=AUTH)
        filters = mock_service.list.call_args[0][0]
        assert filters.type == "savings"

    def test_invalid_type_returns_422(self, client):
        assert client.get("/finance/accounts/?type=invalid", headers=AUTH).status_code == 422


class TestGetAccount:
    def test_found_returns_200(self, client):
        response = client.get("/finance/accounts/1", headers=AUTH)
        assert response.status_code == 200
        assert response.json()["id"] == 1

    def test_not_found_returns_404(self, client, mock_service):
        mock_service.get.return_value = None
        response = client.get("/finance/accounts/999", headers=AUTH)
        assert response.status_code == 404
        assert response.json()["detail"] == "Account not found"

    def test_requires_auth(self, client):
        assert client.get("/finance/accounts/1").status_code == 403


class TestCreateAccount:
    def test_creates_and_returns_201(self, client):
        payload = {"name": "New Account", "type": "checking", "currency": "EUR", "balance": "0"}
        response = client.post("/finance/accounts/", json=payload, headers=AUTH)
        assert response.status_code == 201
        assert response.json()["name"] == "New Account"

    def test_requires_auth(self, client):
        assert client.post("/finance/accounts/", json={"name": "X", "type": "checking"}).status_code == 403

    def test_invalid_type_returns_422(self, client):
        payload = {"name": "X", "type": "INVALID"}
        assert client.post("/finance/accounts/", json=payload, headers=AUTH).status_code == 422

    def test_missing_required_fields_returns_422(self, client):
        assert client.post("/finance/accounts/", json={}, headers=AUTH).status_code == 422


class TestUpdateAccount:
    def test_updates_and_returns_200(self, client):
        response = client.patch("/finance/accounts/1", json={"institution": "Updated Bank"}, headers=AUTH)
        assert response.status_code == 200
        assert response.json()["institution"] == "Updated Bank"

    def test_not_found_returns_404(self, client, mock_service):
        mock_service.update.return_value = None
        assert client.patch("/finance/accounts/999", json={"name": "X"}, headers=AUTH).status_code == 404

    def test_requires_auth(self, client):
        assert client.patch("/finance/accounts/1", json={"name": "X"}).status_code == 403


class TestDeleteAccount:
    def test_deletes_returns_204(self, client):
        assert client.delete("/finance/accounts/1", headers=AUTH).status_code == 204

    def test_not_found_returns_404(self, client, mock_service):
        mock_service.delete.return_value = False
        assert client.delete("/finance/accounts/999", headers=AUTH).status_code == 404

    def test_requires_auth(self, client):
        assert client.delete("/finance/accounts/1").status_code == 403

    def test_service_called_with_correct_id(self, client, mock_service):
        client.delete("/finance/accounts/42", headers=AUTH)
        mock_service.delete.assert_called_once_with(42)

    def test_blocked_by_transactions_returns_409_with_count(self, client, mock_service):
        mock_service.delete.side_effect = AccountDeletionBlockedError(1, 187)
        response = client.delete("/finance/accounts/1", headers=AUTH)
        assert response.status_code == 409
        assert "187" in response.json()["detail"]

    def test_blocked_by_other_records_returns_409_generic_message(self, client, mock_service):
        mock_service.delete.side_effect = AccountDeletionBlockedError(1, 0)
        response = client.delete("/finance/accounts/1", headers=AUTH)
        assert response.status_code == 409
        assert "recurring" in response.json()["detail"].lower()
