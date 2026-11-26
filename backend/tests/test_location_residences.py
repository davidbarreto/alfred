"""Places lived (location.residences): period rules, the Home fix, routes and SQL (DB mocked; synthetic cities)."""
from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateIndex, CreateTable

from app import dependencies as deps
from app.features.location.cities.service import CityService
from app.features.location.errors import LocationConflictError, LocationNotFoundError, LocationValidationError
from app.features.location.residences.periods import lived_on, lived_summary, overlaps
from app.features.location.residences.repository import ResidenceRepository
from app.features.location.residences.schemas import ResidenceCreate, ResidenceUpdate
from app.features.location.residences.service import ResidenceService
from app.features.location.residences.tables import Residence
from app.main import app

AUTH = {"Authorization": "Bearer test-api-token"}
NOW = datetime(2026, 11, 1, tzinfo=timezone.utc)
TODAY = date(2026, 11, 26)
_COUNTRY = SimpleNamespace(id=1, name="Examplia", code="EX")


def _city(id=1, name="Alpha"):
    return SimpleNamespace(id=id, name=name, country_id=_COUNTRY.id, country=_COUNTRY)


def _row(id, city_id, from_date, to_date=None, born=False):
    return SimpleNamespace(
        id=id, city_id=city_id, city=_city(city_id, f"City {city_id}"), from_date=from_date, to_date=to_date, born=born,
        notes=None, created_at=NOW, updated_at=NOW,
    )


def _p(from_date, to_date=None, born=False):
    return SimpleNamespace(from_date=from_date, to_date=to_date, born=born)


class TestPeriods:
    def test_moving_day_belongs_to_the_next_row(self):
        assert not overlaps(_p(None, date(2005, 3, 1), True), _p(date(2005, 3, 1), date(2019, 3, 1)))
        assert overlaps(_p(date(2005, 3, 1), date(2019, 3, 1)), _p(date(2019, 2, 28)))
        assert overlaps(_p(date(2019, 3, 1)), _p(date(2026, 1, 1)))

    def test_lived_on(self):
        periods = [_p(None, date(2005, 3, 1), True), _p(date(2019, 3, 1))]
        assert lived_on(date(1990, 1, 1), periods) and lived_on(date(2026, 11, 26), periods)
        assert not lived_on(date(2005, 3, 1), periods) and not lived_on(date(2010, 6, 1), periods)

    def test_summary_living_since_the_start_of_an_unbroken_run(self):
        rows = [_p(date(2012, 1, 1), date(2015, 1, 1)), _p(date(2015, 1, 1), date(2019, 3, 1)), _p(date(2019, 3, 1))]
        assert lived_summary(rows) == {"born": False, "living": True, "lived_since": date(2012, 1, 1)}
        gap = [_p(date(2010, 1, 1), date(2011, 1, 1)), _p(date(2019, 3, 1))]
        assert lived_summary(gap)["lived_since"] == date(2019, 3, 1)

    def test_summary_since_birth_and_lived_until(self):
        assert lived_summary([_p(None, None, True)]) == {"born": True, "living": True, "lived_since": None}
        rows = [_p(None, date(2005, 3, 1), True), _p(date(2008, 1, 1), date(2010, 1, 1))]
        assert lived_summary(rows) == {"born": True, "lived_until": date(2010, 1, 1)}
        assert lived_summary([]) == {}


class TestSchemas:
    def test_only_the_birth_row_starts_at_birth_and_periods_end_after_they_start(self):
        assert ResidenceCreate(city_id=1, born=True).from_date is None
        with pytest.raises(ValidationError, match="from_date is required"):
            ResidenceCreate(city_id=1)
        with pytest.raises(ValidationError, match="after from_date"):
            ResidenceCreate(city_id=1, from_date=date(2020, 1, 1), to_date=date(2020, 1, 1))


@pytest.fixture
def service(monkeypatch):
    monkeypatch.setattr("app.features.location.residences.service.local_today", lambda: TODAY)
    svc = ResidenceService(AsyncMock())
    svc._repo, svc._cities, svc._places = AsyncMock(), AsyncMock(), AsyncMock()
    svc._repo.get_all.return_value = []
    svc._cities.get_city.return_value = _city()

    async def _refresh(row):
        row.id = row.id or 99
        row.city = _city(row.city_id)
        row.notes = getattr(row, "notes", None)
        row.created_at = row.updated_at = NOW
    svc._repo.refresh.side_effect = _refresh
    return svc


class TestService:
    async def test_create(self, service):
        found = await service.create_residence(ResidenceCreate(city_id=1, from_date=date(2019, 3, 1)))
        assert (found.city.name, found.current) == ("Alpha", True)
        service._repo.add.assert_awaited_once()
        service._repo.commit.assert_awaited_once()

    async def test_unknown_city_is_404(self, service):
        service._cities.get_city.return_value = None
        with pytest.raises(LocationNotFoundError):
            await service.create_residence(ResidenceCreate(city_id=9, from_date=date(2019, 3, 1)))

    @pytest.mark.parametrize("data, match", [
        (dict(born=True, to_date=date(2001, 1, 1)), "birthplace"),
        (dict(from_date=date(2026, 1, 1)), "still open"),
        (dict(from_date=date(2004, 1, 1), to_date=date(2006, 1, 1)), "overlaps City 1"),
    ])
    async def test_clashes_are_409(self, service, data, match):
        service._repo.get_all.return_value = [_row(1, 1, None, date(2005, 3, 1), born=True), _row(2, 2, date(2019, 3, 1))]
        with pytest.raises(LocationConflictError, match=match):
            await service.create_residence(ResidenceCreate(city_id=1, **data))
        service._repo.add.assert_not_awaited()

    async def test_update_checks_the_merged_row_and_ignores_itself(self, service):
        row = _row(2, 2, date(2019, 3, 1))
        service._repo.get.return_value = row
        service._repo.get_all.return_value = [_row(1, 1, None, date(2005, 3, 1), born=True), row]
        await service.update_residence(2, ResidenceUpdate(from_date=date(2005, 3, 1), notes="x"))
        assert (row.from_date, row.notes) == (date(2005, 3, 1), "x")
        with pytest.raises(LocationConflictError, match="overlaps"):
            await service.update_residence(2, ResidenceUpdate(from_date=date(2004, 1, 1)))
        with pytest.raises(LocationValidationError, match="from_date is required"):
            await service.update_residence(2, ResidenceUpdate(from_date=None))

    async def test_update_and_delete_unknown(self, service):
        service._repo.get.return_value = None
        assert await service.update_residence(9, ResidenceUpdate(notes="x")) is None
        assert await service.delete_residence(9) is False

    async def test_follow_home_closes_the_open_row_today_and_opens_one_in_homes_city(self, service):
        current = _row(2, 2, date(2019, 3, 1))
        service._repo.get_all.return_value = [current]
        service._places.get_home.return_value = SimpleNamespace(city_id=5)
        found = await service.follow_home()
        assert current.to_date == TODAY
        added = service._repo.add.await_args.args[0]
        assert (added.city_id, added.from_date, added.to_date) == (5, TODAY, None) and found.city.id == 5

    async def test_follow_home_moves_an_open_row_that_starts_today(self, service):
        current = _row(2, 2, TODAY)
        service._repo.get_all.return_value = [current]
        service._places.get_home.return_value = SimpleNamespace(city_id=5)
        await service.follow_home()
        assert (current.city_id, current.to_date) == (5, None)
        service._repo.add.assert_not_awaited()

    async def test_follow_home_refuses_without_home_or_when_it_matches(self, service):
        service._places.get_home.return_value = None
        with pytest.raises(LocationConflictError, match="no Home"):
            await service.follow_home()
        service._places.get_home.return_value = SimpleNamespace(city_id=2)
        service._repo.get_all.return_value = [_row(2, 2, date(2019, 3, 1))]
        with pytest.raises(LocationConflictError, match="already"):
            await service.follow_home()


class TestCityDelete:
    async def test_a_city_lived_in_is_not_deleted(self):
        hooks = AsyncMock()
        service = CityService(AsyncMock(), hooks)
        service._repo = AsyncMock()
        service._repo.get_city.return_value = _city()
        service._residences = AsyncMock(count_in_city=AsyncMock(return_value=2))
        with pytest.raises(LocationConflictError, match="Places lived"):
            await service.delete_city(1)
        service._repo.delete.assert_not_awaited()


class TestSql:
    def test_ddl_has_the_checks_and_partial_unique_indexes(self):
        dialect = postgresql.dialect()
        ddl = str(CreateTable(Residence.__table__).compile(dialect=dialect))
        assert "REFERENCES location.cities (id) ON DELETE RESTRICT" in ddl and "to_date > from_date" in ddl
        indexes = {i.name: str(CreateIndex(i).compile(dialect=dialect)) for i in Residence.__table__.indexes}
        assert indexes["uq_location_residences_born"].endswith("(born) WHERE born")
        assert indexes["uq_location_residences_open"].endswith("((to_date IS NULL)) WHERE to_date IS NULL")

    async def test_newest_first_birth_last(self):
        session = AsyncMock()
        session.scalars.return_value = MagicMock()
        await ResidenceRepository(session).get_page(5, 10)
        sql = str(session.scalars.await_args.args[0].compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))
        assert "ORDER BY location.residences.from_date DESC NULLS LAST" in sql and "LIMIT 5" in sql and "OFFSET 10" in sql


class TestRoutes:
    @pytest.fixture
    def client(self):
        service = AsyncMock()
        app.dependency_overrides[deps.get_residence_service] = lambda: service
        yield TestClient(app), service
        app.dependency_overrides.clear()

    def _read(self):
        return {"id": 1, "city": {"id": 1, "name": "Alpha", "country": {"id": 1, "name": "Examplia", "code": "EX"}},
                "from_date": "2019-03-01", "to_date": None, "born": False, "created_at": NOW, "updated_at": NOW}

    def test_crud(self, client):
        c, service = client
        service.list_residences.return_value = [self._read()]
        service.create_residence.return_value = self._read()
        response = c.get("/location/residences?limit=6", headers=AUTH)
        assert response.status_code == 200 and response.json()[0]["current"] is True
        assert service.list_residences.await_args.args[0].limit == 6
        assert c.post("/location/residences", json={"city_id": 1, "from_date": "2019-03-01"}, headers=AUTH).status_code == 201
        assert c.post("/location/residences", json={"city_id": 1}, headers=AUTH).status_code == 422
        service.get_residence.return_value = None
        service.update_residence.return_value = None
        service.delete_residence.return_value = False
        assert c.get("/location/residences/9", headers=AUTH).status_code == 404
        assert c.patch("/location/residences/9", json={"notes": "x"}, headers=AUTH).status_code == 404
        assert c.delete("/location/residences/9", headers=AUTH).status_code == 404
        service.delete_residence.return_value = True
        assert c.delete("/location/residences/1", headers=AUTH).status_code == 204

    def test_errors_map_to_status_codes(self, client):
        c, service = client
        service.create_residence.side_effect = LocationConflictError("The period overlaps X")
        response = c.post("/location/residences", json={"city_id": 1, "from_date": "2019-03-01"}, headers=AUTH)
        assert response.status_code == 409 and response.json()["detail"] == "The period overlaps X"
        service.update_residence.side_effect = LocationValidationError("from_date is required")
        assert c.patch("/location/residences/1", json={"from_date": None}, headers=AUTH).status_code == 422
        service.follow_home.side_effect = LocationNotFoundError("x")
        assert c.post("/location/residences/follow-home", headers=AUTH).status_code == 404

    def test_follow_home(self, client):
        c, service = client
        service.follow_home.return_value = self._read()
        assert c.post("/location/residences/follow-home", headers=AUTH).json()["city"]["name"] == "Alpha"

    def test_needs_auth(self, client):
        c, _ = client
        assert c.get("/location/residences").status_code in (401, 403)
