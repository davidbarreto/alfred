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


class TestGetDueReminders:
    def test_returns_digest(self, client):
        from app.dependencies import get_reminder_service
        from app.features.core.reminders.schemas import ReminderDigest
        from app.main import app

        service = AsyncMock()
        service.build_due_digest.return_value = ReminderDigest(
            date=date(2026, 7, 11), has_content=True, text="Reminders text"
        )
        app.dependency_overrides[get_reminder_service] = lambda: service

        response = client.get("/core/reminders/due", headers=AUTH)

        assert response.status_code == 200
        body = response.json()
        assert body["has_content"] is True
        assert body["text"] == "Reminders text"

    def test_requires_auth(self, client):
        response = client.get("/core/reminders/due")
        assert response.status_code == 403
