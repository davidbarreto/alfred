from __future__ import annotations

from datetime import date, datetime, timezone
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


@pytest.fixture
def holidays():
    provider = AsyncMock()
    provider.get_holidays.return_value = []
    return provider


@pytest.fixture
def service(holidays):
    svc = LocationService(session=AsyncMock(), holiday_provider=holidays)
    svc._repo = AsyncMock()
    svc._repo.get_by_name.return_value = None
    svc._repo.get_home.return_value = None
    svc._repo.get_categories.return_value = []
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
    async def test_deletes(self, service):
        location = _location()
        service._repo.get.return_value = location

        assert await service.delete(1) is True
        service._repo.delete.assert_awaited_once_with(location)

    async def test_not_found(self, service):
        service._repo.get.return_value = None

        assert await service.delete(1) is False
