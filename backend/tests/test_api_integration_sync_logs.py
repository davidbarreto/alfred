import pytest
from datetime import datetime, timezone
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch

from app.integrations.sync_log.schemas import SyncLogRead

AUTH = {"Authorization": "Bearer test-api-token"}


def _sync_log_read(**kwargs):
    defaults = dict(
        id=1,
        provider="notion",
        operation="create",
        entity_type="task",
        provider_entity_id="page-abc",
        status="ok",
        request_payload={"properties": {"title": "Buy milk"}},
        response_payload={"id": "page-abc", "object": "page"},
        error=None,
        created_at=datetime(2026, 6, 12, 10, 0, 0, tzinfo=timezone.utc),
    )
    defaults.update(kwargs)
    return SyncLogRead(**defaults)


@pytest.fixture
def client():
    from app.main import app
    return TestClient(app)


class TestListSyncLogs:
    def test_returns_list(self, client):
        log = _sync_log_read()
        with patch(
            "app.api.routes.integrations.sync_logs.get_sync_logs",
            new=AsyncMock(return_value=[log]),
        ):
            response = client.get("/integration/sync-logs/", headers=AUTH)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert data[0]["provider"] == "notion"
        assert data[0]["entity_type"] == "task"

    def test_requires_auth(self, client):
        assert client.get("/integration/sync-logs/").status_code == 403

    def test_wrong_token_rejected(self, client):
        assert client.get("/integration/sync-logs/", headers={"Authorization": "Bearer bad"}).status_code == 401

    def test_response_shape(self, client):
        log = _sync_log_read()
        with patch(
            "app.api.routes.integrations.sync_logs.get_sync_logs",
            new=AsyncMock(return_value=[log]),
        ):
            response = client.get("/integration/sync-logs/", headers=AUTH)
        entry = response.json()[0]
        for field in ("id", "provider", "operation", "entity_type", "provider_entity_id", "status", "request_payload", "response_payload", "error", "created_at"):
            assert field in entry

    def test_filters_forwarded(self, client):
        mock_get = AsyncMock(return_value=[])
        with patch("app.api.routes.integrations.sync_logs.get_sync_logs", new=mock_get):
            client.get("/integration/sync-logs/?provider=notion&entity_type=task&status=ok", headers=AUTH)
        _, kwargs = mock_get.call_args
        assert kwargs["provider"] == "notion"
        assert kwargs["entity_type"] == "task"
        assert kwargs["status"] == "ok"

    def test_q_filter_forwarded(self, client):
        mock_get = AsyncMock(return_value=[])
        with patch("app.api.routes.integrations.sync_logs.get_sync_logs", new=mock_get):
            client.get("/integration/sync-logs/?q=timeout", headers=AUTH)
        _, kwargs = mock_get.call_args
        assert kwargs["q"] == "timeout"

    def test_operation_filter_forwarded(self, client):
        mock_get = AsyncMock(return_value=[])
        with patch("app.api.routes.integrations.sync_logs.get_sync_logs", new=mock_get):
            client.get("/integration/sync-logs/?operation=create", headers=AUTH)
        _, kwargs = mock_get.call_args
        assert kwargs["operation"] == "create"

    def test_after_filter_forwarded(self, client):
        mock_get = AsyncMock(return_value=[])
        with patch("app.api.routes.integrations.sync_logs.get_sync_logs", new=mock_get):
            client.get("/integration/sync-logs/?after=2026-06-01T00:00:00Z", headers=AUTH)
        _, kwargs = mock_get.call_args
        assert kwargs["after"] is not None

    def test_before_filter_forwarded(self, client):
        mock_get = AsyncMock(return_value=[])
        with patch("app.api.routes.integrations.sync_logs.get_sync_logs", new=mock_get):
            client.get("/integration/sync-logs/?before=2026-06-12T00:00:00Z", headers=AUTH)
        _, kwargs = mock_get.call_args
        assert kwargs["before"] is not None


class TestGetSyncLog:
    def test_returns_log(self, client):
        log = _sync_log_read(id=1)
        with patch(
            "app.api.routes.integrations.sync_logs.get_sync_log",
            new=AsyncMock(return_value=log),
        ):
            response = client.get("/integration/sync-logs/1", headers=AUTH)
        assert response.status_code == 200
        assert response.json()["id"] == 1

    def test_not_found_returns_404(self, client):
        with patch(
            "app.api.routes.integrations.sync_logs.get_sync_log",
            new=AsyncMock(return_value=None),
        ):
            response = client.get("/integration/sync-logs/99", headers=AUTH)
        assert response.status_code == 404
