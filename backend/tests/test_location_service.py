from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from zoneinfo import ZoneInfo

import pytest

from app.features.briefing.schemas import HolidayItem
from app.features.organizer.locations.errors import LocationConflictError, LocationValidationError
from app.features.organizer.locations.schemas import LocationCreate, LocationFilters, LocationUpdate
from app.features.organizer.locations.service import LocationService

_NOW = datetime(2026, 11, 1, tzinfo=timezone.utc)
# A Monday, 10:30 local time.
_LOCAL_NOW = datetime(2026, 11, 23, 10, 30, tzinfo=ZoneInfo("Europe/Lisbon"))
_WEEKDAY_HOURS = {d: [["08:00", "20:00"]] for d in ("mon", "tue", "wed", "thu", "fri")}


def _category(id=1, name="groceries"):
    category = MagicMock()
    category.id = id
    category.name = name
    return category


def _location(**kwargs):
    location = MagicMock()
    location.id = kwargs.get("id", 1)
    location.name = kwargs.get("name", "Market")
    location.kind = kwargs.get("kind", "supermarket")
    location.address = kwargs.get("address", None)
    location.maps_url = kwargs.get("maps_url", None)
    location.latitude = kwargs.get("latitude", None)
    location.longitude = kwargs.get("longitude", None)
    location.opening_hours = kwargs.get("opening_hours", None)
    location.notes = kwargs.get("notes", None)
    location.active = kwargs.get("active", True)
    location.categories = kwargs.get("categories", [])
    location.created_at = _NOW
    location.updated_at = _NOW
    return location


def _holiday(name="Feriado"):
    return HolidayItem(name=name, local_name=name, country="PT", days_until=0, date=_LOCAL_NOW.date())


@pytest.fixture(autouse=True)
def _monday_morning(monkeypatch):
    monkeypatch.setattr("app.features.organizer.locations.service.local_now", lambda: _LOCAL_NOW)
    monkeypatch.setattr("app.features.organizer.locations.service.local_today", lambda: _LOCAL_NOW.date())


@pytest.fixture
def holidays():
    provider = AsyncMock()
    provider.get_holidays.return_value = []
    return provider


@pytest.fixture
def home_snapshot():
    return AsyncMock(return_value=2)


@pytest.fixture
def service(holidays, home_snapshot):
    svc = LocationService(session=AsyncMock(), holiday_provider=holidays, home_snapshot=home_snapshot)
    svc._repo = AsyncMock()
    svc._repo.get_by_name.return_value = None
    svc._repo.get_home.return_value = None
    svc._repo.get_categories.return_value = []
    svc._travel_times = AsyncMock()
    svc._travel_times.list_for.return_value = []
    return svc


class TestCreate:
    async def test_parses_hours_text_and_links_categories(self, service):
        groceries = _category()
        service._repo.get_categories.return_value = [groceries]
        service._repo.create.return_value = _location(opening_hours=_WEEKDAY_HOURS, categories=[groceries])

        result = await service.create(LocationCreate(
            name="  Market   by school ", kind=" Supermarket", opening_hours="mon-fri 8-20", category_ids=[1, 1],
        ))

        fields, categories = service._repo.create.call_args.args
        assert fields["name"] == "Market by school"
        assert fields["kind"] == "supermarket"
        assert fields["opening_hours"] == _WEEKDAY_HOURS
        assert categories == [groceries]
        service._repo.get_categories.assert_awaited_once_with([1])
        assert result.opening_hours_text == "mon-fri 08:00-20:00"
        assert [c.name for c in result.categories] == ["groceries"]

    async def test_default_kind_is_other(self, service):
        service._repo.create.return_value = _location(kind="other")

        await service.create(LocationCreate(name="Post office"))

        assert service._repo.create.call_args.args[0]["kind"] == "other"

    async def test_bad_hours_are_a_validation_error(self, service):
        with pytest.raises(LocationValidationError, match="Opening hours: .*not a day"):
            await service.create(LocationCreate(name="Market", opening_hours="funday 9-17"))
        service._repo.create.assert_not_called()

    async def test_unknown_category_is_a_validation_error(self, service):
        service._repo.get_categories.return_value = [_category(1)]

        with pytest.raises(LocationValidationError, match=r"\[7\]"):
            await service.create(LocationCreate(name="Market", category_ids=[1, 7]))

    async def test_name_clash_is_case_insensitive_conflict(self, service):
        service._repo.get_by_name.return_value = _location(id=4, name="Market")

        with pytest.raises(LocationConflictError, match="already exists"):
            await service.create(LocationCreate(name="MARKET"))

    async def test_second_home_is_a_conflict(self, service):
        service._repo.get_home.return_value = _location(id=2, name="Home", kind="home")

        with pytest.raises(LocationConflictError, match="Home is already set"):
            await service.create(LocationCreate(name="Flat", kind="home"))

    def test_blank_name_is_refused_by_the_schema(self):
        with pytest.raises(ValueError):
            LocationCreate(name="   ")


class TestUpdate:
    async def test_changing_to_home_when_another_home_exists_conflicts(self, service):
        service._repo.get.return_value = _location(id=1)
        service._repo.get_home.return_value = _location(id=2, kind="home")

        with pytest.raises(LocationConflictError):
            await service.update(1, LocationUpdate(kind="home"))

    async def test_home_can_be_edited_without_clashing_with_itself(self, service):
        home = _location(id=2, name="Home", kind="home")
        service._repo.get.return_value = home
        service._repo.get_home.return_value = home
        service._repo.get_by_name.return_value = home
        service._repo.update.return_value = home

        await service.update(2, LocationUpdate(name="home", kind="home", address="Somewhere 1"))

        service._repo.update.assert_awaited_once()

    async def test_blank_hours_clear_them_and_categories_untouched_when_not_given(self, service):
        service._repo.get.return_value = _location()
        service._repo.update.return_value = _location()

        await service.update(1, LocationUpdate(opening_hours=""))

        location_id, changes, categories = service._repo.update.call_args.args
        assert changes == {"opening_hours": None}
        assert categories is None

    async def test_category_ids_replace_the_list(self, service):
        service._repo.get.return_value = _location()
        service._repo.get_categories.return_value = [_category(3, "pharmacy")]
        service._repo.update.return_value = _location()

        await service.update(1, LocationUpdate(category_ids=[3]))

        _, changes, categories = service._repo.update.call_args.args
        assert changes == {}
        assert [c.id for c in categories] == [3]

    async def test_required_fields_cannot_be_cleared(self, service):
        with pytest.raises(LocationValidationError, match="kind cannot be cleared"):
            await service.update(1, LocationUpdate(kind=None))

    async def test_not_found(self, service):
        service._repo.get.return_value = None

        assert await service.update(9, LocationUpdate(notes="x")) is None


_PIN_URL = "https://www.google.com/maps/place/X/@41.15,-8.62,17z/data=!3m1!4b1!8m2!3d41.1579!4d-8.6291"


class TestCoordinates:
    async def test_typed_coordinates_are_stored(self, service):
        service._repo.create.return_value = _location(latitude=41.1579, longitude=-8.6291)

        result = await service.create(LocationCreate(name="Home", kind="home", coordinates="41.1579, -8.6291"))

        fields, _ = service._repo.create.call_args.args
        assert (fields["latitude"], fields["longitude"]) == (41.1579, -8.6291)
        assert "coordinates" not in fields
        assert (result.latitude, result.longitude) == (41.1579, -8.6291)

    async def test_create_fills_them_from_the_maps_link(self, service):
        service._repo.create.return_value = _location()

        await service.create(LocationCreate(name="Cafe", maps_url=_PIN_URL))

        fields, _ = service._repo.create.call_args.args
        assert (fields["latitude"], fields["longitude"]) == (41.1579, -8.6291)

    async def test_typed_coordinates_win_over_the_link(self, service):
        service._repo.create.return_value = _location()

        await service.create(LocationCreate(name="Cafe", maps_url=_PIN_URL, coordinates=[38.7, -9.1]))

        fields, _ = service._repo.create.call_args.args
        assert (fields["latitude"], fields["longitude"]) == (38.7, -9.1)

    async def test_none_without_coordinates_or_a_link_that_has_them(self, service):
        service._repo.create.return_value = _location()

        await service.create(LocationCreate(name="Cafe", maps_url="https://maps.app.goo.gl/AbC"))

        fields, _ = service._repo.create.call_args.args
        assert (fields["latitude"], fields["longitude"]) == (None, None)

    async def test_update_without_coordinates_fills_them_from_a_new_link(self, service):
        service._repo.get.return_value = _location()
        service._repo.update.return_value = _location()

        await service.update(1, LocationUpdate(maps_url=_PIN_URL))

        _, changes, _ = service._repo.update.call_args.args
        assert (changes["latitude"], changes["longitude"]) == (41.1579, -8.6291)

    async def test_a_new_link_keeps_coordinates_already_set(self, service):
        service._repo.get.return_value = _location(latitude=1.0, longitude=2.0)
        service._repo.update.return_value = _location()

        await service.update(1, LocationUpdate(maps_url=_PIN_URL))

        _, changes, _ = service._repo.update.call_args.args
        assert "latitude" not in changes

    async def test_clearing_them_falls_back_to_the_link(self, service):
        service._repo.get.return_value = _location(latitude=1.0, longitude=2.0, maps_url=_PIN_URL)
        service._repo.update.return_value = _location()

        await service.update(1, LocationUpdate(coordinates=""))

        _, changes, _ = service._repo.update.call_args.args
        assert (changes["latitude"], changes["longitude"]) == (41.1579, -8.6291)

    async def test_clearing_them_without_a_link(self, service):
        service._repo.get.return_value = _location(latitude=1.0, longitude=2.0)
        service._repo.update.return_value = _location()

        await service.update(1, LocationUpdate(coordinates=None))

        _, changes, _ = service._repo.update.call_args.args
        assert changes == {"latitude": None, "longitude": None}

    def test_bad_coordinates_are_refused(self):
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            LocationCreate(name="X", coordinates="north")
        with pytest.raises(ValidationError):
            LocationCreate(name="X", coordinates=[95, 0])


class TestToday:
    async def test_open_now_on_a_weekday(self, service, holidays):
        service._repo.list.return_value = [_location(opening_hours=_WEEKDAY_HOURS)]

        [result] = await service.list(LocationFilters())

        assert result.today.date == date(2026, 11, 23)
        assert result.today.hours == "08:00-20:00"
        assert result.today.open_now is True
        assert result.today.holiday is None
        holidays.get_holidays.assert_awaited_once_with(date(2026, 11, 23), date(2026, 11, 23))

    async def test_holiday_closes_a_shop_with_holiday_hours(self, service, holidays):
        holidays.get_holidays.return_value = [_holiday()]
        service._repo.list.return_value = [_location(opening_hours={**_WEEKDAY_HOURS, "hol": []})]

        [result] = await service.list(LocationFilters())

        assert result.today.hours == "closed"
        assert result.today.holiday == "Feriado"
        assert result.today.note == "holiday hours"
        assert result.today.open_now is False

    async def test_holiday_without_holiday_hours_shows_weekday_hours_as_unknown(self, service, holidays):
        holidays.get_holidays.return_value = [_holiday()]
        service._repo.list.return_value = [_location(opening_hours=_WEEKDAY_HOURS)]

        [result] = await service.list(LocationFilters())

        assert result.today.hours == "08:00-20:00"
        assert result.today.note == "holiday, hours unknown"
        assert result.today.open_now is None

    async def test_no_holiday_lookup_when_no_location_has_hours(self, service, holidays):
        service._repo.list.return_value = [_location(), _location(id=2, name="Office", kind="work")]

        results = await service.list(LocationFilters())

        holidays.get_holidays.assert_not_called()
        assert [r.today.hours for r in results] == [None, None]
        assert [r.today.open_now for r in results] == [None, None]

    async def test_failing_holiday_provider_is_treated_as_no_holiday(self, service, holidays):
        holidays.get_holidays.side_effect = RuntimeError("down")
        service._repo.list.return_value = [_location(opening_hours=_WEEKDAY_HOURS)]

        [result] = await service.list(LocationFilters())

        assert result.today.holiday is None
        assert result.today.open_now is True

    async def test_without_a_provider(self, service):
        service._holidays = None
        service._repo.get.return_value = _location(opening_hours={"mon": []})

        result = await service.get(1)

        assert result.today.hours == "closed" and result.today.open_now is False


class TestFind:
    async def test_digits_look_up_by_id(self, service):
        service._repo.get.return_value = _location(id=5)

        assert (await service.find(" 5 ")).id == 5
        service._repo.get.assert_awaited_once_with(5)

    async def test_text_looks_up_by_name(self, service):
        service._repo.get_by_name.return_value = _location(name="Market")

        assert (await service.find("market")).name == "Market"

    async def test_missing(self, service):
        service._repo.get_by_name.return_value = None

        assert await service.find("nowhere") is None


class TestCategoryIdsFor:
    async def test_names_resolve_case_insensitively_in_order(self, service):
        service._repo.get_categories_by_name.return_value = [_category(2, "Bakery"), _category(1, "groceries")]

        assert await service.category_ids_for(["Groceries", " bakery", "groceries"]) == [1, 2]

    async def test_unknown_name(self, service):
        service._repo.get_categories_by_name.return_value = []

        with pytest.raises(LocationValidationError, match="hardware"):
            await service.category_ids_for(["hardware"])


class TestDelete:
    async def test_a_location_with_travel_times_is_kept_and_named(self, service):
        service._repo.get.return_value = _location(name="Office")
        office, home = SimpleNamespace(name="Office"), SimpleNamespace(name="Home")
        service._travel_times.list_for.return_value = [
            SimpleNamespace(origin=home, destination=office, mode="metro", minutes=50),
        ]

        with pytest.raises(LocationConflictError, match="Home → Office by metro \\(50 min\\).*archive"):
            await service.delete(1)
        service._repo.delete.assert_not_awaited()

    async def test_deletes(self, service):
        location = _location()
        service._repo.get.return_value = location

        assert await service.delete(1) is True
        service._repo.delete.assert_awaited_once_with(location)

    async def test_not_found(self, service):
        service._repo.get.return_value = None

        assert await service.delete(1) is False


_TODAY = date(2026, 11, 23)


class TestHomeAddressSnapshot:
    """Before the home address changes, trips that have started keep the one they were planned with."""

    @pytest.fixture
    def home(self, service):
        home = _location(id=2, name="Home", kind="home", address="Rua Antiga 2")
        service._repo.get.return_value = home
        service._repo.get_by_name.return_value = home
        service._repo.get_home.return_value = home
        service._repo.update.return_value = home
        return home

    async def test_address_change_snapshots_the_old_address_before_saving(self, service, home, home_snapshot):
        order = []
        home_snapshot.side_effect = lambda *a: order.append("snapshot") or 1
        service._repo.update.side_effect = lambda *a: order.append("save") or home

        await service.update(2, LocationUpdate(address="Rua Nova 3"))

        home_snapshot.assert_awaited_once_with("Rua Antiga 2", _TODAY)
        assert order == ["snapshot", "save"]

    async def test_clearing_the_address_snapshots_it(self, service, home, home_snapshot):
        await service.update(2, LocationUpdate(address=""))

        home_snapshot.assert_awaited_once_with("Rua Antiga 2", _TODAY)

    async def test_other_edits_and_the_same_address_do_not(self, service, home, home_snapshot):
        await service.update(2, LocationUpdate(notes="Blue door", address="Rua Antiga 2"))

        home_snapshot.assert_not_awaited()

    async def test_home_that_stops_being_home_snapshots_its_address(self, service, home, home_snapshot):
        await service.update(2, LocationUpdate(kind="other"))

        home_snapshot.assert_awaited_once_with("Rua Antiga 2", _TODAY)

    async def test_a_home_without_an_address_has_nothing_to_keep(self, service, home, home_snapshot):
        home.address = None

        await service.update(2, LocationUpdate(address="Rua Nova 3"))

        home_snapshot.assert_not_awaited()

    async def test_other_locations_never_snapshot(self, service, home_snapshot):
        shop = _location(id=5, address="Rua Loja 1")
        service._repo.get.return_value = shop
        service._repo.update.return_value = shop

        await service.update(5, LocationUpdate(address="Rua Loja 9"))
        await service.update(5, LocationUpdate(kind="home"))

        home_snapshot.assert_not_awaited()

    async def test_creating_home_has_nothing_to_keep(self, service, home_snapshot):
        service._repo.create.return_value = _location(kind="home", address="Rua Nova 3")

        await service.create(LocationCreate(name="Home", kind="home", address="Rua Nova 3"))

        home_snapshot.assert_not_awaited()

    async def test_deleting_home_snapshots_its_address_first(self, service, home, home_snapshot):
        assert await service.delete(2) is True

        home_snapshot.assert_awaited_once_with("Rua Antiga 2", _TODAY)
        service._repo.delete.assert_awaited_once_with(home)

    async def test_without_a_snapshot_hook_nothing_breaks(self, service, home):
        service._home_snapshot = None

        await service.update(2, LocationUpdate(address="Rua Nova 3"))
