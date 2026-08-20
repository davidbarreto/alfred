from datetime import date
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

AUTH = {"Authorization": "Bearer test-api-token"}


@pytest.fixture
def client():
    from app.main import app
    from app.db.session import get_session

    async def mock_session():
        yield AsyncMock()

    app.dependency_overrides[get_session] = mock_session
    yield TestClient(app)
    app.dependency_overrides.clear()


class TestGetDueCalendarNotifications:
    def test_returns_digest(self, client):
        from app.dependencies import get_calendar_notification_service
        from app.features.core.reminders.schemas import ReminderDigest
        from app.main import app

        service = AsyncMock()
        service.build_due_digest.return_value = ReminderDigest(
            date=date(2026, 8, 20), has_content=True, text="Event reminders text"
        )
        app.dependency_overrides[get_calendar_notification_service] = lambda: service

        response = client.get("/organizer/calendar-notifications/due", headers=AUTH)

        assert response.status_code == 200
        assert response.json()["has_content"] is True

    def test_requires_auth(self, client):
        assert client.get("/organizer/calendar-notifications/due").status_code == 403


class TestGetCalendarNotificationSettings:
    def test_returns_profiles(self, client):
        from app.dependencies import get_calendar_notification_settings_service
        from app.features.organizer.calendar_events.notification_settings.schemas import (
            CalendarNotificationCascadesRead,
        )
        from app.main import app

        service = AsyncMock()
        service.get.return_value = CalendarNotificationCascadesRead(profiles={"normal": ["1h", "10m", "0"]})
        app.dependency_overrides[get_calendar_notification_settings_service] = lambda: service

        response = client.get("/organizer/calendar-notification-settings", headers=AUTH)

        assert response.status_code == 200
        assert response.json()["profiles"]["normal"] == ["1h", "10m", "0"]

    def test_update_profile(self, client):
        from app.dependencies import get_calendar_notification_settings_service
        from app.features.organizer.calendar_events.notification_settings.schemas import (
            CalendarNotificationCascadesRead,
        )
        from app.main import app

        service = AsyncMock()
        service.update_profile.return_value = CalendarNotificationCascadesRead(profiles={"light": ["10m", "0"]})
        app.dependency_overrides[get_calendar_notification_settings_service] = lambda: service

        response = client.put(
            "/organizer/calendar-notification-settings/light", json={"offsets": ["10m", "0"]}, headers=AUTH
        )

        assert response.status_code == 200
        service.update_profile.assert_awaited_once()

    def test_requires_auth(self, client):
        assert client.get("/organizer/calendar-notification-settings").status_code == 403
