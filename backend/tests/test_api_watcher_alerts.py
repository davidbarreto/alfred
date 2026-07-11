import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient
from datetime import datetime

from app.features.watcher.tables import Alert

AUTH = {"Authorization": "Bearer test-api-token"}


def _alert_mock(id=1, execution_id=1, status="pending", **overrides):
    alert = MagicMock(spec=Alert)
    alert.id = id
    alert.execution_id = execution_id
    alert.status = status
    alert.created_at = datetime(2024, 1, 1)
    alert.resolved_at = overrides.get("resolved_at")
    execution = MagicMock()
    execution.config_snapshot = {"name": "Test Watcher", "target": "Target"}
    execution.result = "matched text"
    alert.execution = execution
    return alert


@pytest.fixture
def client():
    from app.main import app
    from app.db.session import get_session

    async def mock_session():
        yield AsyncMock()

    app.dependency_overrides[get_session] = mock_session
    yield TestClient(app)
    app.dependency_overrides.clear()


class TestListPendingAlertsForNotification:
    def test_returns_enriched_fields(self, client):
        alerts = [_alert_mock(id=1), _alert_mock(id=2)]
        with patch(
            "app.api.routes.watcher.alerts.get_pending_alerts_with_context",
            new=AsyncMock(return_value=alerts),
        ):
            response = client.get("/watcher/alerts/pending", headers=AUTH)
        assert response.status_code == 200
        body = response.json()
        assert len(body) == 2
        assert body[0]["watcher_name"] == "Test Watcher"
        assert body[0]["target"] == "Target"
        assert body[0]["result"] == "matched text"

    def test_requires_auth(self, client):
        response = client.get("/watcher/alerts/pending")
        assert response.status_code == 403


class TestResolveAlerts:
    def test_resolves_and_returns_alerts(self, client):
        alerts = [_alert_mock(id=1, status="done"), _alert_mock(id=2, status="done")]
        with patch(
            "app.api.routes.watcher.alerts.resolve_alerts", new=AsyncMock(return_value=alerts)
        ) as mock_resolve:
            response = client.post(
                "/watcher/alerts/resolve", json={"alert_ids": [1, 2]}, headers=AUTH
            )
        assert response.status_code == 200
        body = response.json()
        assert len(body) == 2
        assert all(a["status"] == "done" for a in body)
        mock_resolve.assert_called_once()

    def test_requires_auth(self, client):
        response = client.post("/watcher/alerts/resolve", json={"alert_ids": [1]})
        assert response.status_code == 403
