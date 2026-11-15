from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy.dialects import postgresql

from app import dependencies as deps
from app.features.travel.cities.repository import CityRepository
from app.features.travel.cities.schemas import CityCreate, CityFilters
from app.features.travel.cities.service import CityResolver, CityService
from app.features.travel.cities.tables import City, Country
from app.features.travel.errors import TravelConflictError, TravelNotFoundError
from app.main import app

AUTH = {"Authorization": "Bearer test-api-token"}
NOW = datetime(2026, 11, 1, tzinfo=timezone.utc)


def _country(id=1, name="Examplia", code=None):
    return SimpleNamespace(id=id, name=name, code=code, created_at=NOW, updated_at=NOW)


def _city(id=1, name="Alpha", country=None):
    country = country or _country()
    return SimpleNamespace(id=id, name=name, country_id=country.id, country=country, created_at=NOW, updated_at=NOW)


@pytest.fixture
def repo():
    r = AsyncMock()
    r.get_country_by_code.return_value = None
    r.get_country_by_name.return_value = None
    r.get_city_in_country.return_value = None
    r.attach_leg_ends.return_value = 0
    return r


class TestResolveCountry:
    async def test_a_known_code_wins_over_a_different_name(self, repo):
        repo.get_country_by_code.return_value = _country(name="United Kingdom", code="GB")
        found = await CityResolver(repo).resolve_country("UK", "gb")
        assert found.name == "United Kingdom"
        repo.get_country_by_code.assert_awaited_once_with("GB")
        repo.create_country.assert_not_awaited()

    async def test_a_name_match_ignores_case_and_fills_a_missing_code(self, repo):
        existing = _country(name="Examplia", code=None)
        repo.get_country_by_name.return_value = existing
        found = await CityResolver(repo).resolve_country("examplia", "EX")
        assert found is existing
        repo.set_country_code.assert_awaited_once_with(existing, "EX")

    async def test_a_name_match_keeps_an_existing_code(self, repo):
        repo.get_country_by_name.return_value = _country(code="EX")
        await CityResolver(repo).resolve_country("Examplia", "ZZ")
        repo.set_country_code.assert_not_awaited()

    async def test_an_unknown_country_is_created_as_typed(self, repo):
        repo.create_country.return_value = _country(id=9, name="Newland")
        await CityResolver(repo).resolve_country("  Newland ", "nl")
        repo.create_country.assert_awaited_once_with("  Newland ", "NL")

    async def test_a_blank_code_counts_as_none(self, repo):
        repo.create_country.return_value = _country()
        await CityResolver(repo).resolve_country("Newland", "  ")
        repo.get_country_by_code.assert_not_awaited()
        repo.create_country.assert_awaited_once_with("Newland", None)


class TestResolveCity:
    async def test_an_existing_city_is_reused(self, repo):
        existing = _city()
        repo.get_city_in_country.return_value = existing
        assert await CityResolver(repo).resolve_city("alpha", _country()) is existing
        repo.create_city.assert_not_awaited()

    async def test_a_new_city_gets_the_leg_ends_with_its_name(self, repo):
        repo.create_city.return_value = _city(id=4, name="Beta")
        found = await CityResolver(repo).resolve_city("Beta", _country())
        assert found.id == 4
        repo.attach_leg_ends.assert_awaited_once_with(found)


class TestCityService:
    @pytest.fixture
    def service(self, repo):
        svc = CityService(AsyncMock())
        svc._repo = repo
        svc._resolver = CityResolver(repo)
        return svc

    async def test_create_with_an_unknown_country_id_is_not_found(self, service, repo):
        repo.get_country.return_value = None
        with pytest.raises(TravelNotFoundError):
            await service.create_city(CityCreate(name="Alpha", country_id=9))

    async def test_create_in_a_country_that_already_has_it_is_a_conflict(self, service, repo):
        repo.get_country.return_value = _country()
        repo.get_city_in_country.return_value = _city()
        with pytest.raises(TravelConflictError, match="already exists"):
            await service.create_city(CityCreate(name="alpha", country_id=1))
        repo.create_city.assert_not_awaited()

    async def test_create_with_a_country_name_resolves_it_and_commits(self, service, repo):
        repo.create_country.return_value = _country(id=2, name="Newland")
        repo.create_city.return_value = _city(id=5, name="Gamma", country=_country(id=2, name="Newland"))
        created = await service.create_city(CityCreate(name="Gamma", country="Newland", country_code="nl"))
        assert (created.id, created.country.name) == (5, "Newland")
        repo.commit.assert_awaited_once()

    async def test_the_conflict_message_does_not_touch_an_expired_country(self, service, repo):
        """After a rollback a loaded country is expired and reading it in async code raises: read the name first."""
        class _Expiring:
            id = 1
            expired = False

            @property
            def name(self):
                if self.expired:
                    raise RuntimeError("MissingGreenlet")
                return "Examplia"

        country = _Expiring()
        repo.get_country.return_value = country
        repo.get_city_in_country.return_value = _city()
        repo.rollback.side_effect = lambda: setattr(country, "expired", True)
        with pytest.raises(TravelConflictError, match="Examplia"):
            await service.create_city(CityCreate(name="Alpha", country_id=1))

    async def test_a_unique_index_violation_is_a_conflict(self, service, repo):
        from sqlalchemy.exc import IntegrityError

        repo.get_country.return_value = _country()
        repo.create_city.return_value = _city()
        repo.commit.side_effect = IntegrityError("x", {}, Exception())
        with pytest.raises(TravelConflictError):
            await service.create_city(CityCreate(name="Alpha", country_id=1))
        repo.rollback.assert_awaited()


class TestCitySchemas:
    def test_exactly_one_country_form(self):
        with pytest.raises(ValidationError):
            CityCreate(name="Alpha")
        with pytest.raises(ValidationError):
            CityCreate(name="Alpha", country_id=1, country="Examplia")

    def test_code_is_two_letters(self):
        with pytest.raises(ValidationError):
            CityCreate(name="Alpha", country="Examplia", country_code="EXA")


class TestCityRepositorySql:
    class _Session:
        def __init__(self):
            self.statements = []

        async def execute(self, stmt):
            self.statements.append(stmt)
            return SimpleNamespace(rowcount=1)

        async def scalars(self, stmt):
            self.statements.append(stmt)
            return SimpleNamespace(all=lambda: [])

    @staticmethod
    def _sql(stmt):
        return str(stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))

    async def test_attaching_leg_ends_only_touches_ends_without_a_city_matched_on_trimmed_lowercase_text(self):
        session = self._Session()
        attached = await CityRepository(session).attach_leg_ends(City(id=4, name="Porto", country_id=1))
        sql = [self._sql(s) for s in session.statements]
        assert attached == 2 and len(sql) == 2
        assert "origin_city_id IS NULL" in sql[0] and "lower(trim(travel.legs.origin)) = 'porto'" in sql[0]
        assert "destination_city_id IS NULL" in sql[1] and "SET destination_city_id=4" in sql[1].replace(" = ", "=")

    async def test_list_filters_by_country_and_name_substring(self):
        session = self._Session()
        await CityRepository(session).get_cities(CityFilters(country_id=2, q=" Lis "))
        sql = self._sql(session.statements[0])
        assert "country_id = 2" in sql and "lower(travel.cities.name) LIKE '%%lis%%'" in sql

    async def test_the_unique_lookup_asks_for_two_rows_at_most(self):
        session = self._Session()
        assert await CityRepository(session).find_unique_city_id("Porto") is None
        assert "LIMIT 2" in self._sql(session.statements[0])

    async def test_unique_lookup_with_one_row_returns_it_and_with_two_returns_none(self):
        class _Rows(self._Session):
            def __init__(self, ids):
                super().__init__()
                self._ids = ids

            async def scalars(self, stmt):
                return SimpleNamespace(all=lambda: self._ids)

        assert await CityRepository(_Rows([7])).find_unique_city_id("Porto") == 7
        assert await CityRepository(_Rows([7, 8])).find_unique_city_id("Porto") is None


class TestCityTables:
    def test_names_are_unique_case_insensitively_and_codes_when_set(self):
        indexes = {i.name: i for t in (Country.__table__, City.__table__) for i in t.indexes}
        assert indexes["uq_travel_countries_name"].unique and indexes["uq_travel_cities_name_country"].unique
        code_sql = str(indexes["uq_travel_countries_code"].dialect_options["postgresql"]["where"])
        assert "IS NOT NULL" in code_sql


class TestCityRoutes:
    @pytest.fixture
    def client(self):
        service = AsyncMock()
        app.dependency_overrides[deps.get_city_service] = lambda: service
        yield TestClient(app), service
        app.dependency_overrides.clear()

    def _read(self, id=1, name="Alpha"):
        return {"id": id, "name": name, "country": {"id": 1, "name": "Examplia", "code": None},
                "created_at": NOW.isoformat(), "updated_at": NOW.isoformat()}

    def test_countries(self, client):
        c, service = client
        service.get_countries.return_value = [{"id": 1, "name": "Examplia", "code": "EX"}]
        r = c.get("/travel/countries", headers=AUTH)
        assert r.status_code == 200 and r.json()[0]["code"] == "EX"

    def test_cities_filters(self, client):
        c, service = client
        service.get_cities.return_value = []
        c.get("/travel/cities?country_id=2&q=al", headers=AUTH)
        filters = service.get_cities.await_args.args[0]
        assert (filters.country_id, filters.q) == (2, "al")

    def test_create_returns_201(self, client):
        c, service = client
        service.create_city.return_value = self._read()
        r = c.post("/travel/cities", headers=AUTH, json={"name": "Alpha", "country": "Examplia", "country_code": "EX"})
        assert r.status_code == 201 and r.json()["country"]["name"] == "Examplia"

    def test_create_unknown_country_is_404(self, client):
        c, service = client
        service.create_city.side_effect = TravelNotFoundError("Country 9 not found")
        assert c.post("/travel/cities", headers=AUTH, json={"name": "Alpha", "country_id": 9}).status_code == 404

    def test_create_duplicate_is_409(self, client):
        c, service = client
        service.create_city.side_effect = TravelConflictError("Alpha already exists in Examplia")
        assert c.post("/travel/cities", headers=AUTH, json={"name": "Alpha", "country_id": 1}).status_code == 409

    def test_create_needs_exactly_one_country_form(self, client):
        c, _ = client
        assert c.post("/travel/cities", headers=AUTH, json={"name": "Alpha"}).status_code == 422
        both = {"name": "Alpha", "country_id": 1, "country": "Examplia"}
        assert c.post("/travel/cities", headers=AUTH, json=both).status_code == 422
