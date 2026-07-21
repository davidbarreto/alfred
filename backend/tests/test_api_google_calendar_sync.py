from datetime import date
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.features.organizer.calendar_events.schemas import CalendarSyncResult

AUTH = {"Authorization": "Bearer test-api-token"}


@pytest.fixture
def mock_service():
    svc = AsyncMock()
    svc.sync.return_value = CalendarSyncResult(
        created=2, updated=1, start=date(2026, 7, 21), end=date(2026, 10, 21)
    )
    return svc


@pytest.fixture
def client(mock_service):
    from app.main import app
    from app.dependencies import get_calendar_event_service

    app.dependency_overrides[get_calendar_event_service] = lambda: mock_service
    yield TestClient(app)
    app.dependency_overrides.clear()


class TestSyncCalendar:
    def test_syncs_with_default_range(self, client, mock_service):
        response = client.post("/integration/google-calendar/sync", headers=AUTH)
        assert response.status_code == 200
        data = response.json()
        assert data == {"created": 2, "updated": 1, "start": "2026-07-21", "end": "2026-10-21"}
        mock_service.sync.assert_called_once_with(None, None)

    def test_syncs_with_explicit_range(self, client, mock_service):
        response = client.post(
            "/integration/google-calendar/sync?start=2026-08-01&end=2026-08-31", headers=AUTH
        )
        assert response.status_code == 200
        mock_service.sync.assert_called_once_with(date(2026, 8, 1), date(2026, 8, 31))

    def test_requires_auth(self, client):
        response = client.post("/integration/google-calendar/sync")
        assert response.status_code == 403
