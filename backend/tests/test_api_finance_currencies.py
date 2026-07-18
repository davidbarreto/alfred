import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock
from app.features.finance.currencies.schemas import CurrencyRead
from app.features.finance.currencies.service import DuplicateCurrencyError

AUTH = {"Authorization": "Bearer test-api-token"}


def _currency_read(**kwargs):
    defaults = dict(code="EUR", symbol="€", name="Euro")
    defaults.update(kwargs)
    return CurrencyRead(**defaults)


@pytest.fixture
def mock_service():
    svc = AsyncMock()
    svc.get.return_value = _currency_read()
    svc.list.return_value = [_currency_read()]
    svc.create.return_value = _currency_read(code="PLN", symbol="zł", name="Polish Zloty")
    svc.update.return_value = _currency_read(name="Euro (EU)")
    svc.delete.return_value = True
    return svc


@pytest.fixture
def client(mock_service):
    from app.main import app
    from app.dependencies import get_currency_service
    app.dependency_overrides[get_currency_service] = lambda: mock_service
    yield TestClient(app)
    app.dependency_overrides.clear()


class TestListCurrencies:
    def test_returns_list(self, client):
        response = client.get("/finance/currencies/", headers=AUTH)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert data[0]["code"] == "EUR"

    def test_requires_auth(self, client):
        assert client.get("/finance/currencies/").status_code == 403


class TestGetCurrency:
    def test_found_returns_200(self, client):
        response = client.get("/finance/currencies/EUR", headers=AUTH)
        assert response.status_code == 200
        assert response.json()["code"] == "EUR"

    def test_not_found_returns_404(self, client, mock_service):
        mock_service.get.return_value = None
        response = client.get("/finance/currencies/XYZ", headers=AUTH)
        assert response.status_code == 404
        assert response.json()["detail"] == "Currency not found"

    def test_requires_auth(self, client):
        assert client.get("/finance/currencies/EUR").status_code == 403


class TestCreateCurrency:
    def test_creates_and_returns_201(self, client):
        response = client.post(
            "/finance/currencies/", json={"code": "PLN", "symbol": "zł", "name": "Polish Zloty"}, headers=AUTH
        )
        assert response.status_code == 201
        assert response.json()["code"] == "PLN"

    def test_missing_code_returns_422(self, client):
        assert client.post("/finance/currencies/", json={}, headers=AUTH).status_code == 422

    def test_duplicate_code_returns_409(self, client, mock_service):
        mock_service.create.side_effect = DuplicateCurrencyError("EUR")
        response = client.post("/finance/currencies/", json={"code": "EUR"}, headers=AUTH)
        assert response.status_code == 409

    def test_requires_auth(self, client):
        assert client.post("/finance/currencies/", json={"code": "PLN"}).status_code == 403


class TestUpdateCurrency:
    def test_updates_and_returns_200(self, client):
        response = client.patch("/finance/currencies/EUR", json={"name": "Euro (EU)"}, headers=AUTH)
        assert response.status_code == 200
        assert response.json()["name"] == "Euro (EU)"

    def test_not_found_returns_404(self, client, mock_service):
        mock_service.update.return_value = None
        assert client.patch("/finance/currencies/XYZ", json={"name": "X"}, headers=AUTH).status_code == 404

    def test_requires_auth(self, client):
        assert client.patch("/finance/currencies/EUR", json={"name": "X"}).status_code == 403


class TestDeleteCurrency:
    def test_deletes_returns_204(self, client):
        assert client.delete("/finance/currencies/EUR", headers=AUTH).status_code == 204

    def test_not_found_returns_404(self, client, mock_service):
        mock_service.delete.return_value = False
        assert client.delete("/finance/currencies/XYZ", headers=AUTH).status_code == 404

    def test_requires_auth(self, client):
        assert client.delete("/finance/currencies/EUR").status_code == 403

    def test_service_called_with_correct_code(self, client, mock_service):
        client.delete("/finance/currencies/PLN", headers=AUTH)
        mock_service.delete.assert_called_once_with("PLN")
