from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.features.travel.settings_schemas import TravelSettingsRead

AUTH = {"Authorization": "Bearer test-api-token"}


@pytest.fixture
def settings():
    import app.dependencies as deps
    from app.main import app

    service = AsyncMock()
    app.dependency_overrides[deps.get_travel_settings_service] = lambda: service
    yield TestClient(app), service
    app.dependency_overrides.clear()


def test_get(settings):
    client, service = settings
    service.get.return_value = TravelSettingsRead(airport_buffer_min=120, home_to_airport_min=45, home_address="Rua Exemplo 1")
    assert client.get("/travel/settings", headers=AUTH).json() == {
        "airport_buffer_min": 120, "home_to_airport_min": 45, "home_address": "Rua Exemplo 1", "home_city_id": None, "home_city": None, "max_visits_per_day": 4, "visit_duration_min": 90, "unpaid_leg_days": 30, "snooze_other_events": False,
        "leave_home_lead_min": 60, "check_in_opens_hours": 24, "checklist_nudge_days": 60, "tight_connection_min": 90,
        "long_wait_hours": 4, "rain_mm": 2.0, "charge_link_lead_days": 90, "charge_link_tail_days": 30,
    }


def test_put_updates_only_given_fields(settings):
    client, service = settings
    service.update.return_value = TravelSettingsRead(airport_buffer_min=120, home_to_airport_min=30)
    resp = client.put("/travel/settings", headers=AUTH, json={"home_to_airport_min": 30})
    assert resp.status_code == 200
    assert service.update.await_args.args[0].model_dump(exclude_unset=True) == {"home_to_airport_min": 30}


def test_put_out_of_range_is_422(settings):
    client, _ = settings
    assert client.put("/travel/settings", headers=AUTH, json={"airport_buffer_min": 9999}).status_code == 422


def test_requires_a_token(settings):
    client, _ = settings
    assert client.get("/travel/settings").status_code in (401, 403)


def test_put_home_address_is_refused_with_where_it_moved(settings):
    client, service = settings
    response = client.put("/travel/settings", headers=AUTH, json={"home_address": "Rua Exemplo 1"})
    assert response.status_code == 422
    assert "/organizer/locations" in response.json()["detail"][0]["msg"]
    service.update.assert_not_awaited()
