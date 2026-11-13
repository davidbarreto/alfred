"""Compile the trip/place queries and the table DDL against the real PostgreSQL dialect.

Mocked-repository tests cannot catch SQL that only fails at compile or bind time."""
from datetime import date

from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from app.db.base import Base
from app.features.travel.places.repository import PlaceRepository
from app.features.travel.places.schemas import PlaceFilters
from app.features.travel.visits.repository import VisitRepository
from app.features.travel.visits.schemas import VisitFilters
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


class TestPlaceLocationQuery:
    async def test_selects_city_and_country_of_places(self):
        session = _ExecSession()
        try:
            await PlaceRepository(session).get_locations()
        except _Stop:
            pass
        sql = _literal(session.statement)
        assert "travel.places.city" in sql and "travel.places.country" in sql


class TestTripLocationQueries:
    async def _sql(self, call):
        session = _ExecSession()
        try:
            await call(TripRepository(session))
        except _Stop:
            pass
        return _literal(session.statement)

    async def test_trip_locations_union_stays_and_visits(self):
        sql = await self._sql(lambda repo: repo.get_trip_locations([1, 2]))
        assert "UNION" in sql and "travel.stays" in sql and "travel.visits" in sql

    async def test_locations_only_use_places_of_a_trip(self):
        sql = await self._sql(lambda repo: repo.get_locations())
        assert "UNION" in sql and "trip_id IS NOT NULL" in sql


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


class _ExecSession(_CaptureSession):
    async def execute(self, stmt):
        self.statement = stmt
        raise _Stop


def _literal(stmt) -> str:
    return str(stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))


class TestPlaceQuery:
    async def _sql(self, **kw):
        session = _CaptureSession()
        try:
            await PlaceRepository(session).get_places(PlaceFilters(**kw))
        except _Stop:
            pass
        return _literal(session.statement)

    async def test_tag_filter_requires_every_tag(self):
        sql = await self._sql(tag=["a", "b"])
        assert sql.count("travel.places_tags") >= 2

    async def test_min_grade_averages_visits_and_stays(self):
        sql = await self._sql(min_grade=4)
        assert "UNION ALL" in sql and "avg(" in sql.lower() and "travel.visits" in sql and "travel.stays" in sql

    async def test_no_trip_and_status_compile(self):
        sql = await self._sql(no_trip=True, status="visited", kind="cafe", city="Lisbon", country="Portugal", q="x")
        assert "trip_id IS NOT NULL" in sql and "'visited'" in sql

    async def test_grades_query_compiles(self):
        session = _ExecSession()
        try:
            await PlaceRepository(session).get_grades([1, 2])
        except _Stop:
            pass
        assert "GROUP BY" in _literal(session.statement)


class TestVisitQuery:
    async def test_orders_undated_and_untimed_last(self):
        session = _CaptureSession()
        try:
            await VisitRepository(session).get_visits(
                VisitFilters(trip_id=1, place_id=2, status="planned", date_from=date(2026, 1, 1), date_to=date(2026, 12, 31))
            )
        except _Stop:
            pass
        sql = _literal(session.statement)
        assert "NULLS LAST" in sql and sql.index("visit_date") < sql.index("visit_time", sql.index("ORDER BY"))

    async def test_no_trip_filter(self):
        session = _CaptureSession()
        try:
            await VisitRepository(session).get_visits(VisitFilters(no_trip=True))
        except _Stop:
            pass
        assert "trip_id IS NULL" in _literal(session.statement)
