from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from freezegun import freeze_time

from app.features.travel.errors import TravelNotFoundError
from app.features.travel.settings_schemas import TravelSettingsUpdate
from app.features.travel.settings_service import TravelSettingsService


@pytest.fixture
def service():
    svc = TravelSettingsService(AsyncMock())
    svc._settings = AsyncMock()
    svc._settings.get_value.return_value = None
    svc._cities = AsyncMock()
    svc._trips = AsyncMock()
    svc._trips.snapshot_home_value.return_value = 2
    svc._places = AsyncMock()
    svc._places.get_home.return_value = None
    return svc


class TestHomeAddress:
    @pytest.mark.asyncio
    async def test_is_read_from_the_home_location(self, service):
        service._places.get_home.return_value = SimpleNamespace(address="Rua Exemplo 1")
        assert (await service.get()).home_address == "Rua Exemplo 1"

    @pytest.mark.asyncio
    async def test_is_none_without_a_home_or_its_address(self, service):
        assert (await service.get()).home_address is None
        service._places.get_home.return_value = SimpleNamespace(address=None)
        assert (await service.get()).home_address is None

    @pytest.mark.parametrize("value", ["Rua Exemplo 1", "", None])
    def test_sending_it_is_refused_and_names_the_places_route(self, value):
        with pytest.raises(ValueError, match="/location/places"):
            TravelSettingsUpdate(home_address=value)

    @pytest.mark.asyncio
    async def test_other_fields_stay_in_the_travel_namespace(self, service):
        await service.update(TravelSettingsUpdate(home_to_airport_min=30))
        service._settings.set_value.assert_awaited_once_with("travel.home_to_airport_min", "30")


class TestMaxVisitsPerDay:
    @pytest.mark.asyncio
    async def test_defaults_to_four_and_is_stored_in_the_travel_namespace(self, service):
        assert (await service.get()).max_visits_per_day == 4
        await service.update(TravelSettingsUpdate(max_visits_per_day=6))
        service._settings.set_value.assert_awaited_once_with("travel.max_visits_per_day", "6")


class TestSnoozeOtherEvents:
    @pytest.mark.asyncio
    async def test_is_off_by_default_and_stored_as_zero_or_one(self, service):
        assert (await service.get()).snooze_other_events is False
        await service.update(TravelSettingsUpdate(snooze_other_events=True))
        service._settings.set_value.assert_awaited_once_with("travel.snooze_other_events", "1")
        service._settings.get_value.side_effect = lambda key: "1" if key == "travel.snooze_other_events" else None
        assert (await service.get()).snooze_other_events is True


class TestMovedConstants:
    @pytest.mark.asyncio
    async def test_defaults_are_the_constants_the_code_used(self, service):
        settings = await service.get()
        assert (
            settings.leave_home_lead_min, settings.check_in_opens_hours, settings.checklist_nudge_days,
            settings.tight_connection_min, settings.long_wait_hours, settings.rain_mm,
            settings.charge_link_lead_days, settings.charge_link_tail_days,
        ) == (60, 24, 60, 90, 4, 2.0, 90, 30)

    @pytest.mark.asyncio
    async def test_rain_threshold_is_read_as_a_number_with_decimals(self, service):
        service._settings.get_value.side_effect = lambda key: "2.5" if key == "travel.rain_mm" else None
        assert (await service.get()).rain_mm == 2.5

    @pytest.mark.asyncio
    async def test_stored_as_text(self, service):
        await service.update(TravelSettingsUpdate(rain_mm=1.5, check_in_opens_hours=48))
        stored = {c.args for c in service._settings.set_value.await_args_list}
        assert stored == {("travel.rain_mm", "1.5"), ("travel.check_in_opens_hours", "48")}


def _stored(service, **values):
    service._settings.get_value.side_effect = lambda key: {f"travel.{k}": v for k, v in values.items()}.get(key)


@freeze_time("2026-11-16 12:00:00")
class TestHomeSnapshot:
    @pytest.mark.asyncio
    async def test_changing_a_setting_gives_started_trips_the_old_value(self, service):
        _stored(service, airport_buffer_min="90")
        await service.update(TravelSettingsUpdate(airport_buffer_min=150))
        service._trips.snapshot_home_value.assert_awaited_once_with("airport_buffer_min", 90, date(2026, 11, 16))

    @pytest.mark.asyncio
    async def test_the_default_counts_as_the_old_value_when_nothing_was_stored(self, service):
        await service.update(TravelSettingsUpdate(airport_buffer_min=150))
        service._trips.snapshot_home_value.assert_awaited_once_with("airport_buffer_min", 120, date(2026, 11, 16))

    @pytest.mark.asyncio
    async def test_an_unchanged_value_copies_nothing(self, service):
        _stored(service, airport_buffer_min="90")
        await service.update(TravelSettingsUpdate(airport_buffer_min=90))
        service._trips.snapshot_home_value.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_a_setting_that_was_never_set_is_not_copied(self, service):
        await service.update(TravelSettingsUpdate(home_city_id=None))
        service._trips.snapshot_home_value.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_the_old_city_is_copied_when_it_changes(self, service):
        _stored(service, home_city_id="7")
        service._cities.get_city.return_value = SimpleNamespace(id=7, name="Alpha", country_id=1, country=SimpleNamespace(id=1, name="Examplia", code=None))
        await service.update(TravelSettingsUpdate(home_city_id=None))
        calls = {c.args[0]: c.args[1] for c in service._trips.snapshot_home_value.await_args_list}
        assert calls == {"home_city_id": 7}

    @pytest.mark.asyncio
    async def test_the_snapshot_is_made_before_the_new_value_is_saved(self, service):
        _stored(service, airport_buffer_min="90")
        order = []
        service._trips.snapshot_home_value.side_effect = lambda *a: order.append("snapshot") or 1
        service._settings.set_value.side_effect = lambda *a: order.append("save")
        await service.update(TravelSettingsUpdate(airport_buffer_min=150))
        assert order == ["snapshot", "save"]


class TestHomeCity:
    @pytest.mark.asyncio
    async def test_an_unknown_city_is_not_found_and_nothing_is_saved(self, service):
        service._cities.get_city.return_value = None
        with pytest.raises(TravelNotFoundError):
            await service.update(TravelSettingsUpdate(home_city_id=99))
        service._settings.set_value.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_it_is_stored_and_null_clears_it(self, service):
        service._cities.get_city.return_value = SimpleNamespace(id=7)
        await service.update(TravelSettingsUpdate(home_city_id=7))
        service._settings.set_value.assert_awaited_with("travel.home_city_id", "7")
        await service.update(TravelSettingsUpdate.model_validate({"home_city_id": None}))
        service._settings.set_value.assert_awaited_with("travel.home_city_id", "")

    @pytest.mark.asyncio
    async def test_it_is_read_back_with_its_country(self, service):
        country = SimpleNamespace(id=1, name="Examplia", code="EX")
        service._cities.get_city.return_value = SimpleNamespace(id=7, name="Alpha", country=country)
        _stored(service, home_city_id="7")
        read = await service.get()
        assert (read.home_city_id, read.home_city.name, read.home_city.country.code) == (7, "Alpha", "EX")

    @pytest.mark.asyncio
    async def test_a_settings_update_without_the_city_leaves_it_alone(self, service):
        await service.update(TravelSettingsUpdate(max_visits_per_day=5))
        assert all(c.args[0] != "travel.home_city_id" for c in service._settings.set_value.await_args_list)
