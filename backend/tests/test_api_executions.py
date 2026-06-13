import pytest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient
from datetime import datetime

AUTH = {"Authorization": "Bearer test-api-token"}


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


class TestListExecutions:
    def test_returns_empty_list(self, client):
        with patch("app.api.routes.monitoring.executions.get_all_executions", new=AsyncMock(return_value=[])):
            response = client.get("/monitoring/executions/", headers=AUTH)
        assert response.status_code == 200
        assert response.json() == []

    def test_returns_execution_list(self, client):
        from app.features.monitoring.schemas import ExecutionRead
        executions = [ExecutionRead(**_execution_dict(id=i, config_id=1)) for i in range(3)]
        with patch("app.api.routes.monitoring.executions.get_all_executions", new=AsyncMock(return_value=executions)):
            response = client.get("/monitoring/executions/", headers=AUTH)
        assert response.status_code == 200
        assert len(response.json()) == 3

    def test_requires_auth(self, client):
        response = client.get("/monitoring/executions/")
        assert response.status_code == 403

    def test_filter_by_config_id(self, client):
        with patch("app.api.routes.monitoring.executions.get_all_executions", new=AsyncMock(return_value=[])) as mock_get:
            client.get("/monitoring/executions/?config_id=5", headers=AUTH)
            _, kwargs = mock_get.call_args
            assert kwargs["filters"].config_id == 5

    def test_filter_by_status(self, client):
        with patch("app.api.routes.monitoring.executions.get_all_executions", new=AsyncMock(return_value=[])) as mock_get:
            client.get("/monitoring/executions/?status=found", headers=AUTH)
            _, kwargs = mock_get.call_args
            assert kwargs["filters"].status == "found"

    def test_filter_by_before_date(self, client):
        with patch("app.api.routes.monitoring.executions.get_all_executions", new=AsyncMock(return_value=[])) as mock_get:
            client.get("/monitoring/executions/?before_date=2026-06-01T00:00:00", headers=AUTH)
            _, kwargs = mock_get.call_args
            assert kwargs["filters"].before_date is not None

    def test_filter_by_after_date(self, client):
        with patch("app.api.routes.monitoring.executions.get_all_executions", new=AsyncMock(return_value=[])) as mock_get:
            client.get("/monitoring/executions/?after_date=2026-01-01T00:00:00", headers=AUTH)
            _, kwargs = mock_get.call_args
            assert kwargs["filters"].after_date is not None

    def test_filter_by_result(self, client):
        with patch("app.api.routes.monitoring.executions.get_all_executions", new=AsyncMock(return_value=[])) as mock_get:
            client.get("/monitoring/executions/?result=some+text", headers=AUTH)
            _, kwargs = mock_get.call_args
            assert kwargs["filters"].result == "some text"

    def test_default_pagination(self, client):
        with patch("app.api.routes.monitoring.executions.get_all_executions", new=AsyncMock(return_value=[])) as mock_get:
            client.get("/monitoring/executions/", headers=AUTH)
            _, kwargs = mock_get.call_args
            assert kwargs["filters"].skip == 0
            assert kwargs["filters"].limit == 20

    def test_execution_response_shape(self, client):
        from app.features.monitoring.schemas import ExecutionRead
        execution = ExecutionRead(**_execution_dict(id=7, config_id=3, status="found", result="matched"))
        with patch("app.api.routes.monitoring.executions.get_all_executions", new=AsyncMock(return_value=[execution])):
            response = client.get("/monitoring/executions/", headers=AUTH)
        data = response.json()[0]
        assert data["id"] == 7
        assert data["config_id"] == 3
        assert data["status"] == "found"
        assert data["result"] == "matched"
