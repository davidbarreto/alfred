from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from freezegun import freeze_time
from sqlalchemy.dialects import postgresql

from app.features.travel.errors import TravelNotFoundError
from app.features.travel.settings_schemas import TravelSettingsRead
from app.features.travel.trips.home import effective_home
from app.features.travel.trips.repository import TripRepository
from app.features.travel.trips.schemas import TripUpdate
from app.features.travel.trips.service import TripService
from app.features.travel.trips.trip_cities import build_trip_cities
from test_travel_city_pages import _leg, _stay, _dt
from travel_city_helpers import city_ref

SETTINGS = TravelSettingsRead(airport_buffer_min=120, home_to_airport_min=45, home_address="Rua Exemplo 1", home_city_id=7)


def _trip(**kw):
    base = dict(home_city_id=None, home_address=None, airport_buffer_min=None, home_to_airport_min=None)
    base.update(kw)
    return SimpleNamespace(**base)


class TestEffectiveHome:
    def test_a_trip_without_values_follows_the_settings(self):
        home = effective_home(_trip(), SETTINGS)
        assert (home.city_id, home.address, home.airport_buffer_min, home.home_to_airport_min) == (7, "Rua Exemplo 1", 120, 45)
        assert home.from_trip is False

    def test_each_value_comes_from_the_trip_when_it_has_one(self):
        home = effective_home(_trip(home_city_id=9, airport_buffer_min=60), SETTINGS)
        assert (home.city_id, home.address, home.airport_buffer_min, home.home_to_airport_min) == (9, "Rua Exemplo 1", 60, 45)
        assert home.from_trip is True

    def test_zero_minutes_is_a_value_not_a_missing_one(self):
        assert effective_home(_trip(airport_buffer_min=0), SETTINGS).airport_buffer_min == 0


class TestHomeRole:
    def test_the_home_city_wins_over_stayed_and_passed(self):
        legs = [_leg("Alpha", "Beta", _dt(2), _dt(3))]
        cities, _ = build_trip_cities(legs, [_stay("Beta", _dt(3))], [], date(2026, 12, 1), date(2026, 12, 20), city_ref("Alpha").id)
        assert [(c.city.name, c.role) for c in cities] == [("Alpha", "home"), ("Beta", "stayed")]

    def test_a_home_city_the_trip_never_touches_is_not_listed(self):
        cities, _ = build_trip_cities([], [_stay("Beta", _dt(3))], [], date(2026, 12, 1), date(2026, 12, 20), city_ref("Elsewhere").id)
        assert [c.city.name for c in cities] == ["Beta"]


class TestSnapshotSql:
    class _Session:
        def __init__(self):
            self.statement = None

        async def execute(self, stmt):
            self.statement = stmt
            return SimpleNamespace(rowcount=3)

        async def commit(self):
            pass

    async def test_only_started_trips_with_no_value_of_their_own_are_touched(self):
        session = self._Session()
        count = await TripRepository(session).snapshot_home_value("airport_buffer_min", 90, date(2026, 11, 16))
        sql = str(session.statement.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))
        assert count == 3
        assert "airport_buffer_min IS NULL" in sql and "start_date <= '2026-11-16'" in sql and "SET airport_buffer_min=90" in sql


class TestTripUpdateHome:
    @pytest.fixture
    def service(self):
        svc = TripService(AsyncMock())
        svc._repo, svc._city_repo, svc._tag_repo = AsyncMock(), AsyncMock(), AsyncMock()
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        svc._repo.get_trip.return_value = SimpleNamespace(
            id=1, name="T", start_date=date(2026, 12, 17), end_date=date(2026, 12, 20), notes=None, travelers=None,
            preferences=None, checklist_note_id=None, default_tag_names=None, tags=[], home_city_id=None, home_address=None,
            airport_buffer_min=None, home_to_airport_min=None, created_at=now, updated_at=now,
        )
        svc._repo.update_trip.side_effect = lambda trip, changes, tags: trip
        return svc

    async def test_an_unknown_home_city_is_not_found(self, service):
        service._city_repo.get_city.return_value = None
        with pytest.raises(TravelNotFoundError):
            await service.update_trip(1, TripUpdate(home_city_id=99))
        service._repo.update_trip.assert_not_awaited()

    async def test_null_makes_the_trip_follow_the_settings_again(self, service):
        await service.update_trip(1, TripUpdate.model_validate({"home_city_id": None, "home_address": None}))
        assert service._repo.update_trip.await_args.args[1] == {"home_city_id": None, "home_address": None}

    async def test_a_blank_address_is_stored_as_null(self, service):
        await service.update_trip(1, TripUpdate(home_address="   "))
        assert service._repo.update_trip.await_args.args[1] == {"home_address": None}
