import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.features.core.weather_settings.errors import WeatherPlaceInvalidError, WeatherPlaceNotFoundError
from app.features.core.weather_settings.schemas import WeatherSettingsUpdate
from app.features.core.weather_settings.service import WeatherSettingsService

AUTH = {"Authorization": "Bearer test-api-token"}


def _location(id=1, name="Office", lat=41.1, lon=-8.6, active=True, kind="work"):
    return SimpleNamespace(id=id, name=name, latitude=lat, longitude=lon, active=active, kind=kind)


def _city(id=3, name="Lisbon", country="Portugal"):
    return SimpleNamespace(id=id, name=name, country=SimpleNamespace(name=country))


@pytest.fixture
def stored():
    return {}


@pytest.fixture
def service(stored):
    svc = WeatherSettingsService(session=AsyncMock())
    svc._settings = AsyncMock()
    svc._settings.get_value.side_effect = lambda key: stored.get(key)
    svc._locations = AsyncMock()
    svc._locations.get_home.return_value = _location(id=9, name="Home", lat=38.7, lon=-9.1, kind="home")
    svc._locations.get.return_value = None
    svc._locations.list.return_value = []
    svc._cities = AsyncMock()
    svc._cities.get_city.return_value = None
    svc._cities.get_cities.return_value = []
    return svc


async def _geocode(name):
    return (38.72, -9.14) if name == "Lisbon, Portugal" else None


class TestResolve:
    async def test_default_is_home(self, service):
        place = await service.resolve(_geocode)
        assert (place.source, place.label, place.latitude, place.longitude) == ("home", "Home", 38.7, -9.1)

    async def test_chosen_location_wins(self, service, stored):
        stored["weather.location_id"] = "1"
        service._locations.get.return_value = _location()
        place = await service.resolve(_geocode)
        assert (place.source, place.label, place.latitude) == ("location", "Office", 41.1)

    async def test_chosen_city_is_geocoded(self, service, stored):
        stored["weather.city_id"] = "3"
        service._cities.get_city.return_value = _city()
        place = await service.resolve(_geocode)
        assert (place.source, place.label, place.latitude, place.longitude) == ("city", "Lisbon, Portugal", 38.72, -9.14)

    async def test_city_not_found_by_geocoding_falls_back_to_home(self, service, stored):
        stored["weather.city_id"] = "3"
        service._cities.get_city.return_value = _city(name="Atlantis", country="Nowhere")
        assert (await service.resolve(_geocode)).source == "home"

    async def test_geocoding_error_falls_back_to_home(self, service, stored):
        stored["weather.city_id"] = "3"
        service._cities.get_city.return_value = _city()
        geocode = AsyncMock(side_effect=RuntimeError("down"))
        assert (await service.resolve(geocode)).source == "home"

    async def test_deleted_location_falls_back_to_home_with_a_warning(self, service, stored, caplog):
        stored["weather.location_id"] = "1"
        service._locations.get.return_value = None
        with caplog.at_level(logging.WARNING):
            place = await service.resolve(_geocode)
        assert place.source == "home"
        assert "falling back to Home" in caplog.text

    async def test_archived_location_falls_back_to_home(self, service, stored):
        stored["weather.location_id"] = "1"
        service._locations.get.return_value = _location(active=False)
        assert (await service.resolve(_geocode)).source == "home"

    async def test_none_when_home_has_no_coordinates(self, service):
        service._locations.get_home.return_value = _location(id=9, name="Home", lat=None, lon=None, kind="home")
        assert await service.resolve(_geocode) is None

    async def test_none_without_a_home(self, service):
        service._locations.get_home.return_value = None
        assert await service.resolve(_geocode) is None


class TestGet:
    async def test_lists_choices_and_the_place_in_use(self, service, stored):
        service._locations.list.return_value = [_location(), _location(id=2, name="Gym", lat=None, lon=None)]
        service._cities.get_cities.return_value = [_city()]

        result = await service.get()

        assert (result.location_id, result.city_id, result.place_label) == (None, None, "Home (Home)")
        assert [c.label for c in result.choices.locations] == ["Office"]
        assert [c.label for c in result.choices.cities] == ["Lisbon, Portugal"]

    async def test_no_place(self, service):
        service._locations.get_home.return_value = None
        assert (await service.get()).place_label is None


class TestUpdate:
    async def test_choosing_a_location_clears_the_city(self, service):
        service._locations.get.return_value = _location()

        await service.update(WeatherSettingsUpdate(location_id=1))

        stored = {c.args for c in service._settings.set_value.await_args_list}
        assert stored == {("weather.location_id", "1"), ("weather.city_id", "")}

    async def test_choosing_a_city_clears_the_location(self, service):
        service._cities.get_city.return_value = _city()

        await service.update(WeatherSettingsUpdate(city_id=3))

        stored = {c.args for c in service._settings.set_value.await_args_list}
        assert stored == {("weather.location_id", ""), ("weather.city_id", "3")}

    async def test_both_null_goes_back_to_home(self, service):
        await service.update(WeatherSettingsUpdate(location_id=None, city_id=None))

        stored = {c.args for c in service._settings.set_value.await_args_list}
        assert stored == {("weather.location_id", ""), ("weather.city_id", "")}

    def test_both_is_refused(self):
        with pytest.raises(ValidationError):
            WeatherSettingsUpdate(location_id=1, city_id=3)

    async def test_location_without_coordinates_is_refused(self, service):
        service._locations.get.return_value = _location(lat=None, lon=None)
        with pytest.raises(WeatherPlaceInvalidError, match="no coordinates"):
            await service.update(WeatherSettingsUpdate(location_id=1))
        service._settings.set_value.assert_not_awaited()

    async def test_archived_location_is_refused(self, service):
        service._locations.get.return_value = _location(active=False)
        with pytest.raises(WeatherPlaceInvalidError):
            await service.update(WeatherSettingsUpdate(location_id=1))

    async def test_unknown_location_or_city(self, service):
        with pytest.raises(WeatherPlaceNotFoundError):
            await service.update(WeatherSettingsUpdate(location_id=99))
        with pytest.raises(WeatherPlaceNotFoundError):
            await service.update(WeatherSettingsUpdate(city_id=99))


class TestRoutes:
    @pytest.fixture
    def client(self):
        from app.dependencies import get_weather_settings_service
        from app.main import app

        service = AsyncMock()
        app.dependency_overrides[get_weather_settings_service] = lambda: service
        yield TestClient(app), service
        app.dependency_overrides.clear()

    def test_both_is_a_422(self, client):
        test_client, service = client
        response = test_client.put("/core/weather-settings", json={"location_id": 1, "city_id": 3}, headers=AUTH)
        assert response.status_code == 422
        service.update.assert_not_awaited()

    def test_errors_map_to_404_and_422(self, client):
        test_client, service = client
        service.update.side_effect = WeatherPlaceNotFoundError("Location 9 not found")
        assert test_client.put("/core/weather-settings", json={"location_id": 9}, headers=AUTH).status_code == 404
        service.update.side_effect = WeatherPlaceInvalidError("Office has no coordinates")
        response = test_client.put("/core/weather-settings", json={"location_id": 1}, headers=AUTH)
        assert response.status_code == 422 and response.json()["detail"] == "Office has no coordinates"

    def test_requires_auth(self, client):
        test_client, _ = client
        assert test_client.get("/core/weather-settings").status_code == 403
