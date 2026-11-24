from datetime import date
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.features.organizer.holidays.errors import HolidayRangeError
from app.features.organizer.holidays.schemas import HolidayRead

AUTH = {"Authorization": "Bearer test-api-token"}


@pytest.fixture
def mock_service():
    svc = AsyncMock()
    svc.list.return_value = [HolidayRead(date=date(2026, 12, 25), name="Christmas Day", country="PT")]
    return svc


@pytest.fixture
def client(mock_service):
    from app.main import app
    from app.dependencies import get_holiday_service
    app.dependency_overrides[get_holiday_service] = lambda: mock_service
    yield TestClient(app)
    app.dependency_overrides.clear()


class TestListHolidays:
    def test_returns_holidays_in_range(self, client, mock_service):
        response = client.get("/organizer/holidays?from=2026-12-01&to=2026-12-31", headers=AUTH)

        assert response.status_code == 200
        assert response.json() == [{"date": "2026-12-25", "name": "Christmas Day", "country": "PT"}]
        mock_service.list.assert_awaited_once_with(date(2026, 12, 1), date(2026, 12, 31))

    def test_range_error_is_400(self, client, mock_service):
        mock_service.list.side_effect = HolidayRangeError("'to' must not be before 'from'")

        response = client.get("/organizer/holidays?from=2026-12-31&to=2026-12-01", headers=AUTH)

        assert response.status_code == 400
        assert response.json()["detail"] == "'to' must not be before 'from'"

    def test_missing_dates_are_422(self, client):
        assert client.get("/organizer/holidays?from=2026-12-01", headers=AUTH).status_code == 422

    def test_requires_auth(self, client):
        assert client.get("/organizer/holidays?from=2026-12-01&to=2026-12-31").status_code == 403
