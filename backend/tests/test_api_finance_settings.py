import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock
from app.features.finance.settings.schemas import FinanceSettingsRead

AUTH = {"Authorization": "Bearer test-api-token"}


@pytest.fixture
def mock_service():
    svc = AsyncMock()
    svc.get.return_value = FinanceSettingsRead(cycle_start_day=1)
    svc.update.return_value = FinanceSettingsRead(cycle_start_day=25)
    return svc


@pytest.fixture
def client(mock_service):
    from app.main import app
    from app.dependencies import get_finance_settings_service
    app.dependency_overrides[get_finance_settings_service] = lambda: mock_service
    yield TestClient(app)
    app.dependency_overrides.clear()


class TestGetFinanceSettings:
    def test_returns_current_settings(self, client):
        response = client.get("/finance/settings", headers=AUTH)
        assert response.status_code == 200
        assert response.json() == {"cycle_start_day": 1}

    def test_requires_auth(self, client):
        assert client.get("/finance/settings").status_code == 403


class TestUpdateFinanceSettings:
    def test_updates_and_returns_200(self, client, mock_service):
        response = client.put("/finance/settings", json={"cycle_start_day": 25}, headers=AUTH)
        assert response.status_code == 200
        assert response.json() == {"cycle_start_day": 25}
        mock_service.update.assert_awaited_once()

    def test_rejects_out_of_range_day(self, client):
        response = client.put("/finance/settings", json={"cycle_start_day": 29}, headers=AUTH)
        assert response.status_code == 422

    def test_rejects_zero_day(self, client):
        response = client.put("/finance/settings", json={"cycle_start_day": 0}, headers=AUTH)
        assert response.status_code == 422

    def test_requires_auth(self, client):
        assert client.put("/finance/settings", json={"cycle_start_day": 25}).status_code == 403
