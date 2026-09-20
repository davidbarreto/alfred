from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.features.core.urgency_reset.schemas import UrgencyResetRead

AUTH = {"Authorization": "Bearer test-api-token"}


@pytest.fixture
def mock_service():
    return AsyncMock()


@pytest.fixture
def client(mock_service):
    from app.main import app
    from app.dependencies import get_urgency_reset_service
    app.dependency_overrides[get_urgency_reset_service] = lambda: mock_service
    yield TestClient(app)
    app.dependency_overrides.clear()


class TestResetUrgency:
    def test_resets_with_default_days(self, client, mock_service):
        mock_service.reset.return_value = UrgencyResetRead(
            days=7, tasks_urgency_reset=5, tasks_deadline_moved=3, tasks_snoozed=1
        )

        response = client.post("/core/urgency-reset", headers=AUTH)

        assert response.status_code == 200
        assert response.json() == {
            "days": 7, "tasks_urgency_reset": 5, "tasks_deadline_moved": 3, "tasks_snoozed": 1,
        }
        mock_service.reset.assert_awaited_once_with(None)

    def test_passes_days_query_param(self, client, mock_service):
        mock_service.reset.return_value = UrgencyResetRead(
            days=14, tasks_urgency_reset=0, tasks_deadline_moved=0, tasks_snoozed=0
        )

        response = client.post("/core/urgency-reset?days=14", headers=AUTH)

        assert response.status_code == 200
        mock_service.reset.assert_awaited_once_with(14)

    @pytest.mark.parametrize("days", [0, -1, 366])
    def test_rejects_out_of_range_days(self, client, days):
        assert client.post(f"/core/urgency-reset?days={days}", headers=AUTH).status_code == 422

    def test_requires_auth(self, client):
        assert client.post("/core/urgency-reset").status_code == 403
