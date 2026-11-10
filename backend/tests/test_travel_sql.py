"""Compile the trip/place queries and the table DDL against the real PostgreSQL dialect.

Mocked-repository tests cannot catch SQL that only fails at compile or bind time."""
from datetime import date

from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from app.db.base import Base
from app.features.travel.places.schemas import PlaceFilters
from app.features.travel.trips.repository import TripRepository
from app.features.travel.trips.schemas import TripFilters
from app.main import app  # noqa: F401  (registers every model)


class _CaptureSession:
    def __init__(self):
        self.statement = None

    async def scalars(self, stmt):
        self.statement = stmt
        raise _Stop


class _Stop(Exception):
    pass


class TestTripQuery:
    async def _sql(self, **kw):
        session = _CaptureSession()
        repo = TripRepository(session)
        try:
            await repo.get_trips(TripFilters(**kw), date(2026, 6, 5))
        except _Stop:
            pass
        return str(session.statement.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))

    async def test_default_hides_past_trips(self):
        sql = await self._sql()
        assert "travel.trips.end_date <" in sql and "NOT" in sql.upper()

    async def test_tag_filter_requires_every_tag(self):
        sql = await self._sql(status="all", tag=["family", "work"])
        assert sql.count("travel.trips_tags") >= 2

    async def test_all_filters_compile(self):
        sql = await self._sql(
            status="past", q="Ex", date_from=date(2026, 1, 1), date_to=date(2026, 12, 31), tag=["a"], limit=5, offset=5
        )
        assert "ORDER BY" in sql and "LIMIT 5" in sql


def test_travel_ddl_compiles_for_postgres():
    tables = [t for t in Base.metadata.sorted_tables if t.schema == "travel"]
    assert {t.name for t in tables} >= {"trips", "legs", "stays", "places", "tags", "trips_tags"}
    for table in tables:
        CreateTable(table).compile(dialect=postgresql.dialect())


def test_place_filters_have_plain_defaults():
    filters = PlaceFilters()
    assert (filters.limit, filters.offset, filters.q) == (50, 0, None)


def test_trip_filters_have_plain_defaults():
    filters = TripFilters()
    assert (filters.status, filters.limit, filters.offset) == ("current", 50, 0)
