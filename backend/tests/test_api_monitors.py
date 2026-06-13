import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient
from datetime import datetime

AUTH = {"Authorization": "Bearer test-api-token"}


def _monitor_dict(id=1, **overrides):
    base = dict(
        id=id,
        name="Test Monitor",
        description="desc",
        enabled=True,
        type="html_static",
        url="http://example.com",
        selector=".content",
        json_path=None,
        target="Target",
        case_sensitive=True,
        timeout=10,
        page_size=32,
        max_pages=None,
        request_delay=0,
        wait_selector=None,
    )
    base.update(overrides)
    return base


def _execution_dict(id=1, monitor_id=1, **overrides):
    base = dict(
        id=id,
        monitor_id=monitor_id,
        status="not_found",
        result=None,
        error=None,
        config_snapshot={"type": "html_static", "url": "http://example.com"},
        created_at=datetime(2024, 1, 1).isoformat(),
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


class TestGetMonitors:
    def test_returns_empty_list(self, client):
        with patch("app.api.routes.monitoring.monitors.get_monitors", new=AsyncMock(return_value=[])):
            response = client.get("/monitors/", headers=AUTH)
        assert response.status_code == 200
        assert response.json() == []

    def test_returns_monitor_list(self, client):
        from app.features.monitoring.schemas import MonitorRead
        monitors = [MonitorRead(**_monitor_dict(id=i)) for i in range(2)]
        with patch("app.api.routes.monitoring.monitors.get_monitors", new=AsyncMock(return_value=monitors)):
            response = client.get("/monitors/", headers=AUTH)
        assert response.status_code == 200
        assert len(response.json()) == 2

    def test_requires_auth(self, client):
        response = client.get("/monitors/")
        assert response.status_code == 403


class TestGetMonitor:
    def test_found_returns_200(self, client):
        from app.features.monitoring.schemas import MonitorRead
        monitor = MonitorRead(**_monitor_dict())
        with patch("app.api.routes.monitoring.monitors.get_monitor", new=AsyncMock(return_value=monitor)):
            response = client.get("/monitors/1", headers=AUTH)
        assert response.status_code == 200
        assert response.json()["id"] == 1

    def test_not_found_returns_404(self, client):
        with patch("app.api.routes.monitoring.monitors.get_monitor", new=AsyncMock(return_value=None)):
            response = client.get("/monitors/999", headers=AUTH)
        assert response.status_code == 404
        assert response.json()["detail"] == "Monitor not found"

    def test_requires_auth(self, client):
        response = client.get("/monitors/1")
        assert response.status_code == 403


class TestCreateMonitor:
    def test_creates_monitor(self, client):
        from app.features.monitoring.schemas import MonitorRead
        monitor = MonitorRead(**_monitor_dict(id=10, name="New Monitor"))
        with patch("app.api.routes.monitoring.monitors.create_monitor", new=AsyncMock(return_value=monitor)):
            payload = {
                "name": "New Monitor",
                "url": "http://example.com",
                "target": "Target",
                "type": "html_static",
            }
            response = client.post("/monitors/", json=payload, headers=AUTH)
        assert response.status_code == 200
        assert response.json()["name"] == "New Monitor"

    def test_requires_auth(self, client):
        payload = {"name": "M", "url": "http://x.com", "target": "T", "type": "html_static"}
        response = client.post("/monitors/", json=payload)
        assert response.status_code == 403


class TestDeleteMonitor:
    def test_found_returns_monitor(self, client):
        from app.features.monitoring.schemas import MonitorRead
        monitor = MonitorRead(**_monitor_dict())
        with patch("app.api.routes.monitoring.monitors.delete_monitor", new=AsyncMock(return_value=monitor)):
            response = client.delete("/monitors/1", headers=AUTH)
        assert response.status_code == 200

    def test_not_found_returns_404(self, client):
        with patch("app.api.routes.monitoring.monitors.delete_monitor", new=AsyncMock(return_value=None)):
            response = client.delete("/monitors/999", headers=AUTH)
        assert response.status_code == 404

    def test_requires_auth(self, client):
        response = client.delete("/monitors/1")
        assert response.status_code == 403


class TestUpdateMonitor:
    def test_found_returns_updated(self, client):
        from app.features.monitoring.schemas import MonitorRead
        monitor = MonitorRead(**_monitor_dict(name="Updated"))
        with patch("app.api.routes.monitoring.monitors.update_monitor", new=AsyncMock(return_value=monitor)):
            response = client.patch("/monitors/1", json={"name": "Updated"}, headers=AUTH)
        assert response.status_code == 200
        assert response.json()["name"] == "Updated"

    def test_not_found_returns_404(self, client):
        with patch("app.api.routes.monitoring.monitors.update_monitor", new=AsyncMock(return_value=None)):
            response = client.patch("/monitors/999", json={"name": "X"}, headers=AUTH)
        assert response.status_code == 404

    def test_requires_auth(self, client):
        response = client.patch("/monitors/1", json={"name": "X"})
        assert response.status_code == 403


class TestRunActiveMonitors:
    def test_runs_all_and_returns_executions(self, client):
        from app.features.monitoring.schemas import ExecutionRead
        executions = [ExecutionRead(**_execution_dict(id=i, monitor_id=1)) for i in range(2)]
        with patch("app.api.routes.monitoring.monitors.MonitorService.run_due", new=AsyncMock(return_value=executions)):
            response = client.post("/monitors/run", headers=AUTH)
        assert response.status_code == 200
        assert len(response.json()) == 2

    def test_requires_auth(self, client):
        response = client.post("/monitors/run")
        assert response.status_code == 403


class TestRunMonitorById:
    def test_found_returns_execution(self, client):
        from app.features.monitoring.schemas import ExecutionRead
        execution = ExecutionRead(**_execution_dict())
        with patch(
            "app.api.routes.monitoring.monitors.MonitorService.run_monitor_by_id",
            new=AsyncMock(return_value=execution),
        ):
            response = client.post("/monitors/1/run", headers=AUTH)
        assert response.status_code == 200
        assert response.json()["monitor_id"] == 1

    def test_not_found_returns_404(self, client):
        with patch(
            "app.api.routes.monitoring.monitors.MonitorService.run_monitor_by_id",
            new=AsyncMock(return_value=None),
        ):
            response = client.post("/monitors/999/run", headers=AUTH)
        assert response.status_code == 404

    def test_requires_auth(self, client):
        response = client.post("/monitors/1/run")
        assert response.status_code == 403


class TestGetMonitorExecutions:
    def test_found_returns_executions(self, client):
        from app.features.monitoring.schemas import ExecutionRead, MonitorRead
        monitor = MonitorRead(**_monitor_dict())
        executions = [ExecutionRead(**_execution_dict(id=i)) for i in range(3)]
        with patch("app.api.routes.monitoring.monitors.get_monitor", new=AsyncMock(return_value=monitor)):
            with patch("app.api.routes.monitoring.monitors.get_executions", new=AsyncMock(return_value=executions)):
                response = client.get("/monitors/1/executions", headers=AUTH)
        assert response.status_code == 200
        assert len(response.json()) == 3

    def test_monitor_not_found_returns_404(self, client):
        with patch("app.api.routes.monitoring.monitors.get_monitor", new=AsyncMock(return_value=None)):
            response = client.get("/monitors/999/executions", headers=AUTH)
        assert response.status_code == 404

    def test_requires_auth(self, client):
        response = client.get("/monitors/1/executions")
        assert response.status_code == 403

    def test_limit_parameter(self, client):
        from app.features.monitoring.schemas import MonitorRead
        monitor = MonitorRead(**_monitor_dict())
        with patch("app.api.routes.monitoring.monitors.get_monitor", new=AsyncMock(return_value=monitor)):
            with patch("app.api.routes.monitoring.monitors.get_executions", new=AsyncMock(return_value=[])) as mock_exec:
                client.get("/monitors/1/executions?limit=5", headers=AUTH)
                _, kwargs = mock_exec.call_args
                assert kwargs.get("limit") == 5
