import pytest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient
from datetime import datetime

AUTH = {"Authorization": "Bearer test-api-token"}


def _alert_dict(id=1, execution_id=1, **overrides):
    base = dict(
        id=id,
        execution_id=execution_id,
        status="pending",
        created_at=datetime(2024, 1, 1).isoformat(),
        resolved_at=None,
    )
    base.update(overrides)
    return base


@pytest.fixture
def client():
    from app.main import app
    from app.db.session import get_session

    async def mock_session():
        yield AsyncMock()

    app.dependency_overrides[get_session] = mock_session
    yield TestClient(app)
    app.dependency_overrides.clear()


class TestListAlerts:
    def test_returns_empty_list(self, client):
        with patch("app.api.routes.monitoring.alerts.get_alerts", new=AsyncMock(return_value=[])):
            response = client.get("/alerts/", headers=AUTH)
        assert response.status_code == 200
        assert response.json() == []

    def test_returns_alert_list(self, client):
        from app.features.monitoring.schemas import AlertRead
        alerts = [AlertRead(**_alert_dict(id=i)) for i in range(3)]
        with patch("app.api.routes.monitoring.alerts.get_alerts", new=AsyncMock(return_value=alerts)):
            response = client.get("/alerts/", headers=AUTH)
        assert response.status_code == 200
        assert len(response.json()) == 3

    def test_requires_auth(self, client):
        response = client.get("/alerts/")
        assert response.status_code == 403

    def test_filters_by_status(self, client):
        with patch("app.api.routes.monitoring.alerts.get_alerts", new=AsyncMock(return_value=[])) as mock_get:
            client.get("/alerts/?status=pending", headers=AUTH)
            _, kwargs = mock_get.call_args
            assert kwargs.get("status") == "pending"

    def test_filters_by_monitor_id(self, client):
        with patch("app.api.routes.monitoring.alerts.get_alerts", new=AsyncMock(return_value=[])) as mock_get:
            client.get("/alerts/?monitor_id=5", headers=AUTH)
            _, kwargs = mock_get.call_args
            assert kwargs.get("monitor_id") == 5

    def test_filters_combined(self, client):
        with patch("app.api.routes.monitoring.alerts.get_alerts", new=AsyncMock(return_value=[])) as mock_get:
            client.get("/alerts/?status=done&monitor_id=3&skip=10&limit=5", headers=AUTH)
            _, kwargs = mock_get.call_args
            assert kwargs.get("status") == "done"
            assert kwargs.get("monitor_id") == 3
            assert kwargs.get("skip") == 10
            assert kwargs.get("limit") == 5

    def test_invalid_status_returns_422(self, client):
        response = client.get("/alerts/?status=invalid", headers=AUTH)
        assert response.status_code == 422

    def test_alert_response_shape(self, client):
        from app.features.monitoring.schemas import AlertRead
        alert = AlertRead(**_alert_dict(id=1, execution_id=10, status="pending"))
        with patch("app.api.routes.monitoring.alerts.get_alerts", new=AsyncMock(return_value=[alert])):
            response = client.get("/alerts/", headers=AUTH)
        data = response.json()[0]
        assert data["id"] == 1
        assert data["execution_id"] == 10
        assert data["status"] == "pending"
        assert data["resolved_at"] is None
