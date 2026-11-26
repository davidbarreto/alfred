"""Travel's read-only city and country lists, the photo links and the trip photo album (DB mocked)."""
from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy.dialects import postgresql

from app import dependencies as deps
from app.features.travel.cities.repository import TravelCityRepository
from app.features.travel.cities.schemas import TravelCityRow, TravelLocationFilters
from app.features.travel.cities.service import (
    TravelCityService, best_status, city_status, last_visit, nights_by_city, sort_rows, stay_nights,
)
from app.features.travel.trips.schemas import TripCreate, TripRead, TripUpdate
from app.main import app
from app.shared.utils.links import photo_album_label, photos_search_url

AUTH = {"Authorization": "Bearer test-api-token"}
NOW = datetime(2026, 11, 1, tzinfo=timezone.utc)
TODAY = date(2026, 11, 25)


def _trip(id, start, end, album=None):
    return SimpleNamespace(id=id, name=f"Trip {id}", start_date=start, end_date=end, photo_album_url=album)


def _at(year, month, day, hour, minute=0):
    return datetime(year, month, day, hour, minute, tzinfo=timezone.utc)


def _filters(**kw):
    return TravelLocationFilters(**{"q": None, "country_id": None, "status": "all", "sort": "name", "desc": False, "limit": 50, "offset": 0, **kw})


def _row(id, name, **kw):
    return TravelCityRow(id=id, name=name, country={"id": 1, "name": "Examplia", "code": None}, **kw)


class TestLinks:
    def test_photos_search_encodes_spaces_and_accents(self):
        assert photos_search_url(" Rio de Janeiro ") == "https://photos.google.com/search/Rio%20de%20Janeiro"
        assert photos_search_url("Zürich/Old") == "https://photos.google.com/search/Z%C3%BCrich%2FOld"

    @pytest.mark.parametrize("url, label", [
        ("https://photos.app.goo.gl/abc", "Google Photos"), ("https://photos.google.com/share/x", "Google Photos"),
        ("https://www.icloud.com/sharedalbum/#B0", "iCloud"), ("https://www.flickr.com/photos/x/albums/1", "Flickr"),
        ("https://1drv.ms/a/s!x", "OneDrive"), ("https://example.com/album", "Photo album"),
        ("https://notphotos.google.com.evil.example/x", "Photo album"), (None, None), ("", None),
    ])
    def test_album_label(self, url, label):
        assert photo_album_label(url) == label


class TestTripAlbum:
    def test_http_only_and_blank_clears(self):
        assert TripUpdate(photo_album_url=" https://photos.app.goo.gl/x ").photo_album_url == "https://photos.app.goo.gl/x"
        assert TripUpdate(photo_album_url="").photo_album_url is None
        assert "photo_album_url" in TripUpdate(photo_album_url="").model_fields_set
        with pytest.raises(ValidationError, match="http"):
            TripUpdate(photo_album_url="javascript:alert(1)")
        with pytest.raises(ValidationError):
            TripCreate(name="T", start_date=TODAY, end_date=TODAY, photo_album_url="ftp://x")

    def test_read_has_the_label(self):
        trip = SimpleNamespace(
            id=1, name="T", start_date=TODAY, end_date=TODAY, travelers=None, preferences=None, checklist_note_id=None,
            notes=None, default_tag_names=None, photo_album_url="https://www.icloud.com/sharedalbum/x", tags=[],
            created_at=NOW, updated_at=NOW,
        )
        assert TripRead.model_validate(trip).photo_album_label == "iCloud"


class TestHelpers:
    def test_road_trip_nights_are_check_in_to_check_out_per_city(self):
        """The shape of a 10-day road trip: four stays back to back, plus a city that is only a leg end (no stay)."""
        stays = [(1, _at(2026, 8, 21, 15), _at(2026, 8, 23, 10)), (2, _at(2026, 8, 23, 15), _at(2026, 8, 26, 10)),
                 (3, _at(2026, 8, 26, 15), _at(2026, 8, 29, 10)), (4, _at(2026, 8, 29, 15), _at(2026, 8, 30, 10))]
        nights = nights_by_city([(c, i, o, "Europe/Madrid") for c, i, o in stays], TODAY)
        assert {c: len(d) for c, d in nights.items()} == {1: 2, 2: 3, 3: 3, 4: 1}
        assert 5 not in nights

    def test_overlapping_stays_count_once(self):
        spans = [(1, _at(2026, 3, 1, 15), _at(2026, 3, 4, 10)), (1, _at(2026, 3, 3, 15), _at(2026, 3, 5, 10))]
        assert len(nights_by_city([(c, i, o, "UTC") for c, i, o in spans], TODAY)[1]) == 4

    def test_nights_stop_at_today_and_a_future_stay_has_none(self):
        assert stay_nights(_at(2026, 11, 23, 15), _at(2026, 11, 28, 10), "UTC", TODAY) == {
            date(2026, 11, 23), date(2026, 11, 24), date(2026, 11, 25)}
        assert stay_nights(_at(2026, 12, 17, 15), _at(2026, 12, 20, 10), "UTC", TODAY) == set()
        assert stay_nights(_at(2026, 3, 1, 15), _at(2026, 3, 1, 20), "UTC", TODAY) == set()

    def test_nights_use_the_stays_local_dates(self):
        # 23:30 UTC on 1 March is already 2 March in Tokyo; the check-out is 4 March there too.
        assert stay_nights(_at(2026, 3, 1, 23, 30), _at(2026, 3, 3, 23, 0), "Asia/Tokyo", TODAY) == {
            date(2026, 3, 2), date(2026, 3, 3)}

    def test_last_visit_is_the_later_of_trips_and_local_visits(self):
        trips = [_trip(1, date(2026, 3, 1), date(2026, 3, 5)), _trip(3, date(2026, 12, 17), date(2026, 12, 24))]
        assert last_visit(trips, None, TODAY) == date(2026, 3, 1)
        assert last_visit(trips, date(2026, 6, 2), TODAY) == date(2026, 6, 2)
        assert last_visit([], None, TODAY) is None

    def test_sort_by_a_number_then_by_name(self):
        rows = [_row(1, "beta", trips=2), _row(2, "Alpha", trips=2), _row(3, "Gamma", trips=5)]
        assert [r.id for r in sort_rows(rows, _filters(sort="trips", desc=True))] == [3, 2, 1]
        assert [r.id for r in sort_rows(rows, _filters())] == [2, 1, 3]
        assert [r.id for r in sort_rows(rows, _filters(desc=True))] == [3, 1, 2]

    def test_sort_by_last_visit_puts_undated_rows_last(self):
        rows = [_row(1, "A"), _row(2, "B", last_visit=date(2026, 1, 1)), _row(3, "C", last_visit=date(2026, 5, 1))]
        assert [r.id for r in sort_rows(rows, _filters(sort="last_visit", desc=True))] == [3, 2, 1]
        assert [r.id for r in sort_rows(rows, _filters(sort="last_visit"))] == [2, 3, 1]

    def test_a_city_has_one_status_best_first(self):
        lived, visited, planned, legs = {1, 7}, {2, 3, 7}, {3, 4}, {1, 2, 3, 4, 5}
        assert [city_status(i, 1, lived, visited, planned, legs) for i in (1, 7, 2, 3, 4, 5, 6)] == [
            "home", "lived", "visited", "visited", "planned", "passed", "none"]
        assert city_status(1, None, set(), visited, planned, legs) == "passed"

    def test_a_country_takes_its_best_citys_status(self):
        assert best_status(["passed", "planned", "none"]) == "planned"
        assert best_status(["visited", "home"]) == "home"
        assert best_status([]) == "none"

    def test_the_status_filter_groups_home_with_visited(self):
        rows = [_row(1, "A", status="home"), _row(2, "B", status="visited"), _row(3, "C", status="planned"),
                _row(4, "D", status="passed"), _row(5, "E"), _row(6, "F", status="lived")]
        assert [r.id for r in sort_rows(rows, _filters(status="visited"))] == [1, 2, 6]
        assert [r.id for r in sort_rows(rows, _filters(status="planned"))] == [3]
        assert [r.id for r in sort_rows(rows, _filters(status="passed"))] == [4]
        assert len(sort_rows(rows, _filters())) == 6

    def test_search_and_pages(self):
        rows = [_row(i, f"City {i}") for i in range(1, 6)] + [_row(9, "Other")]
        assert [r.id for r in sort_rows(rows, _filters(q="city", limit=2, offset=2))] == [3, 4]
        assert sort_rows(rows, _filters(sort="spend"))[0].spend_eur == Decimal("0.00")


@pytest.fixture
def service(monkeypatch):
    monkeypatch.setattr("app.features.travel.cities.service.local_today", lambda: TODAY)
    svc = TravelCityService(AsyncMock())
    svc._repo, svc._cities, svc._countries, svc._place_repo = AsyncMock(), AsyncMock(), AsyncMock(), AsyncMock()
    svc._cost_repo, svc._places, svc._residences = AsyncMock(), AsyncMock(), AsyncMock()
    svc._residences.get_all.return_value = []
    svc._cost_repo.get_place_linked_ids.return_value = set()
    svc._cost_repo.get_unlinked_tagged_ids.return_value = set()
    svc._cost_repo.get_cost.return_value = (Decimal("12.50"), 1, 0)
    return svc


def _country(id=1, name="Examplia", code="EX"):
    return SimpleNamespace(id=id, name=name, code=code, default_tag_names=None)


def _city(id, name, country):
    return SimpleNamespace(id=id, name=name, country_id=country.id, country=country, default_tag_names=None)


class TestLists:
    def _data(self, service):
        examplia, testland = _country(), _country(2, "Testland", None)
        cities = [_city(1, "Alpha", examplia), _city(2, "Beta", examplia), _city(3, "Gamma", testland)]
        service._cities.get_cities.return_value = cities
        service._countries.get_countries.return_value = [examplia, testland, _country(3, "Linked only", "LO")]
        service._repo.get_travel_city_ids.return_value = {1, 2}
        service._places.get_home.return_value = None
        # Alpha was been to; Beta has only a planned place and a leg end.
        service._repo.get_status_city_ids.return_value = ({1}, {1, 2}, {2})
        service._repo.get_link_country_ids.return_value = {3}
        service._repo.get_trip_city_pairs.return_value = [(10, 1), (10, 2), (11, 1)]
        service._repo.get_trips.return_value = [
            _trip(10, date(2026, 3, 1), date(2026, 3, 4)), _trip(11, date(2026, 12, 17), date(2026, 12, 20)),
        ]
        service._repo.get_last_local_visits.return_value = {2: date(2026, 9, 9)}
        service._repo.get_place_ids_by_city.side_effect = lambda ids: {i: [i * 100] for i in ids}
        # Alpha: 3 nights in March; Beta: 2 nights overlapping Alpha's dates (same country: they count once there).
        service._repo.get_stay_spans.return_value = [
            (1, _at(2026, 3, 1, 15), _at(2026, 3, 4, 10), "UTC"), (2, _at(2026, 3, 2, 15), _at(2026, 3, 4, 10), "UTC"),
        ]

    async def test_cities_with_travel_data_only(self, service):
        self._data(service)
        rows = await service.list_cities(_filters())
        assert [(r.name, r.trips, r.nights, r.last_visit) for r in rows] == [
            ("Alpha", 2, 3, date(2026, 3, 1)), ("Beta", 1, 2, date(2026, 9, 9)),
        ]
        assert rows[0].spend_eur == Decimal("12.50") and rows[0].photos_url.endswith("/search/Alpha")
        assert [r.status for r in rows] == ["visited", "planned"]

    async def test_the_home_city_is_listed_without_travel_data_and_its_country_is_home(self, service):
        self._data(service)
        service._places.get_home.return_value = SimpleNamespace(city_id=3)
        cities = await service.list_cities(_filters(status="visited"))
        assert [(r.name, r.status, r.trips) for r in cities] == [("Alpha", "visited", 2), ("Gamma", "home", 0)]
        countries = await service.list_countries(_filters())
        assert [(r.name, r.status) for r in countries] == [("Examplia", "visited"), ("Linked only", "none"), ("Testland", "home")]
        assert [r.name for r in await service.list_countries(_filters(status="planned"))] == []

    async def test_countries_count_each_trip_once(self, service):
        self._data(service)
        rows = await service.list_countries(_filters())
        assert [(r.name, r.cities, r.trips, r.nights) for r in rows] == [("Examplia", 2, 2, 3), ("Linked only", 0, 0, 0)]
        assert rows[0].last_visit == date(2026, 9, 9) and rows[0].status == "visited"

    async def test_detail_has_nights_counts_and_last_visit(self, service):
        service._cities.get_city.return_value = SimpleNamespace(
            id=1, name="Alpha", country_id=1, country=_country(), default_tag_names=None, created_at=NOW, updated_at=NOW,
        )
        service._repo.get_place_ids_by_city.return_value = {1: []}
        service._place_repo.get_grades.return_value = {}
        service._repo.get_places.return_value = []
        service._repo.get_trips_of_cities.return_value = [_trip(10, date(2026, 3, 1), date(2026, 3, 4), "https://flickr.com/a")]
        service._repo.get_last_local_visits.return_value = {}
        service._places.get_home.return_value = None
        service._repo.get_stay_spans.return_value = [(1, _at(2026, 3, 1, 15), _at(2026, 3, 3, 10), "UTC")]
        service._repo.count_stays.return_value = 1
        service._repo.count_leg_ends.return_value = 2
        detail = await service.get_city_detail(1)
        assert (detail.nights, detail.stay_count, detail.leg_count, detail.last_visit) == (2, 1, 2, date(2026, 3, 1))
        assert detail.trips[0].photo_album_label == "Flickr"
        assert detail.photos_url.endswith("/search/Alpha")


def _session():
    session = AsyncMock()
    session.execute.return_value = MagicMock()
    session.scalars.return_value = MagicMock()
    return session


class TestStaysAndLegs:
    def _place(self):
        city = SimpleNamespace(id=1, name="Alpha", country=SimpleNamespace(id=1, name="Examplia", code="EX"))
        return SimpleNamespace(name="Hotel Example", kind="hotel", city=city)

    async def test_stays_carry_the_trip_name_place_and_local_nights(self, service):
        service._cities.get_city.return_value = SimpleNamespace(id=1)
        service._repo.get_stays.return_value = [SimpleNamespace(
            id=4, trip_id=10, place_id=7, place=self._place(), check_in_at=_at(2026, 8, 23, 13), check_out_at=_at(2026, 8, 26, 8),
            timezone="Europe/Madrid",
        ), SimpleNamespace(
            id=5, trip_id=None, place_id=7, place=self._place(), check_in_at=_at(2026, 3, 1, 13), check_out_at=_at(2026, 3, 2, 8),
            timezone="UTC",
        )]
        service._repo.get_trip_names.return_value = {10: "Road trip"}
        page = SimpleNamespace(limit=21, offset=0)
        rows = await service.list_city_stays(1, page)
        assert [(r.id, r.trip_name, r.place_name, r.nights) for r in rows] == [(4, "Road trip", "Hotel Example", 3), (5, None, "Hotel Example", 1)]
        assert rows[0].check_in_local == datetime(2026, 8, 23, 15, 0) and rows[0].city.name == "Alpha"
        service._repo.get_stays.assert_awaited_with([1], 21, 0)
        service._repo.get_trip_names.assert_awaited_with({10})

    async def test_country_stays_cover_its_cities_and_unknowns_are_none(self, service):
        service._countries.get_country.return_value = SimpleNamespace(id=2)
        service._cities.get_country_cities.return_value = [SimpleNamespace(id=1), SimpleNamespace(id=3)]
        service._repo.get_stays.return_value = []
        service._repo.get_trip_names.return_value = {}
        assert await service.list_country_stays(2, SimpleNamespace(limit=5, offset=0)) == []
        service._repo.get_stays.assert_awaited_with([1, 3], 5, 0)
        service._countries.get_country.return_value = None
        service._cities.get_city.return_value = None
        assert await service.list_country_stays(9, SimpleNamespace(limit=5, offset=0)) is None
        assert await service.list_city_stays(9, SimpleNamespace(limit=5, offset=0)) is None
        assert await service.list_city_legs(9, SimpleNamespace(limit=5, offset=0)) is None

    async def test_legs_carry_the_trip_name_and_local_times(self, service):
        service._cities.get_city.return_value = SimpleNamespace(id=1)
        city = self._place().city
        service._repo.get_legs.return_value = [SimpleNamespace(
            id=3, trip_id=10, mode="car", origin="Alpha", destination="Beta", origin_city=city, destination_city=None,
            departs_at=_at(2026, 8, 23, 22), departs_tz="Europe/Madrid", arrives_at=_at(2026, 8, 24, 0), arrives_tz="Europe/Madrid",
        )]
        service._repo.get_trip_names.return_value = {10: "Road trip"}
        [leg] = await service.list_city_legs(1, SimpleNamespace(limit=6, offset=0))
        assert (leg.trip_name, leg.mode, leg.origin_city.name, leg.destination_city) == ("Road trip", "car", "Alpha", None)
        assert leg.departs_local == datetime(2026, 8, 24, 0, 0) and leg.arrives_local == datetime(2026, 8, 24, 2, 0)


class TestRepositorySql:
    async def _compiled(self, call):
        session = _session()
        await call(TravelCityRepository(session))
        stmt = (session.execute.await_args or session.scalars.await_args).args[0]
        return str(stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))

    async def test_status_city_ids(self):
        session = _session()
        session.scalars.return_value = MagicMock(all=lambda: [1])
        assert await TravelCityRepository(session).get_status_city_ids() == ({1}, {1}, {1})
        visited, planned, legs = (
            str(c.args[0].compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))
            for c in session.scalars.await_args_list
        )
        assert "travel.visits.status = 'visited'" in visited and "check_in_at <= now()" in visited
        assert "travel.visits.status = 'planned'" in planned and "check_in_at > now()" in planned
        assert "travel.legs.destination_city_id IS NOT NULL" in legs

    async def test_travel_city_ids(self):
        sql = await self._compiled(lambda r: r.get_travel_city_ids())
        assert "UNION" in sql and "travel.links.city_id" in sql and "travel.legs.origin_city_id" in sql

    async def test_trip_city_pairs(self):
        sql = await self._compiled(lambda r: r.get_trip_city_pairs([1, 2]))
        assert "JOIN location.places" in sql and "travel.stays.trip_id IS NOT NULL" in sql

    async def test_stay_spans_join_the_places(self):
        sql = await self._compiled(lambda r: r.get_stay_spans([1, 2]))
        assert "JOIN location.places" in sql and "location.places.city_id IN (1, 2)" in sql and "travel.stays.timezone" in sql

    async def test_stays_newest_first_and_paged(self):
        sql = await self._compiled(lambda r: r.get_stays([1], 21, 20))
        assert "ORDER BY travel.stays.check_in_at DESC" in sql and "LIMIT 21" in sql and "OFFSET 20" in sql

    async def test_legs_of_either_end_newest_first(self):
        sql = await self._compiled(lambda r: r.get_legs(4, 6, 0))
        assert "travel.legs.origin_city_id = 4 OR travel.legs.destination_city_id = 4" in sql
        assert "ORDER BY travel.legs.departs_at DESC" in sql and "LIMIT 6" in sql

    async def test_no_cities_no_stay_query(self):
        session = _session()
        repo = TravelCityRepository(session)
        assert await repo.get_stay_spans([]) == [] and await repo.get_stays([], 5, 0) == [] and await repo.count_stays([]) == 0
        assert await repo.get_trip_names(set()) == {}
        session.execute.assert_not_awaited()

    async def test_last_local_visits(self):
        session = _session()
        await TravelCityRepository(session).get_last_local_visits([1], TODAY)
        for call in session.execute.await_args_list:
            sql = str(call.args[0].compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))
            assert "GROUP BY location.places.city_id" in sql and "'2026-11-25'" in sql


class TestRoutes:
    @pytest.fixture
    def client(self):
        service = AsyncMock()
        app.dependency_overrides[deps.get_travel_city_service] = lambda: service
        yield TestClient(app), service
        app.dependency_overrides.clear()

    def test_lists(self, client):
        c, service = client
        service.list_cities.return_value = [_row(1, "Alpha", trips=2)]
        service.list_countries.return_value = []
        response = c.get("/travel/cities?sort=trips&desc=true&limit=5", headers=AUTH)
        assert response.status_code == 200 and response.json()[0]["trips"] == 2
        filters = service.list_cities.await_args.args[0]
        assert (filters.sort, filters.desc, filters.limit, filters.status) == ("trips", True, 5, "all")
        assert response.json()[0]["status"] == "none"
        c.get("/travel/countries?status=passed", headers=AUTH)
        assert service.list_countries.await_args.args[0].status == "passed"
        assert c.get("/travel/cities?status=home", headers=AUTH).status_code == 422
        assert c.get("/travel/countries", headers=AUTH).json() == []

    def test_bad_sort_is_422(self, client):
        c, _ = client
        assert c.get("/travel/cities?sort=grade", headers=AUTH).status_code == 422
        assert c.get("/travel/cities?sort=days", headers=AUTH).status_code == 422
        assert c.get("/travel/cities?sort=nights", headers=AUTH).status_code == 200

    def test_stays_and_legs_pages(self, client):
        c, service = client
        service.list_city_stays.return_value = []
        service.list_city_legs.return_value = []
        service.list_country_stays.return_value = []
        assert c.get("/travel/cities/4/stays?limit=21&offset=20", headers=AUTH).json() == []
        page = service.list_city_stays.await_args.args[1]
        assert (page.limit, page.offset) == (21, 20)
        assert c.get("/travel/cities/4/legs", headers=AUTH).status_code == 200
        assert c.get("/travel/countries/2/stays", headers=AUTH).status_code == 200
        assert c.get("/travel/cities/4/legs?limit=0", headers=AUTH).status_code == 422

    @pytest.mark.parametrize("path, method", [
        ("/travel/cities/9/stays", "list_city_stays"), ("/travel/cities/9/legs", "list_city_legs"),
        ("/travel/countries/9/stays", "list_country_stays"),
    ])
    def test_unknown_owner_is_404(self, client, path, method):
        c, service = client
        getattr(service, method).return_value = None
        assert c.get(path, headers=AUTH).status_code == 404


class TestPlacesLived:
    """Synthetic shape: born in Gamma (Testland) until 2005, living in Alpha (Examplia) since 2019."""

    def _data(self, service):
        TestLists()._data(service)
        testland, examplia = _country(2, "Testland", None), _country()
        service._residences.get_all.return_value = [
            SimpleNamespace(city_id=1, city=_city(1, "Alpha", examplia), from_date=date(2019, 3, 1), to_date=None, born=False),
            SimpleNamespace(city_id=3, city=_city(3, "Gamma", testland), from_date=None, to_date=date(2005, 3, 1), born=True),
        ]
        # Alpha's March 2026 nights fall while living there; Beta's (same country) too, but Beta itself was not lived in.
        service._places.get_home.return_value = SimpleNamespace(city_id=1)
        service._repo.get_trip_city_pairs.return_value = [(10, 1), (10, 2), (11, 1), (12, 3)]
        service._repo.get_trips.return_value = [
            _trip(10, date(2026, 3, 1), date(2026, 3, 4)), _trip(11, date(2026, 12, 17), date(2026, 12, 20)),
            _trip(12, date(2010, 7, 1), date(2010, 7, 9)),
        ]

    async def test_city_nights_leave_out_dates_lived_in_that_city_only(self, service):
        self._data(service)
        rows = {r.name: r for r in await service.list_cities(_filters())}
        assert (rows["Alpha"].nights, rows["Beta"].nights) == (0, 2)
        assert (rows["Alpha"].status, rows["Gamma"].status) == ("home", "lived")
        assert (rows["Alpha"].living, rows["Alpha"].lived_since) == (True, date(2019, 3, 1))
        assert (rows["Gamma"].born, rows["Gamma"].lived_until, rows["Gamma"].trips_since) == (True, date(2005, 3, 1), 1)

    async def test_country_nights_leave_out_dates_lived_in_the_country(self, service):
        self._data(service)
        rows = {r.name: r for r in await service.list_countries(_filters(status="visited"))}
        assert rows["Examplia"].nights == 0 and rows["Examplia"].living and not rows["Examplia"].born
        assert (rows["Testland"].status, rows["Testland"].born, rows["Testland"].trips_since) == ("lived", True, 1)

    async def test_a_lived_city_without_travel_data_is_listed_as_visited(self, service):
        self._data(service)
        service._repo.get_travel_city_ids.return_value = set()
        service._repo.get_trip_city_pairs.return_value = [(12, 3)]
        assert [r.name for r in await service.list_cities(_filters(status="visited"))] == ["Alpha", "Gamma"]
