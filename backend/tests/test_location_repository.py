from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError

from app.features.organizer.locations.errors import LocationConflictError
from app.features.organizer.locations.repository import LocationRepository
from app.features.organizer.locations.schemas import LocationFilters


def _sql(statement) -> str:
    return str(statement.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))


@pytest.fixture
def session():
    session = AsyncMock()
    session.add = MagicMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    result.scalars.return_value.first.return_value = None
    session.execute.return_value = result
    return session


class TestList:
    async def test_filters_and_home_first_order(self, session):
        await LocationRepository(session).list(LocationFilters(kind="pharmacy", active=True, category_id=3, limit=10))

        sql = _sql(session.execute.call_args.args[0])
        assert "organizer.locations.kind = 'pharmacy'" in sql
        assert "organizer.locations.active IS true" in sql
        assert "organizer.locations_shopping_categories" in sql and "organizer.shopping_categories.id = 3" in sql
        assert "CASE WHEN (organizer.locations.kind = 'home') THEN 0 ELSE 1 END, lower(organizer.locations.name)" in sql
        assert "LIMIT 10" in sql

    async def test_no_filters(self, session):
        await LocationRepository(session).list(LocationFilters())

        sql = _sql(session.execute.call_args.args[0])
        assert "WHERE" not in sql


class TestLookups:
    async def test_name_lookup_is_case_insensitive_and_space_normalised(self, session):
        await LocationRepository(session).get_by_name("  The   Market ")

        assert "lower(organizer.locations.name) = 'the market'" in _sql(session.execute.call_args.args[0])

    async def test_categories_by_name_lowercase(self, session):
        await LocationRepository(session).get_categories_by_name(["Groceries"])

        assert "lower(organizer.shopping_categories.name) IN ('groceries')" in _sql(session.execute.call_args.args[0])

    async def test_empty_lookups_skip_the_query(self, session):
        repo = LocationRepository(session)

        assert await repo.get_categories([]) == []
        assert await repo.get_categories_by_name([]) == []
        session.execute.assert_not_called()


class TestCreate:
    async def test_integrity_error_becomes_a_conflict(self, session):
        session.commit.side_effect = IntegrityError("insert", {}, Exception("duplicate key"))

        with pytest.raises(LocationConflictError):
            await LocationRepository(session).create({"name": "Home", "kind": "home"}, [])
        session.rollback.assert_awaited_once()
