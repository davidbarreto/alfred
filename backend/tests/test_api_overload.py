from datetime import date
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.features.core.overload.schemas import OverloadDayRead, OverloadStatusRead

AUTH = {"Authorization": "Bearer test-api-token"}


@pytest.fixture
def mock_service():
    return AsyncMock()


@pytest.fixture
def client(mock_service):
    from app.main import app
    from app.dependencies import get_overload_service

    app.dependency_overrides[get_overload_service] = lambda: mock_service
    yield TestClient(app)
    app.dependency_overrides.clear()


class TestGetStatus:
    def test_returns_status(self, client, mock_service):
        mock_service.status.return_value = OverloadStatusRead(
            level="overloaded", overdue=7, urgent=5, active=20,
            overdue_threshold=5, urgent_threshold=4, streak_days=3,
        )

        response = client.get("/core/overload/status", headers=AUTH)

        assert response.status_code == 200
        body = response.json()
        assert body["level"] == "overloaded"
        assert body["streak_days"] == 3
        assert body["overdue_threshold"] == 5

    def test_requires_auth(self, client):
        assert client.get("/core/overload/status").status_code == 403


class TestGetHistory:
    def test_returns_history_with_default_window(self, client, mock_service):
        mock_service.history.return_value = [
            OverloadDayRead(
                date=date(2026, 10, 22), level="elevated", peak_overdue=3, peak_urgent=2, peak_active=15,
                reminder_runs=15, tasks_listed=20, tasks_omitted=0, first_overloaded_at=None,
            )
        ]

        response = client.get("/core/overload/history", headers=AUTH)

        assert response.status_code == 200
        assert response.json()[0]["peak_overdue"] == 3
        mock_service.history.assert_awaited_once_with(30)

    def test_passes_days(self, client, mock_service):
        mock_service.history.return_value = []

        client.get("/core/overload/history?days=7", headers=AUTH)

        mock_service.history.assert_awaited_once_with(7)

    @pytest.mark.parametrize("days", [0, 366])
    def test_rejects_out_of_range_days(self, client, days):
        assert client.get(f"/core/overload/history?days={days}", headers=AUTH).status_code == 422
