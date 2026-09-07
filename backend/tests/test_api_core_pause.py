from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

AUTH = {"Authorization": "Bearer test-api-token"}


@pytest.fixture
def mock_service():
    return AsyncMock()


@pytest.fixture
def client(mock_service):
    from app.main import app
    from app.dependencies import get_global_pause_service
    app.dependency_overrides[get_global_pause_service] = lambda: mock_service
    yield TestClient(app)
    app.dependency_overrides.clear()


class TestGetPauseState:
    def test_returns_state(self, client, mock_service):
        from app.features.core.pause.schemas import PauseStateRead

        mock_service.get_state.return_value = PauseStateRead(paused=False, paused_at=None)

        response = client.get("/core/pause", headers=AUTH)

        assert response.status_code == 200
        assert response.json() == {"paused": False, "paused_at": None}

    def test_requires_auth(self, client):
        assert client.get("/core/pause").status_code == 403


class TestPause:
    def test_pauses(self, client, mock_service):
        from app.features.core.pause.schemas import PauseStateRead

        now = datetime(2026, 9, 7, 12, 0, tzinfo=timezone.utc)
        mock_service.pause.return_value = PauseStateRead(paused=True, paused_at=now)

        response = client.post("/core/pause", headers=AUTH)

        assert response.status_code == 200
        assert response.json()["paused"] is True

    def test_rejects_when_already_paused(self, client, mock_service):
        mock_service.pause.side_effect = HTTPException(status_code=400, detail="Already paused")

        response = client.post("/core/pause", headers=AUTH)

        assert response.status_code == 400

    def test_requires_auth(self, client):
        assert client.post("/core/pause").status_code == 403


class TestResume:
    def test_resumes(self, client, mock_service):
        from app.features.core.pause.schemas import PauseResumeRead

        mock_service.resume.return_value = PauseResumeRead(
            resumed_at=datetime(2026, 9, 7, 12, 0, tzinfo=timezone.utc),
            tasks_urgency_reset=3,
            tasks_deadline_shifted=1,
        )

        response = client.post("/core/pause/resume", headers=AUTH)

        assert response.status_code == 200
        body = response.json()
        assert body["tasks_urgency_reset"] == 3
        assert body["tasks_deadline_shifted"] == 1

    def test_rejects_when_not_paused(self, client, mock_service):
        mock_service.resume.side_effect = HTTPException(status_code=400, detail="Not paused")

        response = client.post("/core/pause/resume", headers=AUTH)

        assert response.status_code == 400

    def test_requires_auth(self, client):
        assert client.post("/core/pause/resume").status_code == 403
