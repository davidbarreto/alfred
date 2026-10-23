from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.features.core.reminders.schemas import ReminderSettingsRead

AUTH = {"Authorization": "Bearer test-api-token"}

_SETTINGS = ReminderSettingsRead(
    overload_overdue_threshold=5, overload_urgent_threshold=4, overload_max_listed=5,
    overload_urgent_interval_hours=4, overdue_grace_hours_high=0, overdue_grace_hours_medium=48,
    overdue_grace_hours_low=168, undated_escalation_days_high=7, undated_escalation_days_medium=21,
    undated_escalation_days_low=45, urgency_reset_days=7, catchup_tasks_per_day=3, catchup_stale_days=30,
    catchup_missed_habit_threshold=3,
)


@pytest.fixture
def mock_service():
    return AsyncMock()


@pytest.fixture
def client(mock_service):
    from app.main import app
    from app.dependencies import get_reminder_settings_service

    app.dependency_overrides[get_reminder_settings_service] = lambda: mock_service
    yield TestClient(app)
    app.dependency_overrides.clear()


class TestGetReminderSettings:
    def test_returns_settings(self, client, mock_service):
        mock_service.get.return_value = _SETTINGS

        response = client.get("/core/reminder-settings", headers=AUTH)

        assert response.status_code == 200
        assert response.json()["overload_max_listed"] == 5
        assert response.json()["overdue_grace_hours_low"] == 168

    def test_requires_auth(self, client):
        assert client.get("/core/reminder-settings").status_code == 403


class TestUpdateReminderSettings:
    def test_updates_only_sent_fields(self, client, mock_service):
        mock_service.update.return_value = _SETTINGS

        response = client.put("/core/reminder-settings", json={"overload_max_listed": 8}, headers=AUTH)

        assert response.status_code == 200
        (update,), _ = mock_service.update.call_args
        assert update.model_dump(exclude_unset=True) == {"overload_max_listed": 8}

    def test_rejects_out_of_range_value(self, client):
        response = client.put("/core/reminder-settings", json={"overload_max_listed": 0}, headers=AUTH)

        assert response.status_code == 422
