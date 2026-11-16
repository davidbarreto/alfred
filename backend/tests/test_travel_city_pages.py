from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy.dialects import postgresql

from app import dependencies as deps
from app.features.travel.cities.repository import CityRepository
from app.features.travel.cities.schemas import CityUpdate, CountryUpdate
from app.features.travel.cities.service import CityService
from app.features.travel.errors import TravelConflictError, TravelNotFoundError
from app.features.travel.legs.schemas import LegRead
from app.features.travel.places.repository import PlaceRepository
from app.features.travel.places.schemas import PlaceFilters
from app.features.travel.stays.schemas import StayRead
from app.features.travel.places.schemas import PlaceRead
from app.features.travel.trips.trip_cities import build_trip_cities
from app.features.travel.visits.schemas import VisitPlace, VisitRead
from app.main import app
from travel_city_helpers import city_ref

AUTH = {"Authorization": "Bearer test-api-token"}
NOW = datetime(2026, 11, 1, tzinfo=timezone.utc)


def _dt(day, hour=12):
    return datetime(2026, 12, day, hour, tzinfo=timezone.utc)


def _leg(origin, destination, dep, arr):
    return LegRead(
        id=1, trip_id=1, mode="train", origin="o", destination="d", origin_city=city_ref(origin) if origin else None,
        destination_city=city_ref(destination) if destination else None, origin_code=None, destination_code=None,
        departs_at=dep, arrives_at=arr, departs_tz="UTC", arrives_tz="UTC", carrier=None, number=None, booking_ref=None,
        booking_url=None, seat=None, notes=None, created_at=NOW, updated_at=NOW,
    )


def _stay(city, check_in):
    place = PlaceRead(id=1, kind="hotel", name="Hotel Example", city=city_ref(city), maps_url=None, lat=None, lng=None,
                      address=None, notes=None, created_at=NOW, updated_at=NOW)
    return StayRead(id=1, trip_id=1, place_id=1, place=place, check_in_at=check_in, check_out_at=check_in.replace(day=check_in.day + 1),
                    timezone="UTC", booking_ref=None, booking_url=None, notes=None, grade=None, created_at=NOW, updated_at=NOW)


def _visit(city, day, status="planned"):
    place = VisitPlace(id=2, kind="museum", name="Museum Example", city=city_ref(city), maps_url=None, lat=None, lng=None)
    return VisitRead(id=1, place_id=2, place=place, trip_id=1, trip_name=None, status=status,
                     visit_date=date(2026, 12, day) if day else None, visit_time=None, notes=None, grade=None,
                     created_at=NOW, updated_at=NOW)


class TestTripCities:
    def _run(self, legs=(), stays=(), visits=(), today=date(2026, 12, 1), end=date(2026, 12, 20)):
        found, unmatched = build_trip_cities(list(legs), list(stays), list(visits), today, end)
        return [(c.city.name, c.role) for c in found], unmatched

    def test_a_stay_makes_a_city_stayed_and_a_leg_end_only_passed(self):
        cities, _ = self._run(legs=[_leg("Home", "Alpha", _dt(2), _dt(3))], stays=[_stay("Alpha", _dt(3, 15))])
        assert cities == [("Home", "passed"), ("Alpha", "stayed")]

    def test_cities_come_in_order_of_first_appearance(self):
        cities, _ = self._run(stays=[_stay("Beta", _dt(9)), _stay("Alpha", _dt(4))], visits=[_visit("Gamma", None)])
        assert [name for name, _ in cities] == ["Alpha", "Beta", "Gamma"]

    def test_leg_ends_without_a_city_are_counted(self):
        _, unmatched = self._run(legs=[_leg(None, "Alpha", _dt(2), _dt(3)), _leg("Home", None, _dt(5), _dt(6))])
        assert unmatched == 2

    def test_a_planned_visit_counts_as_staying_only_until_the_trip_ends(self):
        planned = [_visit("Alpha", 5)]
        assert self._run(visits=planned)[0] == [("Alpha", "stayed")]
        assert self._run(visits=planned, today=date(2026, 12, 30))[0] == []

    def test_a_missed_visit_is_not_listed_unless_a_leg_ends_there(self):
        missed = [_visit("Alpha", 5, "missed")]
        assert self._run(visits=missed)[0] == []
        assert self._run(legs=[_leg("Home", "Alpha", _dt(2), _dt(3))], visits=missed)[0] == [("Home", "passed"), ("Alpha", "passed")]

    def test_a_visited_visit_counts_even_after_the_trip(self):
        assert self._run(visits=[_visit("Alpha", 5, "visited")], today=date(2026, 12, 30))[0] == [("Alpha", "stayed")]

    def test_the_same_city_is_listed_once(self):
        cities, _ = self._run(stays=[_stay("Alpha", _dt(3)), _stay("Alpha", _dt(8))])
        assert cities == [("Alpha", "stayed")]


def _city_row(id=1, name="Alpha", country_id=2):
    country = SimpleNamespace(id=country_id, name="Examplia", code=None, created_at=NOW, updated_at=NOW, default_tag_names=None)
    return SimpleNamespace(
        id=id, name=name, country_id=country_id, country=country, created_at=NOW, updated_at=NOW, default_tag_names=None,
    )


@pytest.fixture
def service():
    svc = CityService(AsyncMock())
    svc._repo, svc._place_repo, svc._link_repo, svc._notes = AsyncMock(), AsyncMock(), AsyncMock(), AsyncMock()
    svc._cost_repo, svc._trip_repo, svc._settings = AsyncMock(), AsyncMock(), AsyncMock()
    svc._repo.get_city_in_country.return_value = None
    svc._settings.get_value.return_value = None
    svc._trip_repo.count_home_city_trips.return_value = 0
    svc._cost_repo.get_place_linked_ids.return_value = set()
    svc._cost_repo.get_unlinked_tagged_ids.return_value = set()
    svc._cost_repo.get_cost.return_value = (Decimal("0.00"), 0, 0)
    return svc


class TestCityDetail:
    async def test_unknown_city(self, service):
        service._repo.get_city.return_value = None
        assert await service.get_city_detail(9) is None

    async def test_grade_is_the_mean_of_the_graded_places_and_counts_them(self, service):
        service._repo.get_city.return_value = _city_row()
        service._repo.get_place_ids_by_city.return_value = {1: [10, 11, 12]}
        service._place_repo.get_grades.return_value = {10: (4.0, 2), 11: (3.0, 1)}
        service._repo.get_places.return_value = [SimpleNamespace(id=10, name="A", kind="cafe")]
        service._repo.get_trips_of_cities.return_value = []
        detail = await service.get_city_detail(1)
        assert (detail.grade, detail.grade_count, detail.place_count) == (3.5, 2, 3)
        assert detail.places[0].grade == 4.0

    async def test_no_graded_place_means_no_grade(self, service):
        service._repo.get_city.return_value = _city_row()
        service._repo.get_place_ids_by_city.return_value = {1: [10]}
        service._place_repo.get_grades.return_value = {}
        service._repo.get_places.return_value = []
        service._repo.get_trips_of_cities.return_value = []
        detail = await service.get_city_detail(1)
        assert (detail.grade, detail.grade_count) == (None, 0)

    async def test_only_five_places_are_asked_for(self, service):
        service._repo.get_city.return_value = _city_row()
        service._repo.get_place_ids_by_city.return_value = {1: list(range(8))}
        service._place_repo.get_grades.return_value = {}
        service._repo.get_places.return_value = []
        service._repo.get_trips_of_cities.return_value = []
        await service.get_city_detail(1)
        assert service._repo.get_places.await_args.args[1] == 5


class TestCountryDetail:
    async def test_grade_is_the_mean_of_the_city_means(self, service):
        country = SimpleNamespace(id=2, name="Examplia", code="EX", created_at=NOW, updated_at=NOW, default_tag_names=None)
        service._repo.get_country.return_value = country
        service._repo.get_country_cities.return_value = [_city_row(1, "Alpha"), _city_row(3, "Beta"), _city_row(4, "Gamma")]
        service._repo.get_place_ids_by_city.return_value = {1: [10], 3: [11, 12], 4: []}
        service._place_repo.get_grades.return_value = {10: (5.0, 1), 11: (3.0, 1), 12: (4.0, 1)}
        service._repo.get_trips_of_cities.return_value = []
        detail = await service.get_country_detail(2)
        assert (detail.grade, detail.grade_count) == (4.25, 2)
        assert [(c.name, c.place_count, c.grade) for c in detail.cities] == [("Alpha", 1, 5.0), ("Beta", 2, 3.5), ("Gamma", 0, None)]


class TestEdits:
    async def test_rename_into_a_taken_name_is_a_conflict(self, service):
        service._repo.get_city.return_value = _city_row()
        service._repo.get_city_in_country.return_value = _city_row(id=7, name="Beta")
        with pytest.raises(TravelConflictError):
            await service.update_city(1, CityUpdate(name="Beta"))
        service._repo.update.assert_not_awaited()

    async def test_a_case_change_of_its_own_name_is_fine(self, service):
        service._repo.get_city.return_value = _city_row()
        service._repo.get_city_in_country.return_value = _city_row()
        await service.update_city(1, CityUpdate(name=" ALPHA "))
        assert service._repo.update.await_args.args[1] == {"name": "ALPHA"}

    async def test_moving_to_an_unknown_country_is_not_found(self, service):
        service._repo.get_city.return_value = _city_row()
        service._repo.get_country.return_value = None
        with pytest.raises(TravelNotFoundError):
            await service.update_city(1, CityUpdate(country_id=99))

    async def test_a_code_of_another_country_is_a_conflict(self, service):
        service._repo.get_country.return_value = SimpleNamespace(id=2, name="Examplia", code=None)
        service._repo.get_other_country_by_code.return_value = SimpleNamespace(id=3)
        with pytest.raises(TravelConflictError):
            await service.update_country(2, CountryUpdate(code="ex"))

    async def test_a_null_code_clears_it(self, service):
        service._repo.get_country.return_value = SimpleNamespace(id=2, name="Examplia", code="EX")
        await service.update_country(2, CountryUpdate.model_validate({"code": None}))
        assert service._repo.update.await_args.args[1] == {"code": None}

    def test_the_code_is_uppercased_and_must_be_letters(self):
        assert CountryUpdate(code="gb").code == "GB"
        with pytest.raises(ValidationError):
            CountryUpdate(code="1a")


class TestDeletes:
    async def test_a_city_with_places_or_leg_ends_is_a_conflict_naming_them(self, service):
        service._repo.get_city.return_value = _city_row()
        service._repo.count_places.return_value = 2
        service._repo.count_leg_ends.return_value = 3
        with pytest.raises(TravelConflictError, match="2 place.*3 leg end.*0 trip home"):
            await service.delete_city(1)
        service._repo.delete.assert_not_awaited()

    async def test_an_unused_city_is_deleted_with_its_link_notes(self, service):
        service._repo.get_city.return_value = _city_row()
        service._repo.count_places.return_value = 0
        service._repo.count_leg_ends.return_value = 0
        service._link_repo.get_link_ids.return_value = [5, 6]
        assert await service.delete_city(1) is True
        assert service._notes.remove.await_count == 2

    async def test_unknown_city_is_not_deleted(self, service):
        service._repo.get_city.return_value = None
        assert await service.delete_city(1) is False

    async def test_a_country_with_cities_is_a_conflict(self, service):
        service._repo.get_country.return_value = SimpleNamespace(id=2, name="Examplia")
        service._repo.get_country_cities.return_value = [_city_row()]
        with pytest.raises(TravelConflictError):
            await service.delete_country(2)

    async def test_an_empty_country_is_deleted(self, service):
        service._repo.get_country.return_value = SimpleNamespace(id=2, name="Examplia")
        service._repo.get_country_cities.return_value = []
        service._link_repo.get_link_ids.return_value = []
        assert await service.delete_country(2) is True
        service._repo.delete.assert_awaited_once()


class TestSql:
    class _Session:
        def __init__(self):
            self.statements = []

        async def scalars(self, stmt):
            self.statements.append(stmt)
            return SimpleNamespace(all=lambda: [])

        async def execute(self, stmt):
            self.statements.append(stmt)
            return SimpleNamespace(all=lambda: [])

    @staticmethod
    def _sql(stmt):
        return str(stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))

    async def test_trips_of_cities_look_at_stays_visits_and_leg_ends(self):
        session = self._Session()
        await CityRepository(session).get_trips_of_cities([1, 2])
        sql = self._sql(session.statements[0])
        assert "UNION" in sql and "travel.stays" in sql and "travel.visits" in sql and "travel.legs" in sql
        assert "origin_city_id IN (1, 2)" in sql and "ORDER BY travel.trips.start_date DESC" in sql

    async def test_no_cities_no_query(self):
        session = self._Session()
        assert await CityRepository(session).get_trips_of_cities([]) == []
        assert session.statements == []

    async def test_places_filter_by_city_id_and_country_id(self):
        session = self._Session()
        await PlaceRepository(session).get_places(PlaceFilters(city_id=4, country_id=2))
        sql = self._sql(session.statements[0])
        assert "travel.places.city_id = 4" in sql and "travel.cities.country_id = 2" in sql


class TestRoutes:
    @pytest.fixture
    def client(self):
        svc = AsyncMock()
        app.dependency_overrides[deps.get_city_service] = lambda: svc
        yield TestClient(app), svc
        app.dependency_overrides.clear()

    def test_get_city_404(self, client):
        c, svc = client
        svc.get_city_detail.return_value = None
        assert c.get("/travel/cities/9", headers=AUTH).status_code == 404

    def test_get_country_404(self, client):
        c, svc = client
        svc.get_country_detail.return_value = None
        assert c.get("/travel/countries/9", headers=AUTH).status_code == 404

    def test_delete_conflict_and_missing_and_ok(self, client):
        c, svc = client
        svc.delete_city.side_effect = TravelConflictError("in use")
        assert c.delete("/travel/cities/1", headers=AUTH).status_code == 409
        svc.delete_city.side_effect = None
        svc.delete_city.return_value = False
        assert c.delete("/travel/cities/1", headers=AUTH).status_code == 404
        svc.delete_city.return_value = True
        assert c.delete("/travel/cities/1", headers=AUTH).status_code == 204
        svc.delete_country.return_value = True
        assert c.delete("/travel/countries/1", headers=AUTH).status_code == 204

    def test_patch_conflicts_and_unknown(self, client):
        c, svc = client
        svc.update_city.side_effect = TravelConflictError("exists")
        assert c.patch("/travel/cities/1", headers=AUTH, json={"name": "B"}).status_code == 409
        svc.update_city.side_effect = TravelNotFoundError("Country 9 not found")
        assert c.patch("/travel/cities/1", headers=AUTH, json={"country_id": 9}).status_code == 404
        svc.update_country.side_effect = TravelConflictError("exists")
        assert c.patch("/travel/countries/1", headers=AUTH, json={"code": "EX"}).status_code == 409
        assert c.patch("/travel/countries/1", headers=AUTH, json={"code": "1"}).status_code == 422


class TestLinkRoutes:
    @pytest.fixture
    def client(self):
        svc = AsyncMock()
        app.dependency_overrides[deps.get_web_link_service] = lambda: svc
        yield TestClient(app), svc
        app.dependency_overrides.clear()

    def _link(self, **kw):
        base = {"id": 1, "trip_id": None, "place_id": None, "city_id": 4, "country_id": None, "url": "https://example.com/a",
                "kind": "website", "title": None, "description": None, "image_url": None, "notes": None,
                "created_at": NOW.isoformat(), "updated_at": NOW.isoformat()}
        return {**base, **kw}

    def test_city_links_list_and_create(self, client):
        c, svc = client
        svc.get_city_links.return_value = [self._link()]
        assert c.get("/travel/cities/4/links", headers=AUTH).json()[0]["city_id"] == 4
        svc.create_city_link.return_value = self._link()
        assert c.post("/travel/cities/4/links", headers=AUTH, json={"url": "https://example.com/a"}).status_code == 201

    def test_country_links_list_and_create(self, client):
        c, svc = client
        svc.get_country_links.return_value = [self._link(city_id=None, country_id=2)]
        assert c.get("/travel/countries/2/links", headers=AUTH).json()[0]["country_id"] == 2
        svc.create_country_link.return_value = self._link(city_id=None, country_id=2)
        assert c.post("/travel/countries/2/links", headers=AUTH, json={"url": "https://example.com/a"}).status_code == 201

    def test_unknown_owner_is_404_and_a_duplicate_409(self, client):
        c, svc = client
        svc.get_city_links.side_effect = TravelNotFoundError("City 9 not found")
        assert c.get("/travel/cities/9/links", headers=AUTH).status_code == 404
        svc.create_country_link.side_effect = TravelConflictError("This link is already saved here")
        assert c.post("/travel/countries/2/links", headers=AUTH, json={"url": "https://example.com/a"}).status_code == 409
        svc.create_city_link.side_effect = TravelNotFoundError("City 9 not found")
        assert c.post("/travel/cities/9/links", headers=AUTH, json={"url": "https://example.com/a"}).status_code == 404
        svc.get_country_links.side_effect = TravelNotFoundError("nope")
        assert c.get("/travel/countries/9/links", headers=AUTH).status_code == 404
        svc.create_country_link.side_effect = TravelNotFoundError("nope")
        assert c.post("/travel/countries/9/links", headers=AUTH, json={"url": "https://example.com/a"}).status_code == 404
        svc.create_city_link.side_effect = TravelConflictError("dup")
        assert c.post("/travel/cities/4/links", headers=AUTH, json={"url": "https://example.com/a"}).status_code == 409


class TestSpendAndTags:
    async def test_linked_spend_comes_from_the_citys_places_and_tagged_spend_is_what_nothing_else_counts(self, service):
        service._repo.get_city.return_value = SimpleNamespace(**{**_city_row().__dict__, "default_tag_names": "Lisbon, Trip"})
        service._repo.get_place_ids_by_city.return_value = {1: [10, 11]}
        service._place_repo.get_grades.return_value = {}
        service._repo.get_places.return_value = []
        service._repo.get_trips_of_cities.return_value = []
        service._cost_repo.get_place_linked_ids.return_value = {1, 2}
        service._cost_repo.get_unlinked_tagged_ids.return_value = {2, 3}
        sums = {frozenset({1, 2}): "50.00", frozenset({3}): "20.00", frozenset({1, 2, 3}): "70.00"}
        service._cost_repo.get_cost.side_effect = lambda ids: (Decimal(sums[frozenset(ids)]), len(ids), 0)
        detail = await service.get_city_detail(1)
        service._cost_repo.get_place_linked_ids.assert_awaited_once_with([10, 11])
        service._cost_repo.get_unlinked_tagged_ids.assert_awaited_once_with(["lisbon", "trip"])
        assert (detail.costs.linked.total_eur, detail.costs.tagged.total_eur, detail.costs.overall.total_eur) == (
            Decimal("50.00"), Decimal("20.00"), Decimal("70.00"))
        assert detail.costs.tagged.transaction_count == 1 and detail.default_tag_names == "Lisbon, Trip"

    async def test_a_city_without_tags_asks_for_no_tagged_charges_beyond_an_empty_set(self, service):
        service._repo.get_city.return_value = _city_row()
        service._repo.get_place_ids_by_city.return_value = {1: []}
        service._place_repo.get_grades.return_value = {}
        service._repo.get_places.return_value = []
        service._repo.get_trips_of_cities.return_value = []
        await service.get_city_detail(1)
        service._cost_repo.get_unlinked_tagged_ids.assert_awaited_once_with([])

    async def test_a_country_counts_each_transaction_once_across_its_cities_and_its_own_tags(self, service):
        country = SimpleNamespace(id=2, name="Examplia", code=None, created_at=NOW, updated_at=NOW, default_tag_names="spain")
        city_a = SimpleNamespace(**{**_city_row(1, "Alpha").__dict__, "default_tag_names": "alpha"})
        city_b = SimpleNamespace(**{**_city_row(3, "Beta").__dict__, "default_tag_names": None})
        service._repo.get_country.return_value = country
        service._repo.get_country_cities.return_value = [city_a, city_b]
        service._repo.get_place_ids_by_city.return_value = {1: [10], 3: [11]}
        service._place_repo.get_grades.return_value = {}
        service._repo.get_trips_of_cities.return_value = []
        by_tags = {("spain",): {5, 6}, ("alpha",): {6, 7}, (): set()}
        service._cost_repo.get_unlinked_tagged_ids.side_effect = lambda names: by_tags[tuple(names)]
        service._cost_repo.get_cost.side_effect = lambda ids: (Decimal(len(ids)), len(ids), 0)
        detail = await service.get_country_detail(2)
        service._cost_repo.get_place_linked_ids.assert_awaited_once_with([10, 11])
        assert detail.costs.tagged.transaction_count == 3  # 5, 6 and 7, with 6 counted once
        assert detail.costs.overall.transaction_count == 3

    async def test_blank_default_tags_are_stored_as_null(self, service):
        service._repo.get_city.return_value = _city_row()
        await service.update_city(1, CityUpdate(default_tag_names="  "))
        assert service._repo.update.await_args.args[1] == {"default_tag_names": None}

    async def test_the_tags_are_saved_trimmed(self, service):
        service._repo.get_country.return_value = SimpleNamespace(id=2, name="Examplia", code=None)
        await service.update_country(2, CountryUpdate(default_tag_names=" spain, travel "))
        assert service._repo.update.await_args.args[1] == {"default_tag_names": "spain, travel"}


class TestHome:
    async def test_the_home_city_is_flagged_on_its_page(self, service):
        service._repo.get_city.return_value = _city_row()
        service._repo.get_place_ids_by_city.return_value = {1: []}
        service._place_repo.get_grades.return_value = {}
        service._repo.get_places.return_value = []
        service._repo.get_trips_of_cities.return_value = []
        service._settings.get_value.return_value = "1"
        assert (await service.get_city_detail(1)).home is True
        service._settings.get_value.return_value = "9"
        assert (await service.get_city_detail(1)).home is False

    async def test_the_home_city_cannot_be_deleted(self, service):
        service._repo.get_city.return_value = _city_row()
        service._repo.count_places.return_value = 0
        service._repo.count_leg_ends.return_value = 0
        service._settings.get_value.return_value = "1"
        with pytest.raises(TravelConflictError, match="home city"):
            await service.delete_city(1)

    async def test_a_city_that_is_the_home_of_a_trip_cannot_be_deleted(self, service):
        service._repo.get_city.return_value = _city_row()
        service._repo.count_places.return_value = 0
        service._repo.count_leg_ends.return_value = 0
        service._trip_repo.count_home_city_trips.return_value = 2
        with pytest.raises(TravelConflictError, match="2 trip home"):
            await service.delete_city(1)


class TestCostSql:
    class _Session:
        def __init__(self):
            self.statement = None

        async def scalars(self, stmt):
            self.statement = stmt
            return SimpleNamespace(all=lambda: [])

    async def test_tagged_ids_have_no_date_window_and_leave_out_anything_linked(self):
        from app.features.travel.transaction_links.repository import TransactionLinkRepository

        session = self._Session()
        assert await TransactionLinkRepository(session).get_unlinked_tagged_ids(["Spain", "Trip"]) == set()
        sql = str(session.statement.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))
        assert "date" not in sql.lower().replace("transactions", "")
        assert "NOT IN" in sql and "legs_transactions" in sql and "stays_transactions" in sql and "visits_transactions" in sql
        assert "'expense', 'income'" in sql and "'spain'" in sql and "'trip'" in sql

    async def test_no_tags_no_query(self):
        from app.features.travel.transaction_links.repository import TransactionLinkRepository

        session = self._Session()
        assert await TransactionLinkRepository(session).get_unlinked_tagged_ids([]) == set()
        assert session.statement is None

    async def test_place_linked_ids_cover_stays_and_visits_of_the_places(self):
        from app.features.travel.transaction_links.repository import TransactionLinkRepository

        session = self._Session()
        await TransactionLinkRepository(session).get_place_linked_ids([3, 4])
        sql = str(session.statement.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))
        assert "UNION" in sql and "place_id IN (3, 4)" in sql
