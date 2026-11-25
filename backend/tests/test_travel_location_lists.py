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
from app.features.travel.cities.service import TravelCityService, days_so_far, last_visit, sort_rows
from app.features.travel.trips.schemas import TripCreate, TripRead, TripUpdate
from app.main import app
from app.shared.utils.links import photo_album_label, photos_search_url

AUTH = {"Authorization": "Bearer test-api-token"}
NOW = datetime(2026, 11, 1, tzinfo=timezone.utc)
TODAY = date(2026, 11, 25)


def _trip(id, start, end, album=None):
    return SimpleNamespace(id=id, name=f"Trip {id}", start_date=start, end_date=end, photo_album_url=album)


def _filters(**kw):
    return TravelLocationFilters(**{"q": None, "country_id": None, "sort": "name", "desc": False, "limit": 50, "offset": 0, **kw})


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
    def test_days_so_far_counts_started_trips_up_to_today(self):
        trips = [_trip(1, date(2026, 3, 1), date(2026, 3, 5)), _trip(2, date(2026, 11, 20), date(2026, 11, 30)),
                 _trip(3, date(2026, 12, 17), date(2026, 12, 24))]
        assert days_so_far(trips, TODAY) == 5 + 6

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

    def test_search_and_pages(self):
        rows = [_row(i, f"City {i}") for i in range(1, 6)] + [_row(9, "Other")]
        assert [r.id for r in sort_rows(rows, _filters(q="city", limit=2, offset=2))] == [3, 4]
        assert sort_rows(rows, _filters(sort="spend"))[0].spend_eur == Decimal("0.00")


@pytest.fixture
def service(monkeypatch):
    monkeypatch.setattr("app.features.travel.cities.service.local_today", lambda: TODAY)
    svc = TravelCityService(AsyncMock())
    svc._repo, svc._cities, svc._countries, svc._place_repo = AsyncMock(), AsyncMock(), AsyncMock(), AsyncMock()
    svc._cost_repo, svc._places = AsyncMock(), AsyncMock()
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
        service._repo.get_link_country_ids.return_value = {3}
        service._repo.get_trip_city_pairs.return_value = [(10, 1), (10, 2), (11, 1)]
        service._repo.get_trips.return_value = [
            _trip(10, date(2026, 3, 1), date(2026, 3, 4)), _trip(11, date(2026, 12, 17), date(2026, 12, 20)),
        ]
        service._repo.get_last_local_visits.return_value = {2: date(2026, 9, 9)}
        service._repo.get_place_ids_by_city.side_effect = lambda ids: {i: [i * 100] for i in ids}

    async def test_cities_with_travel_data_only(self, service):
        self._data(service)
        rows = await service.list_cities(_filters())
        assert [(r.name, r.trips, r.days, r.last_visit) for r in rows] == [
            ("Alpha", 2, 4, date(2026, 3, 1)), ("Beta", 1, 4, date(2026, 9, 9)),
        ]
        assert rows[0].spend_eur == Decimal("12.50") and rows[0].photos_url.endswith("/search/Alpha")

    async def test_countries_count_each_trip_once(self, service):
        self._data(service)
        rows = await service.list_countries(_filters())
        assert [(r.name, r.cities, r.trips, r.days) for r in rows] == [("Examplia", 2, 2, 4), ("Linked only", 0, 0, 0)]
        assert rows[0].last_visit == date(2026, 9, 9)

    async def test_detail_has_days_and_last_visit(self, service):
        service._cities.get_city.return_value = SimpleNamespace(
            id=1, name="Alpha", country_id=1, country=_country(), default_tag_names=None, created_at=NOW, updated_at=NOW,
        )
        service._repo.get_place_ids_by_city.return_value = {1: []}
        service._place_repo.get_grades.return_value = {}
        service._repo.get_places.return_value = []
        service._repo.get_trips_of_cities.return_value = [_trip(10, date(2026, 3, 1), date(2026, 3, 4), "https://flickr.com/a")]
        service._repo.get_last_local_visits.return_value = {}
        service._places.get_home.return_value = None
        detail = await service.get_city_detail(1)
        assert (detail.days, detail.last_visit) == (4, date(2026, 3, 1))
        assert detail.trips[0].photo_album_label == "Flickr"
        assert detail.photos_url.endswith("/search/Alpha")


def _session():
    session = AsyncMock()
    session.execute.return_value = MagicMock()
    session.scalars.return_value = MagicMock()
    return session


class TestRepositorySql:
    async def _compiled(self, call):
        session = _session()
        await call(TravelCityRepository(session))
        stmt = (session.execute.await_args or session.scalars.await_args).args[0]
        return str(stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))

    async def test_travel_city_ids(self):
        sql = await self._compiled(lambda r: r.get_travel_city_ids())
        assert "UNION" in sql and "travel.links.city_id" in sql and "travel.legs.origin_city_id" in sql

    async def test_trip_city_pairs(self):
        sql = await self._compiled(lambda r: r.get_trip_city_pairs([1, 2]))
        assert "JOIN location.places" in sql and "travel.stays.trip_id IS NOT NULL" in sql

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
        assert (filters.sort, filters.desc, filters.limit) == ("trips", True, 5)
        assert c.get("/travel/countries", headers=AUTH).json() == []

    def test_bad_sort_is_422(self, client):
        c, _ = client
        assert c.get("/travel/cities?sort=grade", headers=AUTH).status_code == 422
