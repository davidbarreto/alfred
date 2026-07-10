from datetime import date
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.features.briefing.schemas import FormattedBriefing, MorningBriefing, WeatherForecast

AUTH = {"Authorization": "Bearer test-api-token"}


def _morning_briefing() -> MorningBriefing:
    return MorningBriefing(
        date=date(2026, 7, 10),
        tasks=[],
        events=[],
        holidays=[],
        birthdays=[],
        weather=WeatherForecast(
            temperature_max_c=22.0,
            temperature_min_c=15.0,
            feels_like_max_c=21.0,
            precipitation_probability=20,
            wind_speed_max_kmh=12.0,
            description="Partly cloudy",
            advice=[],
        ),
    )


@pytest.fixture
def mock_summary_service():
    svc = AsyncMock()
    svc.build.return_value = _morning_briefing()
    return svc


@pytest.fixture
def mock_formatter_service():
    svc = AsyncMock()
    svc.get_saved.return_value = None
    svc.format.return_value = FormattedBriefing(date=date(2026, 7, 10), text="Freshly generated briefing.")
    return svc


@pytest.fixture
def client(mock_summary_service, mock_formatter_service):
    from app.main import app
    from app.dependencies import get_briefing_formatter_service, get_briefing_summary_service
    app.dependency_overrides[get_briefing_summary_service] = lambda: mock_summary_service
    app.dependency_overrides[get_briefing_formatter_service] = lambda: mock_formatter_service
    yield TestClient(app)
    app.dependency_overrides.clear()


class TestMorningBriefingFormatted:
    def test_requires_auth(self, client):
        assert client.get("/briefing/morning/formatted").status_code == 403

    def test_generates_when_no_saved_briefing(self, client, mock_summary_service, mock_formatter_service):
        response = client.get("/briefing/morning/formatted", headers=AUTH)

        assert response.status_code == 200
        assert response.json()["text"] == "Freshly generated briefing."
        mock_summary_service.build.assert_called_once()
        mock_formatter_service.format.assert_called_once()

    def test_reuses_saved_briefing(self, client, mock_summary_service, mock_formatter_service):
        mock_formatter_service.get_saved.return_value = FormattedBriefing(
            date=date(2026, 7, 10), text="Saved briefing."
        )

        response = client.get("/briefing/morning/formatted", headers=AUTH)

        assert response.status_code == 200
        assert response.json()["text"] == "Saved briefing."
        mock_summary_service.build.assert_not_called()
        mock_formatter_service.format.assert_not_called()

    def test_force_regenerates_even_when_saved(self, client, mock_summary_service, mock_formatter_service):
        mock_formatter_service.get_saved.return_value = FormattedBriefing(
            date=date(2026, 7, 10), text="Saved briefing."
        )

        response = client.get("/briefing/morning/formatted?force=true", headers=AUTH)

        assert response.status_code == 200
        assert response.json()["text"] == "Freshly generated briefing."
        mock_formatter_service.get_saved.assert_not_called()
        mock_summary_service.build.assert_called_once()
        mock_formatter_service.format.assert_called_once()
