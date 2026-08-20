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


class TestGetDueContactBirthdayNotifications:
    def test_returns_digest(self, client):
        from app.dependencies import get_contact_birthday_notification_service
        from app.features.core.reminders.schemas import ReminderDigest
        from app.main import app

        service = AsyncMock()
        service.build_due_digest.return_value = ReminderDigest(
            date=date(2026, 8, 20), has_content=True, text="Birthday reminders text"
        )
        app.dependency_overrides[get_contact_birthday_notification_service] = lambda: service

        response = client.get("/organizer/contact-birthday-notifications/due", headers=AUTH)

        assert response.status_code == 200
        assert response.json()["has_content"] is True

    def test_requires_auth(self, client):
        assert client.get("/organizer/contact-birthday-notifications/due").status_code == 403


class TestGetContactBirthdaySettings:
    def test_returns_relationships(self, client):
        from app.dependencies import get_contact_birthday_settings_service
        from app.features.organizer.contacts.notification_settings.schemas import ContactBirthdayCascadesRead
        from app.main import app

        service = AsyncMock()
        service.get.return_value = ContactBirthdayCascadesRead(relationships={"family": ["1mo", "1d"]})
        app.dependency_overrides[get_contact_birthday_settings_service] = lambda: service

        response = client.get("/organizer/contact-birthday-settings", headers=AUTH)

        assert response.status_code == 200
        assert response.json()["relationships"]["family"] == ["1mo", "1d"]

    def test_update_relationship(self, client):
        from app.dependencies import get_contact_birthday_settings_service
        from app.features.organizer.contacts.notification_settings.schemas import ContactBirthdayCascadesRead
        from app.main import app

        service = AsyncMock()
        service.update_relationship.return_value = ContactBirthdayCascadesRead(relationships={"friend": ["3d"]})
        app.dependency_overrides[get_contact_birthday_settings_service] = lambda: service

        response = client.put(
            "/organizer/contact-birthday-settings/friend", json={"offsets": ["3d"]}, headers=AUTH
        )

        assert response.status_code == 200
        service.update_relationship.assert_awaited_once()

    def test_requires_auth(self, client):
        assert client.get("/organizer/contact-birthday-settings").status_code == 403
