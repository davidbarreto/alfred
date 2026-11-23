from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.dialects import postgresql

from app.features.organizer.locations.errors import LocationValidationError
from app.features.organizer.locations.schemas import LocationTravelTimeSet
from app.features.organizer.locations.travel_time_repository import LocationTravelTimeRepository
from app.features.organizer.locations.travel_time_service import LocationTravelTimeService, route_label, route_name

_NOW = datetime(2026, 11, 1, tzinfo=timezone.utc)
_HOME = SimpleNamespace(id=1, name="Casa", kind="home")
_OFFICE = SimpleNamespace(id=2, name="Office", kind="work")
_SCHOOL = SimpleNamespace(id=3, name="School by the Park", kind="school")
_BY_ID = {loc.id: loc for loc in (_HOME, _OFFICE, _SCHOOL)}


def _travel_time(id, origin, destination, mode, minutes):
    return SimpleNamespace(
        id=id, origin=origin, destination=destination, origin_id=origin.id, destination_id=destination.id,
        mode=mode, minutes=minutes, created_at=_NOW, updated_at=_NOW,
    )


@pytest.fixture
def service():
    svc = LocationTravelTimeService(session=AsyncMock())
    svc._repo = AsyncMock()
    svc._repo.find.return_value = None
    svc._repo.count.return_value = 0
    svc._locations = AsyncMock()
    svc._locations.get.side_effect = lambda location_id: _BY_ID.get(location_id)
    svc._locations.get_home.return_value = _HOME
    svc._locations.get_by_name.side_effect = lambda name: next(
        (loc for loc in _BY_ID.values() if loc.name.lower() == name), None
    )
    return svc


class TestNames:
    def test_home_is_always_called_home_and_others_are_lowercase(self):
        assert route_name(_HOME) == "home"
        assert route_name(_SCHOOL) == "school by the park"

    def test_label(self):
        assert route_label(_travel_time(1, _HOME, _OFFICE, "metro", 50)) == "Casa → Office by metro (50 min)"


class TestPreferences:
    async def test_rows_come_back_in_the_planning_settings_shape(self, service):
        """Same shape and names as the old planning.travel_times setting, so clients see no change."""
        service._repo.list_all.return_value = [
            _travel_time(1, _HOME, _OFFICE, "metro", 50), _travel_time(2, _OFFICE, _SCHOOL, "car", 20),
        ]

        assert await service.as_preferences() == [
            {"origin": "home", "place": "office", "mode": "metro", "minutes": 50},
            {"origin": "office", "place": "school by the park", "mode": "car", "minutes": 20},
        ]

    async def test_replace_resolves_home_and_names_case_insensitively(self, service):
        await service.replace_from_preferences([("home", "office", "metro", 50), ("office", "school by the park", "car", 20)])

        service._repo.replace_all.assert_awaited_once_with([(1, 2, "metro", 50), (2, 3, "car", 20)])
        service._locations.create.assert_not_awaited()

    async def test_unknown_names_become_locations_with_a_guessed_kind(self, service):
        created = iter([SimpleNamespace(id=7, name="Gym"), SimpleNamespace(id=8, name="Bakery corner")])
        service._locations.create.side_effect = lambda fields, categories: next(created)

        await service.replace_from_preferences([("home", "gym", "foot", 10), ("gym", "bakery corner", "foot", 3)])

        fields = [c.args[0] for c in service._locations.create.await_args_list]
        assert fields == [{"name": "Gym", "kind": "gym"}, {"name": "Bakery corner", "kind": "other"}]
        service._repo.replace_all.assert_awaited_once_with([(1, 7, "foot", 10), (7, 8, "foot", 3)])

    async def test_empty_clears_everything(self, service):
        await service.replace_from_preferences([])

        service._repo.replace_all.assert_awaited_once_with([])


class TestNetwork:
    async def test_names_home_and_routes_of_every_location(self, service):
        service._locations.list.return_value = [_HOME, _OFFICE, _SCHOOL]
        service._repo.list_all.return_value = [_travel_time(1, _HOME, _OFFICE, "metro", 50)]

        network = await service.network()

        assert network.names == {1: "Casa", 2: "Office", 3: "School by the Park"}
        assert network.home_id == 1
        assert network.routes == [(1, 2, "metro", 50)]
        assert service._locations.list.call_args.args[0].active is None  # archived places too

    async def test_no_home(self, service):
        service._locations.list.return_value = [_OFFICE]
        service._repo.list_all.return_value = []
        assert (await service.network()).home_id is None


class TestFindLocation:
    async def test_home_means_the_home_location_whatever_its_name(self, service):
        assert await service.find_location(" HOME ") is _HOME

    async def test_other_names(self, service):
        assert await service.find_location("Office") is _OFFICE
        assert await service.find_location("nowhere") is None


class TestSet:
    async def test_saves_the_route(self, service):
        service._repo.save.return_value = _travel_time(5, _HOME, _OFFICE, "metro", 45)

        result = await service.set(1, LocationTravelTimeSet(destination_id=2, mode=" Metro ", minutes=45))

        service._repo.save.assert_awaited_once_with(1, 2, "metro", 45)
        assert (result.origin.name, result.destination.name, result.minutes) == ("Casa", "Office", 45)

    async def test_unknown_origin_is_none(self, service):
        assert await service.set(99, LocationTravelTimeSet(destination_id=2, mode="car", minutes=5)) is None

    async def test_unknown_destination_or_itself_is_a_validation_error(self, service):
        with pytest.raises(LocationValidationError, match="Unknown location id 99"):
            await service.set(1, LocationTravelTimeSet(destination_id=99, mode="car", minutes=5))
        with pytest.raises(LocationValidationError, match="from itself"):
            await service.set(1, LocationTravelTimeSet(destination_id=1, mode="car", minutes=5))

    async def test_a_new_route_over_the_cap_is_refused_but_an_existing_one_updates(self, service):
        service._repo.count.return_value = 60
        with pytest.raises(LocationValidationError, match="At most 60"):
            await service.set(1, LocationTravelTimeSet(destination_id=2, mode="car", minutes=5))

        service._repo.find.return_value = _travel_time(5, _HOME, _OFFICE, "car", 10)
        service._repo.save.return_value = _travel_time(5, _HOME, _OFFICE, "car", 5)
        assert (await service.set(1, LocationTravelTimeSet(destination_id=2, mode="car", minutes=5))).minutes == 5

    @pytest.mark.parametrize("minutes", [0, 601])
    def test_minutes_are_bounded(self, minutes):
        with pytest.raises(ValueError):
            LocationTravelTimeSet(destination_id=2, mode="car", minutes=minutes)


class TestListAndDelete:
    async def test_list_for_unknown_location_is_none(self, service):
        assert await service.list_for(99) is None

    async def test_list_for(self, service):
        service._repo.list_for.return_value = [_travel_time(1, _HOME, _OFFICE, "metro", 50)]

        [row] = await service.list_for(2)

        assert row.origin.kind == "home" and row.mode == "metro"

    async def test_delete(self, service):
        service._repo.get.return_value = _travel_time(1, _HOME, _OFFICE, "metro", 50)
        assert await service.delete(1) is True
        service._repo.get.return_value = None
        assert await service.delete(1) is False


def _sql(statement) -> str:
    return str(statement.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))


class TestRepository:
    async def test_list_for_matches_either_end(self):
        session = AsyncMock()
        result = MagicMock()
        result.scalars.return_value.all.return_value = []
        session.execute.return_value = result

        await LocationTravelTimeRepository(session).list_for(4)

        sql = _sql(session.execute.call_args.args[0])
        assert "organizer.location_travel_times.origin_id = 4 OR organizer.location_travel_times.destination_id = 4" in sql
