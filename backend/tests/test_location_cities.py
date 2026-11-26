from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError

from app import dependencies as deps
from app.features.location.cities.repository import CityRepository
from app.features.location.cities.schemas import CityCreate, CityFilters, CityUpdate
from app.features.location.cities.service import CityResolver, CityService
from app.features.location.cities.tables import City
from app.features.location.countries.schemas import CountryUpdate
from app.features.location.countries.service import CountryService
from app.features.location.countries.tables import Country
from app.features.location.errors import LocationConflictError, LocationNotFoundError
from app.main import app

AUTH = {"Authorization": "Bearer test-api-token"}
NOW = datetime(2026, 11, 1, tzinfo=timezone.utc)


def _country(id=1, name="Examplia", code=None):
    return SimpleNamespace(
        id=id, name=name, code=code, default_tag_names=None, cover_path=None, cover_credit=None, cover_source_url=None,
        created_at=NOW, updated_at=NOW,
    )


def _city(id=1, name="Alpha", country=None):
    country = country or _country()
    return SimpleNamespace(
        id=id, name=name, country_id=country.id, country=country, default_tag_names=None, latitude=None, longitude=None,
        cover_path=None, cover_credit=None, cover_source_url=None, created_at=NOW, updated_at=NOW,
    )


@pytest.fixture
def cities():
    r = AsyncMock()
    r.get_city_in_country.return_value = None
    return r


@pytest.fixture
def countries():
    r = AsyncMock()
    r.get_country_by_code.return_value = None
    r.get_country_by_name.return_value = None
    return r


@pytest.fixture
def hooks():
    h = AsyncMock()
    h.city_in_use.return_value = None
    h.before_delete.return_value = AsyncMock()
    return h


class TestResolveCountry:
    async def test_a_known_code_wins_over_a_different_name(self, cities, countries, hooks):
        countries.get_country_by_code.return_value = _country(name="United Kingdom", code="GB")
        found = await CityResolver(cities, countries, hooks).resolve_country("UK", "gb")
        assert found.name == "United Kingdom"
        countries.get_country_by_code.assert_awaited_once_with("GB")
        countries.create_country.assert_not_awaited()

    async def test_a_name_match_ignores_case_and_fills_a_missing_code(self, cities, countries, hooks):
        existing = _country(name="Examplia", code=None)
        countries.get_country_by_name.return_value = existing
        found = await CityResolver(cities, countries, hooks).resolve_country("examplia", "EX")
        assert found is existing
        countries.set_country_code.assert_awaited_once_with(existing, "EX")

    async def test_a_name_match_keeps_an_existing_code(self, cities, countries, hooks):
        countries.get_country_by_name.return_value = _country(code="EX")
        await CityResolver(cities, countries, hooks).resolve_country("Examplia", "ZZ")
        countries.set_country_code.assert_not_awaited()

    async def test_an_unknown_country_is_created_as_typed(self, cities, countries, hooks):
        countries.create_country.return_value = _country(id=9, name="Newland")
        await CityResolver(cities, countries, hooks).resolve_country("  Newland ", "nl")
        countries.create_country.assert_awaited_once_with("  Newland ", "NL")

    async def test_a_blank_code_counts_as_none(self, cities, countries, hooks):
        countries.create_country.return_value = _country()
        await CityResolver(cities, countries, hooks).resolve_country("Newland", "  ")
        countries.get_country_by_code.assert_not_awaited()
        countries.create_country.assert_awaited_once_with("Newland", None)


class TestResolveCity:
    async def test_an_existing_city_is_reused_and_the_hooks_are_not_told(self, cities, countries, hooks):
        existing = _city()
        cities.get_city_in_country.return_value = existing
        assert await CityResolver(cities, countries, hooks).resolve_city("alpha", _country()) is existing
        cities.create_city.assert_not_awaited()
        hooks.city_created.assert_not_awaited()

    async def test_a_new_city_is_passed_to_the_hooks(self, cities, countries, hooks):
        cities.create_city.return_value = _city(id=4, name="Beta")
        found = await CityResolver(cities, countries, hooks).resolve_city("Beta", _country())
        assert found.id == 4
        hooks.city_created.assert_awaited_once_with(found)


@pytest.fixture
def city_service(cities, countries, hooks):
    svc = CityService(AsyncMock(), hooks)
    svc._repo, svc._country_repo = cities, countries
    svc._residences = AsyncMock()
    svc._residences.count_in_city.return_value = 0
    svc._resolver = CityResolver(cities, countries, hooks)
    return svc


@pytest.fixture
def country_service(countries, hooks):
    svc = CountryService(AsyncMock(), hooks)
    svc._repo = countries
    return svc


class TestCreateCity:
    async def test_an_unknown_country_id_is_not_found(self, city_service, countries):
        countries.get_country.return_value = None
        with pytest.raises(LocationNotFoundError):
            await city_service.create_city(CityCreate(name="Alpha", country_id=9))

    async def test_a_country_that_already_has_it_is_a_conflict(self, city_service, cities, countries):
        countries.get_country.return_value = _country()
        cities.get_city_in_country.return_value = _city()
        with pytest.raises(LocationConflictError, match="already exists"):
            await city_service.create_city(CityCreate(name="alpha", country_id=1))
        cities.create_city.assert_not_awaited()

    async def test_a_country_name_is_resolved_and_the_city_committed(self, city_service, cities, countries):
        countries.create_country.return_value = _country(id=2, name="Newland")
        cities.create_city.return_value = _city(id=5, name="Gamma", country=_country(id=2, name="Newland"))
        created = await city_service.create_city(CityCreate(name="Gamma", country="Newland", country_code="nl"))
        assert (created.id, created.country.name) == (5, "Newland")
        cities.commit.assert_awaited_once()

    async def test_the_conflict_message_does_not_touch_an_expired_country(self, city_service, cities, countries):
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
        countries.get_country.return_value = country
        cities.get_city_in_country.return_value = _city()
        cities.rollback.side_effect = lambda: setattr(country, "expired", True)
        with pytest.raises(LocationConflictError, match="Examplia"):
            await city_service.create_city(CityCreate(name="Alpha", country_id=1))

    async def test_a_unique_index_violation_is_a_conflict(self, city_service, cities, countries):
        countries.get_country.return_value = _country()
        cities.create_city.return_value = _city()
        cities.commit.side_effect = IntegrityError("x", {}, Exception())
        with pytest.raises(LocationConflictError):
            await city_service.create_city(CityCreate(name="Alpha", country_id=1))
        cities.rollback.assert_awaited()


class TestEdits:
    async def test_rename_into_a_taken_name_is_a_conflict(self, city_service, cities):
        cities.get_city.return_value = _city()
        cities.get_city_in_country.return_value = _city(id=7, name="Beta")
        with pytest.raises(LocationConflictError):
            await city_service.update_city(1, CityUpdate(name="Beta"))
        cities.update.assert_not_awaited()

    async def test_a_case_change_of_its_own_name_is_fine(self, city_service, cities):
        cities.get_city.return_value = _city()
        cities.get_city_in_country.return_value = _city()
        await city_service.update_city(1, CityUpdate(name=" ALPHA "))
        assert cities.update.await_args.args[1] == {"name": "ALPHA"}

    async def test_moving_to_an_unknown_country_is_not_found(self, city_service, cities, countries):
        cities.get_city.return_value = _city()
        countries.get_country.return_value = None
        with pytest.raises(LocationNotFoundError):
            await city_service.update_city(1, CityUpdate(country_id=99))

    async def test_blank_default_tags_clear_them(self, city_service, cities):
        cities.get_city.return_value = _city()
        await city_service.update_city(1, CityUpdate(default_tag_names="  "))
        assert cities.update.await_args.args[1] == {"default_tag_names": None}

    async def test_a_code_of_another_country_is_a_conflict(self, country_service, countries):
        countries.get_country.return_value = _country(id=2)
        countries.get_other_country_by_code.return_value = SimpleNamespace(id=3)
        with pytest.raises(LocationConflictError):
            await country_service.update_country(2, CountryUpdate(code="ex"))

    async def test_a_null_code_clears_it(self, country_service, countries):
        countries.get_country.return_value = _country(id=2, code="EX")
        await country_service.update_country(2, CountryUpdate.model_validate({"code": None}))
        assert countries.update.await_args.args[1] == {"code": None}

    async def test_a_taken_country_name_is_a_conflict(self, country_service, countries):
        countries.get_country.return_value = _country(id=2)
        countries.get_country_by_name.return_value = _country(id=3, name="Otherland")
        with pytest.raises(LocationConflictError):
            await country_service.update_country(2, CountryUpdate(name="Otherland"))

    async def test_country_tags_are_saved_trimmed(self, country_service, countries):
        countries.get_country.return_value = _country(id=2)
        await country_service.update_country(2, CountryUpdate(default_tag_names=" spain, travel "))
        assert countries.update.await_args.args[1] == {"default_tag_names": "spain, travel"}

    def test_the_code_is_uppercased_and_must_be_letters(self):
        assert CountryUpdate(code="gb").code == "GB"
        with pytest.raises(ValidationError):
            CountryUpdate(code="1a")


class TestDeletes:
    async def test_a_city_the_hooks_say_is_in_use_is_a_conflict_with_their_reason(self, city_service, cities, hooks):
        cities.get_city.return_value = _city()
        hooks.city_in_use.return_value = "Alpha is used by 2 place(s)"
        with pytest.raises(LocationConflictError, match="2 place"):
            await city_service.delete_city(1)
        cities.delete.assert_not_awaited()
        hooks.before_delete.assert_not_awaited()

    async def test_an_unused_city_is_deleted_then_the_hooks_finish(self, city_service, cities, hooks):
        after = AsyncMock()
        hooks.before_delete.return_value = after
        cities.get_city.return_value = _city()
        assert await city_service.delete_city(1) is True
        hooks.before_delete.assert_awaited_once_with(city_id=1)
        cities.delete.assert_awaited_once()
        after.assert_awaited_once()

    async def test_a_foreign_key_violation_is_a_conflict_and_the_hooks_do_not_finish(self, city_service, cities, hooks):
        after = AsyncMock()
        hooks.before_delete.return_value = after
        cities.get_city.return_value = _city()
        cities.delete.side_effect = IntegrityError("x", {}, Exception())
        with pytest.raises(LocationConflictError, match="still in use"):
            await city_service.delete_city(1)
        after.assert_not_awaited()

    async def test_unknown_city_is_not_deleted(self, city_service, cities):
        cities.get_city.return_value = None
        assert await city_service.delete_city(1) is False

    async def test_a_country_with_cities_is_a_conflict(self, country_service, countries):
        countries.get_country.return_value = _country(id=2)
        countries.count_cities.return_value = 1
        with pytest.raises(LocationConflictError, match="1 city"):
            await country_service.delete_country(2)
        countries.delete.assert_not_awaited()

    async def test_an_empty_country_is_deleted_then_the_hooks_finish(self, country_service, countries, hooks):
        after = AsyncMock()
        hooks.before_delete.return_value = after
        countries.get_country.return_value = _country(id=2)
        countries.count_cities.return_value = 0
        assert await country_service.delete_country(2) is True
        hooks.before_delete.assert_awaited_once_with(country_id=2)
        countries.delete.assert_awaited_once()
        after.assert_awaited_once()


class TestCitySchemas:
    def test_exactly_one_country_form(self):
        with pytest.raises(ValidationError):
            CityCreate(name="Alpha")
        with pytest.raises(ValidationError):
            CityCreate(name="Alpha", country_id=1, country="Examplia")

    def test_code_is_two_letters(self):
        with pytest.raises(ValidationError):
            CityCreate(name="Alpha", country="Examplia", country_code="EXA")


class TestRepositorySql:
    class _Session:
        def __init__(self):
            self.statements = []

        async def scalars(self, stmt):
            self.statements.append(stmt)
            return SimpleNamespace(all=lambda: [])

        async def scalar(self, stmt):
            self.statements.append(stmt)
            return 0

    @staticmethod
    def _sql(stmt):
        return str(stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))

    async def test_list_filters_by_country_and_name_substring(self):
        session = self._Session()
        await CityRepository(session).get_cities(CityFilters(country_id=2, q=" Lis "))
        sql = self._sql(session.statements[0])
        assert "country_id = 2" in sql and "lower(location.cities.name) LIKE '%%lis%%'" in sql

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

    async def test_a_country_counts_its_cities(self):
        from app.features.location.countries.repository import CountryRepository

        session = self._Session()
        assert await CountryRepository(session).count_cities(2) == 0
        sql = self._sql(session.statements[0])
        assert "FROM location.cities" in sql and "location.cities.country_id = 2" in sql


class TestTables:
    def test_both_live_in_the_location_schema(self):
        assert (Country.__table__.schema, City.__table__.schema) == ("location", "location")
        assert {fk.target_fullname for fk in City.__table__.foreign_keys} == {"location.countries.id"}

    def test_names_are_unique_case_insensitively_and_codes_when_set(self):
        indexes = {i.name: i for t in (Country.__table__, City.__table__) for i in t.indexes}
        assert indexes["uq_location_countries_name"].unique and indexes["uq_location_cities_name_country"].unique
        code_sql = str(indexes["uq_location_countries_code"].dialect_options["postgresql"]["where"])
        assert "IS NOT NULL" in code_sql


class TestRoutes:
    @pytest.fixture
    def client(self):
        cities, countries = AsyncMock(), AsyncMock()
        app.dependency_overrides[deps.get_city_service] = lambda: cities
        app.dependency_overrides[deps.get_country_service] = lambda: countries
        yield TestClient(app), cities, countries
        app.dependency_overrides.clear()

    def _read(self, id=1, name="Alpha"):
        return {"id": id, "name": name, "country": {"id": 1, "name": "Examplia", "code": None},
                "created_at": NOW.isoformat(), "updated_at": NOW.isoformat()}

    def _country_read(self):
        return {"id": 1, "name": "Examplia", "code": "EX", "created_at": NOW.isoformat(), "updated_at": NOW.isoformat()}

    def test_countries(self, client):
        c, _, countries = client
        countries.get_countries.return_value = [self._country_read()]
        r = c.get("/location/countries", headers=AUTH)
        assert r.status_code == 200 and r.json()[0]["code"] == "EX"
        assert r.json()[0]["has_cover"] is False and r.json()[0]["photos_url"].endswith("/search/Examplia")

    def test_one_country_and_its_404(self, client):
        c, _, countries = client
        countries.get_country.return_value = self._country_read()
        assert c.get("/location/countries/1", headers=AUTH).json()["code"] == "EX"
        countries.get_country.return_value = None
        assert c.get("/location/countries/9", headers=AUTH).status_code == 404

    def test_cities_filters(self, client):
        c, cities, _ = client
        cities.get_cities.return_value = []
        c.get("/location/cities?country_id=2&q=al", headers=AUTH)
        filters = cities.get_cities.await_args.args[0]
        assert (filters.country_id, filters.q) == (2, "al")

    def test_one_city_and_its_404(self, client):
        c, cities, _ = client
        cities.get_city.return_value = self._read()
        assert c.get("/location/cities/1", headers=AUTH).json()["name"] == "Alpha"
        cities.get_city.return_value = None
        assert c.get("/location/cities/9", headers=AUTH).status_code == 404

    def test_create_returns_201(self, client):
        c, cities, _ = client
        cities.create_city.return_value = self._read()
        r = c.post("/location/cities", headers=AUTH, json={"name": "Alpha", "country": "Examplia", "country_code": "EX"})
        assert r.status_code == 201 and r.json()["country"]["name"] == "Examplia"

    def test_create_unknown_country_is_404(self, client):
        c, cities, _ = client
        cities.create_city.side_effect = LocationNotFoundError("Country 9 not found")
        assert c.post("/location/cities", headers=AUTH, json={"name": "Alpha", "country_id": 9}).status_code == 404

    def test_create_duplicate_is_409(self, client):
        c, cities, _ = client
        cities.create_city.side_effect = LocationConflictError("Alpha already exists in Examplia")
        assert c.post("/location/cities", headers=AUTH, json={"name": "Alpha", "country_id": 1}).status_code == 409

    def test_create_needs_exactly_one_country_form(self, client):
        c, _, _ = client
        assert c.post("/location/cities", headers=AUTH, json={"name": "Alpha"}).status_code == 422
        both = {"name": "Alpha", "country_id": 1, "country": "Examplia"}
        assert c.post("/location/cities", headers=AUTH, json=both).status_code == 422

    def test_delete_conflict_and_missing_and_ok(self, client):
        c, cities, countries = client
        cities.delete_city.side_effect = LocationConflictError("in use")
        assert c.delete("/location/cities/1", headers=AUTH).status_code == 409
        cities.delete_city.side_effect = None
        cities.delete_city.return_value = False
        assert c.delete("/location/cities/1", headers=AUTH).status_code == 404
        cities.delete_city.return_value = True
        assert c.delete("/location/cities/1", headers=AUTH).status_code == 204
        countries.delete_country.return_value = True
        assert c.delete("/location/countries/1", headers=AUTH).status_code == 204
        countries.delete_country.side_effect = LocationConflictError("has cities")
        assert c.delete("/location/countries/1", headers=AUTH).status_code == 409

    def test_patch_conflicts_and_unknown(self, client):
        c, cities, countries = client
        cities.update_city.side_effect = LocationConflictError("exists")
        assert c.patch("/location/cities/1", headers=AUTH, json={"name": "B"}).status_code == 409
        cities.update_city.side_effect = LocationNotFoundError("Country 9 not found")
        assert c.patch("/location/cities/1", headers=AUTH, json={"country_id": 9}).status_code == 404
        countries.update_country.side_effect = LocationConflictError("exists")
        assert c.patch("/location/countries/1", headers=AUTH, json={"code": "EX"}).status_code == 409
        assert c.patch("/location/countries/1", headers=AUTH, json={"code": "1"}).status_code == 422

    def test_the_travel_paths_no_longer_edit(self, client):
        c, _, _ = client
        assert c.post("/travel/cities", headers=AUTH, json={"name": "Alpha", "country_id": 1}).status_code in (404, 405)
        assert c.patch("/travel/countries/1", headers=AUTH, json={"name": "X"}).status_code in (404, 405)


class TestMigration:
    @staticmethod
    def _run(direction: str, monkeypatch) -> list[str]:
        import importlib.util
        from pathlib import Path

        path = Path(__file__).parents[1] / "alembic" / "versions" / "100_location_schema.py"
        spec = importlib.util.spec_from_file_location("migration_100", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        statements: list[str] = []
        monkeypatch.setattr(module.op, "execute", statements.append, raising=False)
        monkeypatch.setenv("DATABASE_URL", "postgresql://alfred_app:x@db/alfred")
        getattr(module, direction)()
        return statements

    def test_upgrade_moves_both_tables_and_renames_their_indexes_to_the_orm_names(self, monkeypatch):
        sql = self._run("upgrade", monkeypatch)
        assert sql[0] == "CREATE SCHEMA IF NOT EXISTS location"
        assert sql[1:3] == ["ALTER TABLE travel.countries SET SCHEMA location", "ALTER TABLE travel.cities SET SCHEMA location"]
        renamed = {s.split(" RENAME TO ")[1] for s in sql if " RENAME TO " in s}
        orm = {i.name for t in (Country.__table__, City.__table__) for i in t.indexes}
        assert renamed == orm
        assert "ALTER INDEX location.uq_travel_cities_name_country RENAME TO uq_location_cities_name_country" in sql
        assert "GRANT USAGE ON SCHEMA location TO alfred_app" in sql

    def test_downgrade_moves_them_back_and_restores_the_names(self, monkeypatch):
        sql = self._run("downgrade", monkeypatch)
        assert sql[:2] == ["ALTER TABLE location.countries SET SCHEMA travel", "ALTER TABLE location.cities SET SCHEMA travel"]
        assert "ALTER INDEX travel.ix_location_countries_id RENAME TO ix_travel_countries_id" in sql
        assert sql[-1] == "DROP SCHEMA IF EXISTS location"
