import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient
from datetime import datetime

AUTH = {"Authorization": "Bearer test-api-token"}


def _watcher_dict(id=1, **overrides):
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


def _execution_dict(id=1, config_id=1, **overrides):
    base = dict(
        id=id,
        config_id=config_id,
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


class TestGetWatchers:
    def test_returns_empty_list(self, client):
        with patch("app.api.routes.watcher.watchers.get_watchers", new=AsyncMock(return_value=[])):
            response = client.get("/watcher/configs/", headers=AUTH)
        assert response.status_code == 200
        assert response.json() == []

    def test_returns_monitor_list(self, client):
        from app.features.watcher.schemas import WatcherRead
        monitors = [WatcherRead(**_watcher_dict(id=i)) for i in range(2)]
        with patch("app.api.routes.watcher.watchers.get_watchers", new=AsyncMock(return_value=monitors)):
            response = client.get("/watcher/configs/", headers=AUTH)
        assert response.status_code == 200
        assert len(response.json()) == 2

    def test_requires_auth(self, client):
        response = client.get("/watcher/configs/")
        assert response.status_code == 403


class TestGetWatcher:
    def test_found_returns_200(self, client):
        from app.features.watcher.schemas import WatcherRead
        monitor = WatcherRead(**_watcher_dict())
        with patch("app.api.routes.watcher.watchers.get_watcher", new=AsyncMock(return_value=monitor)):
            response = client.get("/watcher/configs/1", headers=AUTH)
        assert response.status_code == 200
        assert response.json()["id"] == 1

    def test_not_found_returns_404(self, client):
        with patch("app.api.routes.watcher.watchers.get_watcher", new=AsyncMock(return_value=None)):
            response = client.get("/watcher/configs/999", headers=AUTH)
        assert response.status_code == 404
        assert response.json()["detail"] == "Watcher not found"

    def test_requires_auth(self, client):
        response = client.get("/watcher/configs/1")
        assert response.status_code == 403


class TestCreateWatcher:
    def test_creates_monitor(self, client):
        from app.features.watcher.schemas import WatcherRead
        monitor = WatcherRead(**_watcher_dict(id=10, name="New Monitor"))
        with patch("app.api.routes.watcher.watchers.create_monitor", new=AsyncMock(return_value=monitor)):
            payload = {
                "name": "New Monitor",
                "url": "http://example.com",
                "target": "Target",
                "type": "html_static",
            }
            response = client.post("/watcher/configs/", json=payload, headers=AUTH)
        assert response.status_code == 200
        assert response.json()["name"] == "New Monitor"

    def test_requires_auth(self, client):
        payload = {"name": "M", "url": "http://x.com", "target": "T", "type": "html_static"}
        response = client.post("/watcher/configs/", json=payload)
        assert response.status_code == 403


class TestDeleteWatcher:
    def test_found_returns_monitor(self, client):
        from app.features.watcher.schemas import WatcherRead
        monitor = WatcherRead(**_watcher_dict())
        with patch("app.api.routes.watcher.watchers.delete_monitor", new=AsyncMock(return_value=monitor)):
            response = client.delete("/watcher/configs/1", headers=AUTH)
        assert response.status_code == 200

    def test_not_found_returns_404(self, client):
        with patch("app.api.routes.watcher.watchers.delete_monitor", new=AsyncMock(return_value=None)):
            response = client.delete("/watcher/configs/999", headers=AUTH)
        assert response.status_code == 404

    def test_requires_auth(self, client):
        response = client.delete("/watcher/configs/1")
        assert response.status_code == 403


class TestUpdateWatcher:
    def test_found_returns_updated(self, client):
        from app.features.watcher.schemas import WatcherRead
        monitor = WatcherRead(**_watcher_dict(name="Updated"))
        with patch("app.api.routes.watcher.watchers.update_monitor", new=AsyncMock(return_value=monitor)):
            response = client.patch("/watcher/configs/1", json={"name": "Updated"}, headers=AUTH)
        assert response.status_code == 200
        assert response.json()["name"] == "Updated"

    def test_not_found_returns_404(self, client):
        with patch("app.api.routes.watcher.watchers.update_monitor", new=AsyncMock(return_value=None)):
            response = client.patch("/watcher/configs/999", json={"name": "X"}, headers=AUTH)
        assert response.status_code == 404

    def test_requires_auth(self, client):
        response = client.patch("/watcher/configs/1", json={"name": "X"})
        assert response.status_code == 403


class TestRunActiveWatchers:
    def test_runs_all_and_returns_executions(self, client):
        from app.features.watcher.schemas import ExecutionRead
        executions = [ExecutionRead(**_execution_dict(id=i, config_id=1)) for i in range(2)]
        with patch("app.api.routes.watcher.watchers.MonitorService.run_due", new=AsyncMock(return_value=executions)):
            response = client.post("/watcher/configs/run", headers=AUTH)
        assert response.status_code == 200
        assert len(response.json()) == 2

    def test_requires_auth(self, client):
        response = client.post("/watcher/configs/run")
        assert response.status_code == 403


class TestRunWatcherById:
    def test_found_returns_execution(self, client):
        from app.features.watcher.schemas import ExecutionRead
        execution = ExecutionRead(**_execution_dict())
        with patch(
            "app.api.routes.watcher.watchers.MonitorService.run_monitor_by_id",
            new=AsyncMock(return_value=execution),
        ):
            response = client.post("/watcher/configs/1/run", headers=AUTH)
        assert response.status_code == 200
        assert response.json()["config_id"] == 1

    def test_not_found_returns_404(self, client):
        with patch(
            "app.api.routes.watcher.watchers.MonitorService.run_monitor_by_id",
            new=AsyncMock(return_value=None),
        ):
            response = client.post("/watcher/configs/999/run", headers=AUTH)
        assert response.status_code == 404

    def test_requires_auth(self, client):
        response = client.post("/watcher/configs/1/run")
        assert response.status_code == 403


class TestGetWatcherExecutions:
    def test_found_returns_executions(self, client):
        from app.features.watcher.schemas import ExecutionRead, WatcherRead
        watcher = WatcherRead(**_watcher_dict())
        executions = [ExecutionRead(**_execution_dict(id=i)) for i in range(3)]
        with patch("app.api.routes.watcher.watchers.get_watcher", new=AsyncMock(return_value=watcher)):
            with patch("app.api.routes.watcher.watchers.get_executions", new=AsyncMock(return_value=executions)):
                response = client.get("/watcher/configs/1/executions", headers=AUTH)
        assert response.status_code == 200
        assert len(response.json()) == 3

    def test_watcher_not_found_returns_404(self, client):
        with patch("app.api.routes.watcher.watchers.get_watcher", new=AsyncMock(return_value=None)):
            response = client.get("/watcher/configs/999/executions", headers=AUTH)
        assert response.status_code == 404

    def test_requires_auth(self, client):
        response = client.get("/watcher/configs/1/executions")
        assert response.status_code == 403

    def test_limit_parameter(self, client):
        from app.features.watcher.schemas import WatcherRead
        watcher = WatcherRead(**_watcher_dict())
        with patch("app.api.routes.watcher.watchers.get_watcher", new=AsyncMock(return_value=watcher)):
            with patch("app.api.routes.watcher.watchers.get_executions", new=AsyncMock(return_value=[])) as mock_exec:
                client.get("/watcher/configs/1/executions?limit=5", headers=AUTH)
                _, kwargs = mock_exec.call_args
                assert kwargs.get("limit") == 5
