from datetime import datetime
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.features.core.sessions.schemas import SessionRead

AUTH = {"Authorization": "Bearer test-api-token"}


def _session_read(**kwargs):
    defaults = dict(
        id=1,
        source=None,
        external_id=None,
        summary=None,
        last_interaction_at=datetime(2026, 1, 1),
        created_at=datetime(2026, 1, 1),
        finished_at=None,
    )
    defaults.update(kwargs)
    return SessionRead(**defaults)


@pytest.fixture
def mock_service():
    svc = AsyncMock()
    svc.get.return_value = _session_read()
    svc.list.return_value = [_session_read()]
    svc.create.return_value = _session_read(id=2, summary="Morning briefing")
    svc.finish.return_value = _session_read(finished_at=datetime(2026, 1, 1, 12))
    svc.delete.return_value = True
    return svc


@pytest.fixture
def client(mock_service):
    from app.main import app
    from app.dependencies import get_session_service
    app.dependency_overrides[get_session_service] = lambda: mock_service
    yield TestClient(app)
    app.dependency_overrides.clear()


class TestListSessions:
    def test_returns_list(self, client):
        response = client.get("/core/sessions/", headers=AUTH)
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_requires_auth(self, client):
        assert client.get("/core/sessions/").status_code == 403

    def test_active_only_filter_passed_to_service(self, client, mock_service):
        client.get("/core/sessions/?active_only=true", headers=AUTH)
        filters = mock_service.list.call_args[0][0]
        assert filters.active_only is True


class TestGetSession:
    def test_returns_session(self, client):
        response = client.get("/core/sessions/1", headers=AUTH)
        assert response.status_code == 200
        assert response.json()["id"] == 1

    def test_returns_404_when_not_found(self, client, mock_service):
        mock_service.get.return_value = None
        assert client.get("/core/sessions/999", headers=AUTH).status_code == 404


class TestCreateSession:
    def test_creates_and_returns_201(self, client):
        response = client.post("/core/sessions/", json={"summary": "Morning briefing"}, headers=AUTH)
        assert response.status_code == 201
        assert response.json()["summary"] == "Morning briefing"

    def test_creates_without_summary(self, client):
        response = client.post("/core/sessions/", json={}, headers=AUTH)
        assert response.status_code == 201

    def test_response_includes_correlation_fields(self, client):
        body = client.post("/core/sessions/", json={}, headers=AUTH).json()
        assert "source" in body
        assert "external_id" in body
        assert "last_interaction_at" in body


class TestFinishSession:
    def test_finishes_session(self, client):
        response = client.post("/core/sessions/1/finish", headers=AUTH)
        assert response.status_code == 200
        assert response.json()["finished_at"] is not None

    def test_returns_404_when_not_found(self, client, mock_service):
        mock_service.finish.return_value = None
        assert client.post("/core/sessions/999/finish", headers=AUTH).status_code == 404


class TestDeleteSession:
    def test_deletes_and_returns_204(self, client):
        assert client.delete("/core/sessions/1", headers=AUTH).status_code == 204

    def test_returns_404_when_not_found(self, client, mock_service):
        mock_service.delete.return_value = False
        assert client.delete("/core/sessions/999", headers=AUTH).status_code == 404
