from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.features.organizer.interviews.preferences.schemas import InterviewPreferencesRead

AUTH = {"Authorization": "Bearer test-api-token"}

_READ = InterviewPreferencesRead(
    id=1,
    work_regimes=["remote", "hybrid"],
    target_office_days_per_month=4.0,
    salary_min=80000,
    salary_max=100000,
    salary_currency="EUR",
    locations=["Lisbon"],
    tech_stack=["Java", "Python"],
    roles=["Backend Engineer"],
    career_objectives="Move into a staff-level role",
    created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
)


@pytest.fixture
def client():
    from app.main import app
    from app.dependencies import get_interview_preferences_service

    mock_service = AsyncMock(
        get_preferences=AsyncMock(return_value=_READ),
        update_preferences=AsyncMock(return_value=_READ),
    )
    app.dependency_overrides[get_interview_preferences_service] = lambda: mock_service
    yield TestClient(app), mock_service
    app.dependency_overrides.clear()


class TestGetPreferences:
    def test_returns_preferences(self, client):
        test_client, mock_service = client
        response = test_client.get("/organizer/interview-preferences", headers=AUTH)
        assert response.status_code == 200
        assert response.json()["tech_stack"] == ["Java", "Python"]


class TestUpdatePreferences:
    def test_patches_and_returns_preferences(self, client):
        test_client, mock_service = client
        response = test_client.patch(
            "/organizer/interview-preferences", json={"work_regimes": ["remote"]}, headers=AUTH
        )
        assert response.status_code == 200
        mock_service.update_preferences.assert_awaited_once()
