from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

import pytest

from app.features.briefing.schemas import HolidayItem
from app.features.location.errors import LocationConflictError, LocationNotFoundError, LocationValidationError
from app.features.location.places.schemas import PlaceCreate, PlaceUpdate
from app.features.location.places.service import HomeValues, PlaceService

_NOW = datetime(2026, 11, 1, tzinfo=timezone.utc)
# A Monday, 10:30 local time.
_LOCAL_NOW = datetime(2026, 11, 23, 10, 30, tzinfo=ZoneInfo("Europe/Lisbon"))
_WEEKDAY_HOURS = {d: [["08:00", "20:00"]] for d in ("mon", "tue", "wed", "thu", "fri")}
_HOMETOWN = SimpleNamespace(id=15, name="Hometown", country=SimpleNamespace(id=1, name="Testland", code="TL"))
_FARAWAY = SimpleNamespace(id=16, name="Faraway", country=SimpleNamespace(id=2, name="Farland", code=None))


def _place(**kwargs):
    fields = dict(
        id=1, name="Market", kind="supermarket", city_id=15, city=_HOMETOWN, address=None, maps_url=None,
        latitude=None, longitude=None, opening_hours=None, notes=None, active=True, created_at=_NOW, updated_at=_NOW,
    )
    fields.update(kwargs)
    return SimpleNamespace(**fields)


_HOME = _place(id=9, name="Casa", kind="home", address="Old street 1")


def _holiday(name="Feriado"):
    return HolidayItem(name=name, local_name=name, country="PT", days_until=0, date=_LOCAL_NOW.date())


@pytest.fixture(autouse=True)
def _monday_morning(monkeypatch):
    monkeypatch.setattr("app.features.location.places.service.local_now", lambda: _LOCAL_NOW)
    monkeypatch.setattr("app.features.location.places.service.local_today", lambda: _LOCAL_NOW.date())


@pytest.fixture
def holidays():
    provider = AsyncMock()
    provider.get_holidays.return_value = []
    return provider


@pytest.fixture
def home_snapshot():
    return AsyncMock(return_value=2)


@pytest.fixture
def hooks():
    hook = AsyncMock()
    hook.place_in_use.return_value = None
    hook.before_place_delete.return_value = AsyncMock()
    return hook


@pytest.fixture
def service(holidays, home_snapshot, hooks):
    svc = PlaceService(session=AsyncMock(), hooks=[hooks], holiday_provider=holidays, home_snapshot=home_snapshot)
    svc._repo = AsyncMock()
    svc._repo.get_by_name.return_value = []
    svc._repo.get_home.return_value = _HOME
    svc._repo.city_exists.return_value = True
    stored: dict[int, SimpleNamespace] = {}

    async def _add(fields):
        place = _place(id=2, **{**fields, "city": _HOMETOWN if fields["city_id"] == 15 else _FARAWAY})
        stored[place.id] = place
        return place

    svc._repo.add.side_effect = _add
    svc._repo.get.side_effect = lambda place_id: stored.get(place_id)
    svc.stored = stored
    return svc


class TestCreate:
    async def test_parses_hours_and_defaults_to_the_home_city(self, service, hooks):
        result = await service.create(PlaceCreate(name="  Market   by school ", kind=" Supermarket", opening_hours="mon-fri 8-20"))

        fields = service._repo.add.call_args.args[0]
        assert fields["name"] == "Market by school" and fields["kind"] == "supermarket"
        assert fields["city_id"] == 15
        assert fields["opening_hours"] == _WEEKDAY_HOURS
        service._repo.commit.assert_awaited_once()
        hooks.place_saved.assert_awaited_once()
        assert result.opening_hours_text == "mon-fri 08:00-20:00"
        assert result.city.name == "Hometown"

    async def test_default_kind_is_other(self, service):
        await service.create(PlaceCreate(name="Post office"))
        assert service._repo.add.call_args.args[0]["kind"] == "other"

    async def test_no_city_and_no_home_is_a_validation_error(self, service):
        service._repo.get_home.return_value = None
        with pytest.raises(LocationValidationError, match="no Home place"):
            await service.create(PlaceCreate(name="Market"))
        service._repo.add.assert_not_called()

    async def test_unknown_city_is_not_found(self, service):
        service._repo.city_exists.return_value = False
        with pytest.raises(LocationNotFoundError, match="City 99"):
            await service.create(PlaceCreate(name="Market", city_id=99))

    async def test_bad_hours_are_a_validation_error(self, service):
        with pytest.raises(LocationValidationError, match="Opening hours: .*not a day"):
            await service.create(PlaceCreate(name="Market", opening_hours="funday 9-17"))
        service._repo.add.assert_not_called()

    async def test_the_same_name_in_the_same_city_conflicts(self, service):
        service._repo.get_by_name.return_value = [_place(id=4, name="Market")]

        with pytest.raises(LocationConflictError, match="already exists in Hometown"):
            await service.create(PlaceCreate(name="market"))
        service._repo.get_by_name.assert_awaited_once_with("market", 15)

    async def test_the_same_name_in_another_city_is_fine(self, service):
        await service.create(PlaceCreate(name="Market", city_id=16))
        service._repo.get_by_name.assert_awaited_once_with("Market", 16)

    async def test_second_home_is_a_conflict(self, service):
        with pytest.raises(LocationConflictError, match="Home is already set"):
            await service.create(PlaceCreate(name="Flat", kind="home", city_id=15))

    def test_blank_name_is_refused_by_the_schema(self):
        with pytest.raises(ValueError):
            PlaceCreate(name="   ")


class TestUpdate:
    async def test_changing_to_home_when_another_home_exists_conflicts(self, service):
        service.stored[2] = _place(id=2)
        with pytest.raises(LocationConflictError, match="Home is already set"):
            await service.update(2, PlaceUpdate(kind="home"))

    async def test_home_can_be_edited_without_clashing_with_itself(self, service):
        service.stored[9] = _HOME
        service._repo.get_by_name.return_value = [_HOME]

        assert (await service.update(9, PlaceUpdate(name="Casa", kind="home"))).name == "Casa"

    async def test_moving_city_checks_the_name_there(self, service):
        service.stored[2] = _place(id=2)
        service._repo.get_by_name.return_value = [_place(id=7, name="Market", city=_FARAWAY)]

        with pytest.raises(LocationConflictError, match="already exists in Faraway"):
            await service.update(2, PlaceUpdate(city_id=16))
        service._repo.get_by_name.assert_awaited_once_with("Market", 16)

    async def test_blank_hours_clear_them(self, service):
        service.stored[2] = _place(id=2, opening_hours=_WEEKDAY_HOURS)

        await service.update(2, PlaceUpdate(opening_hours=" "))

        assert service._repo.update.call_args.args[1] == {"opening_hours": None}

    @pytest.mark.parametrize("field", ["name", "kind", "city_id", "active"])
    async def test_required_fields_cannot_be_cleared(self, service, field):
        with pytest.raises(LocationValidationError, match="cannot be cleared"):
            await service.update(2, PlaceUpdate(**{field: None}))

    async def test_not_found(self, service):
        assert await service.update(99, PlaceUpdate(notes="x")) is None
        service._repo.update.assert_not_called()


class TestCoordinates:
    async def test_typed_coordinates_are_stored(self, service):
        await service.create(PlaceCreate(name="Market", coordinates="41.1579, -8.6291"))
        fields = service._repo.add.call_args.args[0]
        assert (fields["latitude"], fields["longitude"]) == (41.1579, -8.6291)

    async def test_create_fills_them_from_the_maps_link(self, service):
        await service.create(PlaceCreate(name="Market", maps_url="https://www.google.com/maps/place/X/@41.15,-8.62,17z"))
        fields = service._repo.add.call_args.args[0]
        assert (fields["latitude"], fields["longitude"]) == (41.15, -8.62)

    async def test_update_without_coordinates_fills_them_from_a_new_link(self, service):
        service.stored[2] = _place(id=2)
        await service.update(2, PlaceUpdate(maps_url="https://maps.google.com/?q=41.2,-8.5"))
        assert service._repo.update.call_args.args[1]["latitude"] == 41.2

    async def test_a_new_link_keeps_coordinates_already_set(self, service):
        service.stored[2] = _place(id=2, latitude=40.0, longitude=-8.0)
        await service.update(2, PlaceUpdate(maps_url="https://maps.google.com/?q=41.2,-8.5"))
        assert "latitude" not in service._repo.update.call_args.args[1]

    async def test_clearing_them_falls_back_to_the_link(self, service):
        service.stored[2] = _place(id=2, latitude=40.0, longitude=-8.0, maps_url="https://maps.google.com/?q=41.2,-8.5")
        await service.update(2, PlaceUpdate(coordinates=None))
        changes = service._repo.update.call_args.args[1]
        assert (changes["latitude"], changes["longitude"]) == (41.2, -8.5)


class TestToday:
    async def test_open_now_on_a_weekday(self, service, holidays):
        service.stored[2] = _place(id=2, opening_hours=_WEEKDAY_HOURS)

        today = (await service.get(2)).today

        assert (today.hours, today.open_now, today.holiday) == ("08:00-20:00", True, None)

    async def test_holiday_closes_a_shop_with_holiday_hours(self, service, holidays):
        holidays.get_holidays.return_value = [_holiday()]
        service.stored[2] = _place(id=2, opening_hours={**_WEEKDAY_HOURS, "hol": []})

        today = (await service.get(2)).today

        assert (today.hours, today.open_now, today.holiday, today.note) == ("closed", False, "Feriado", "holiday hours")

    async def test_holiday_without_holiday_hours_is_unknown(self, service, holidays):
        holidays.get_holidays.return_value = [_holiday()]
        service.stored[2] = _place(id=2, opening_hours=_WEEKDAY_HOURS)

        today = (await service.get(2)).today

        assert today.open_now is None and today.note == "holiday, hours unknown"

    async def test_no_holiday_lookup_when_no_place_has_hours(self, service, holidays):
        service.stored[2] = _place(id=2)
        await service.get(2)
        holidays.get_holidays.assert_not_called()

    async def test_failing_holiday_provider_is_treated_as_no_holiday(self, service, holidays):
        holidays.get_holidays.side_effect = RuntimeError("down")
        service.stored[2] = _place(id=2, opening_hours=_WEEKDAY_HOURS)
        assert (await service.get(2)).today.holiday is None


class TestFind:
    async def test_digits_look_up_by_id(self, service):
        service.stored[2] = _place(id=2)
        assert (await service.find(" 2 ")).id == 2

    async def test_a_name_in_the_home_city_wins(self, service):
        service._repo.get_by_name.side_effect = lambda name, city_id=None: [_place(id=3)] if city_id == 15 else []
        assert (await service.find("market")).id == 3

    async def test_a_name_elsewhere_is_found_when_unique(self, service):
        service._repo.get_by_name.side_effect = lambda name, city_id=None: [] if city_id else [_place(id=7, city=_FARAWAY)]
        assert (await service.find("market")).id == 7

    async def test_several_elsewhere_is_a_conflict_listing_them(self, service):
        service._repo.get_by_name.side_effect = lambda name, city_id=None: [] if city_id else [
            _place(id=7, city=_FARAWAY), _place(id=8, city=_HOMETOWN, city_id=15),
        ]
        with pytest.raises(LocationConflictError, match=r"Market in Faraway \(id 7\), Market in Hometown \(id 8\)"):
            await service.find("market")

    async def test_a_given_city_is_searched_alone(self, service):
        await service.find("market", city_id=16)
        service._repo.get_by_name.assert_awaited_once_with("market", 16)


class TestDelete:
    async def test_what_a_domain_holds_is_a_conflict_naming_it(self, service, hooks):
        service.stored[2] = _place(id=2, name="Gym")
        hooks.place_in_use.return_value = "it has 2 travel time(s)"

        with pytest.raises(LocationConflictError, match="'Gym' can't be deleted: it has 2 travel time"):
            await service.delete(2)
        service._repo.delete.assert_not_called()

    async def test_deletes_and_runs_the_hooks_after_the_commit(self, service, hooks):
        service.stored[2] = _place(id=2)
        after = AsyncMock()
        hooks.before_place_delete.return_value = after

        assert await service.delete(2) is True

        service._repo.delete.assert_awaited_once()
        service._repo.commit.assert_awaited_once()
        after.assert_awaited_once()

    async def test_a_foreign_key_that_still_holds_it_is_a_conflict(self, service):
        from sqlalchemy.exc import IntegrityError

        service.stored[2] = _place(id=2)
        service._repo.commit.side_effect = IntegrityError("DELETE", {}, Exception("fk"))

        with pytest.raises(LocationConflictError, match="still in use"):
            await service.delete(2)
        service._repo.rollback.assert_awaited_once()

    async def test_not_found(self, service):
        assert await service.delete(99) is False


class TestHomeSnapshot:
    @pytest.fixture
    def home(self, service):
        service.stored[9] = _HOME
        service._repo.get_by_name.return_value = [_HOME]
        return _HOME

    async def test_address_change_snapshots_the_old_address_before_saving(self, service, home, home_snapshot):
        await service.update(9, PlaceUpdate(address="New street 2"))
        home_snapshot.assert_awaited_once_with(HomeValues(address="Old street 1"), _LOCAL_NOW.date())

    async def test_city_change_snapshots_the_old_city(self, service, home, home_snapshot):
        service._repo.get_by_name.return_value = []
        await service.update(9, PlaceUpdate(city_id=16))
        home_snapshot.assert_awaited_once_with(HomeValues(city_id=15), _LOCAL_NOW.date())

    async def test_moving_to_another_city_snapshots_both(self, service, home, home_snapshot):
        service._repo.get_by_name.return_value = []
        await service.update(9, PlaceUpdate(city_id=16, address="Far street 3"))
        home_snapshot.assert_awaited_once_with(HomeValues(address="Old street 1", city_id=15), _LOCAL_NOW.date())

    async def test_other_edits_and_the_same_address_and_city_do_not(self, service, home, home_snapshot):
        await service.update(9, PlaceUpdate(notes="Ring twice", address="Old street 1", city_id=15))
        home_snapshot.assert_not_called()

    async def test_home_that_stops_being_home_snapshots_its_address_and_city(self, service, home, home_snapshot):
        await service.update(9, PlaceUpdate(kind="other"))
        home_snapshot.assert_awaited_once_with(HomeValues(address="Old street 1", city_id=15), _LOCAL_NOW.date())

    async def test_a_home_without_address_still_snapshots_its_city(self, service, home_snapshot):
        service.stored[9] = _place(id=9, name="Casa", kind="home")
        service._repo.get_by_name.return_value = []
        await service.update(9, PlaceUpdate(city_id=16))
        home_snapshot.assert_awaited_once_with(HomeValues(city_id=15), _LOCAL_NOW.date())

    async def test_other_places_never_snapshot(self, service, home_snapshot):
        service.stored[2] = _place(id=2, address="Shop street")
        service._repo.get_by_name.return_value = []
        await service.update(2, PlaceUpdate(address="Other street", city_id=16))
        home_snapshot.assert_not_called()

    async def test_deleting_home_snapshots_its_address_and_city_first(self, service, home, home_snapshot):
        await service.delete(9)
        home_snapshot.assert_awaited_once_with(HomeValues(address="Old street 1", city_id=15), _LOCAL_NOW.date())
