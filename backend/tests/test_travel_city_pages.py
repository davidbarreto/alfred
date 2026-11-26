from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.dialects import postgresql

from app import dependencies as deps
from app.features.location.cities.tables import City
from app.features.travel.cities.hooks import TravelLocationHooks
from app.features.travel.cities.repository import TravelCityRepository
from app.features.travel.cities.service import TravelCityService
from app.features.travel.errors import TravelConflictError, TravelNotFoundError
from app.features.travel.legs.schemas import LegRead
from app.features.travel.places.repository import TravelPlaceRepository
from app.features.travel.places.schemas import TravelPlaceFilters
from app.features.travel.stays.schemas import StayRead
from app.features.travel.places.schemas import TravelPlaceRead
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
    place = TravelPlaceRead(id=1, kind="hotel", name="Hotel Example", city=city_ref(city), maps_url=None, latitude=None, longitude=None,
                      address=None, notes=None, created_at=NOW, updated_at=NOW)
    return StayRead(id=1, trip_id=1, place_id=1, place=place, check_in_at=check_in, check_out_at=check_in.replace(day=check_in.day + 1),
                    timezone="UTC", booking_ref=None, booking_url=None, notes=None, grade=None, created_at=NOW, updated_at=NOW)


def _visit(city, day, status="planned"):
    place = VisitPlace(id=2, kind="museum", name="Museum Example", city=city_ref(city), maps_url=None, latitude=None, longitude=None)
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
    svc = TravelCityService(AsyncMock())
    svc._repo, svc._cities, svc._countries, svc._place_repo = AsyncMock(), AsyncMock(), AsyncMock(), AsyncMock()
    svc._cost_repo, svc._places, svc._residences = AsyncMock(), AsyncMock(), AsyncMock()
    svc._places.get_home.return_value = None
    svc._residences.get_all.return_value = []
    svc._repo.get_last_local_visits.return_value = {}
    svc._cost_repo.get_place_linked_ids.return_value = set()
    svc._cost_repo.get_unlinked_tagged_ids.return_value = set()
    svc._cost_repo.get_cost.return_value = (Decimal("0.00"), 0, 0)
    return svc


class TestCityDetail:
    async def test_unknown_city(self, service):
        service._cities.get_city.return_value = None
        assert await service.get_city_detail(9) is None

    async def test_grade_is_the_mean_of_the_graded_places_and_counts_them(self, service):
        service._cities.get_city.return_value = _city_row()
        service._repo.get_place_ids_by_city.return_value = {1: [10, 11, 12]}
        service._place_repo.get_grades.return_value = {10: (4.0, 2), 11: (3.0, 1)}
        service._repo.get_places.return_value = [SimpleNamespace(id=10, name="A", kind="cafe")]
        service._repo.get_trips_of_cities.return_value = []
        detail = await service.get_city_detail(1)
        assert (detail.grade, detail.grade_count, detail.place_count) == (3.5, 2, 3)
        assert detail.places[0].grade == 4.0

    async def test_no_graded_place_means_no_grade(self, service):
        service._cities.get_city.return_value = _city_row()
        service._repo.get_place_ids_by_city.return_value = {1: [10]}
        service._place_repo.get_grades.return_value = {}
        service._repo.get_places.return_value = []
        service._repo.get_trips_of_cities.return_value = []
        detail = await service.get_city_detail(1)
        assert (detail.grade, detail.grade_count) == (None, 0)

    async def test_only_five_places_are_asked_for(self, service):
        service._cities.get_city.return_value = _city_row()
        service._repo.get_place_ids_by_city.return_value = {1: list(range(8))}
        service._place_repo.get_grades.return_value = {}
        service._repo.get_places.return_value = []
        service._repo.get_trips_of_cities.return_value = []
        await service.get_city_detail(1)
        assert service._repo.get_places.await_args.args[1] == 5


class TestCountryDetail:
    async def test_grade_is_the_mean_of_the_city_means(self, service):
        country = SimpleNamespace(id=2, name="Examplia", code="EX", created_at=NOW, updated_at=NOW, default_tag_names=None)
        service._countries.get_country.return_value = country
        service._cities.get_country_cities.return_value = [_city_row(1, "Alpha"), _city_row(3, "Beta"), _city_row(4, "Gamma")]
        service._repo.get_place_ids_by_city.return_value = {1: [10], 3: [11, 12], 4: []}
        service._place_repo.get_grades.return_value = {10: (5.0, 1), 11: (3.0, 1), 12: (4.0, 1)}
        service._repo.get_trips_of_cities.return_value = []
        detail = await service.get_country_detail(2)
        assert (detail.grade, detail.grade_count) == (4.25, 2)
        assert [(c.name, c.place_count, c.grade) for c in detail.cities] == [("Alpha", 1, 5.0), ("Beta", 2, 3.5), ("Gamma", 0, None)]


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
        await TravelCityRepository(session).get_trips_of_cities([1, 2])
        sql = self._sql(session.statements[0])
        assert "UNION" in sql and "travel.stays" in sql and "travel.visits" in sql and "travel.legs" in sql
        assert "origin_city_id IN (1, 2)" in sql and "ORDER BY travel.trips.start_date DESC" in sql

    async def test_no_cities_no_query(self):
        session = self._Session()
        assert await TravelCityRepository(session).get_trips_of_cities([]) == []
        assert session.statements == []

    async def test_places_filter_by_city_id_and_country_id(self):
        session = self._Session()
        await TravelPlaceRepository(session).get_places(TravelPlaceFilters(city_id=4, country_id=2))
        sql = self._sql(session.statements[0])
        assert "location.places.city_id = 4" in sql and "location.cities.country_id = 2" in sql


class TestRoutes:
    @pytest.fixture
    def client(self):
        svc = AsyncMock()
        app.dependency_overrides[deps.get_travel_city_service] = lambda: svc
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

    def test_charges_404(self, client):
        c, svc = client
        svc.get_city_charges.return_value = None
        svc.get_country_charges.return_value = None
        assert c.get("/travel/cities/9/charges", headers=AUTH).status_code == 404
        assert c.get("/travel/countries/9/charges", headers=AUTH).status_code == 404


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
        service._cities.get_city.return_value = SimpleNamespace(**{**_city_row().__dict__, "default_tag_names": "Lisbon, Trip"})
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
        service._cities.get_city.return_value = _city_row()
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
        service._countries.get_country.return_value = country
        service._cities.get_country_cities.return_value = [city_a, city_b]
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

    async def test_city_charges_are_the_ids_behind_each_spend_part(self, service):
        service._cities.get_city.return_value = SimpleNamespace(**{**_city_row().__dict__, "default_tag_names": "Trip"})
        service._repo.get_place_ids_by_city.return_value = {1: [10]}
        service._place_repo.get_grades.return_value = {}
        service._cost_repo.get_place_linked_ids.return_value = {1, 2}
        service._cost_repo.get_unlinked_tagged_ids.return_value = {2, 3}
        service._cost_repo.get_transactions.side_effect = lambda ids: [
            SimpleNamespace(id=i, date=NOW, merchant="M", description=None, bank_description=None, type="expense",
                            amount=Decimal("1.00"), currency="EUR", amount_eur=Decimal("1.00"))
            for i in sorted(ids)
        ]
        service._cost_repo.get_cost.side_effect = lambda ids: (Decimal(len(ids)), len(ids), 0)
        found = {part: await service.get_city_charges(1, part) for part in ("linked", "tagged", "overall")}
        assert {part: [t.id for t in f.transactions] for part, f in found.items()} == {
            "linked": [1, 2], "tagged": [3], "overall": [1, 2, 3],  # 2 is linked, so not tagged
        }

    async def test_country_charges_merge_every_tag_group_once_and_unknowns_are_none(self, service):
        service._countries.get_country.return_value = SimpleNamespace(id=2, default_tag_names="spain")
        service._cities.get_country_cities.return_value = [SimpleNamespace(id=1, default_tag_names="alpha")]
        service._repo.get_place_ids_by_city.return_value = {1: [10]}
        service._place_repo.get_grades.return_value = {}
        service._cost_repo.get_place_linked_ids.return_value = set()
        by_tags = {("spain",): {5, 6}, ("alpha",): {6, 7}}
        service._cost_repo.get_unlinked_tagged_ids.side_effect = lambda names: by_tags[tuple(names)]
        service._cost_repo.get_transactions.return_value = []
        service._cost_repo.get_cost.side_effect = lambda ids: (Decimal(len(ids)), len(ids), 0)
        assert (await service.get_country_charges(2, "tagged")).cost.transaction_count == 3
        service._countries.get_country.return_value = None
        service._cities.get_city.return_value = None
        assert await service.get_country_charges(9, "overall") is None
        assert await service.get_city_charges(9, "overall") is None


class TestHome:
    async def test_the_home_city_is_flagged_on_its_page(self, service):
        service._cities.get_city.return_value = _city_row()
        service._repo.get_place_ids_by_city.return_value = {1: []}
        service._place_repo.get_grades.return_value = {}
        service._repo.get_places.return_value = []
        service._repo.get_trips_of_cities.return_value = []
        service._places.get_home.return_value = SimpleNamespace(city_id=1)
        assert (await service.get_city_detail(1)).home is True
        service._places.get_home.return_value = SimpleNamespace(city_id=9)
        assert (await service.get_city_detail(1)).home is False
        service._places.get_home.return_value = None
        assert (await service.get_city_detail(1)).home is False


@pytest.fixture
def hooks():
    h = TravelLocationHooks(AsyncMock())
    h._repo, h._trip_repo, h._link_repo, h._places, h._notes = AsyncMock(), AsyncMock(), AsyncMock(), AsyncMock(), AsyncMock()
    h._places.get_home.return_value = None
    h._repo.count_places.return_value = 0
    h._repo.count_leg_ends.return_value = 0
    h._trip_repo.count_home_city_trips.return_value = 0
    return h


class TestHooks:
    async def test_an_unused_city_is_not_in_use(self, hooks):
        assert await hooks.city_in_use(_city_row()) is None

    async def test_places_leg_ends_and_trip_homes_are_named(self, hooks):
        hooks._repo.count_places.return_value = 2
        hooks._repo.count_leg_ends.return_value = 3
        hooks._trip_repo.count_home_city_trips.return_value = 1
        assert await hooks.city_in_use(_city_row()) == "Alpha is used by 2 place(s), 3 leg end(s) and 1 trip home(s)"

    async def test_the_home_city_is_in_use(self, hooks):
        hooks._places.get_home.return_value = SimpleNamespace(city_id=1)
        assert await hooks.city_in_use(_city_row()) == "Alpha is the home city (the Home place is there)"

    async def test_a_new_city_gets_the_leg_ends_with_its_name(self, hooks):
        hooks._repo.attach_leg_ends.return_value = 2
        city = _city_row(id=4, name="Beta")
        await hooks.city_created(city)
        hooks._repo.attach_leg_ends.assert_awaited_once_with(city)

    async def test_the_link_notes_are_dropped_only_when_the_delete_is_done(self, hooks):
        hooks._link_repo.get_link_ids.return_value = [5, 6]
        after = await hooks.before_delete(city_id=1)
        hooks._link_repo.get_link_ids.assert_awaited_once_with(city_id=1, country_id=None)
        hooks._notes.remove.assert_not_awaited()
        await after()
        assert hooks._notes.remove.await_count == 2

    async def test_attaching_leg_ends_only_touches_ends_without_a_city_matched_on_trimmed_lowercase_text(self):
        class _Session:
            def __init__(self):
                self.statements = []

            async def execute(self, stmt):
                self.statements.append(stmt)
                return SimpleNamespace(rowcount=1)

        session = _Session()
        attached = await TravelCityRepository(session).attach_leg_ends(City(id=4, name="Porto", country_id=1))
        sql = [str(st.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})) for st in session.statements]
        assert attached == 2 and len(sql) == 2
        assert "origin_city_id IS NULL" in sql[0] and "lower(trim(travel.legs.origin)) = 'porto'" in sql[0]
        assert "destination_city_id IS NULL" in sql[1] and "SET destination_city_id=4" in sql[1].replace(" = ", "=")


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
