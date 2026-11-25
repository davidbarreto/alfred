from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.dialects import postgresql

from app.features.location.places.repository import PlaceRepository
from app.features.location.places.schemas import PlaceFilters
from app.features.organizer.everyday_places.repository import EverydayPlaceRepository
from app.features.organizer.everyday_places.schemas import EverydayPlaceFilters


def _sql(statement) -> str:
    return str(statement.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))


@pytest.fixture
def session():
    session = AsyncMock()
    session.add = MagicMock()
    scalars = MagicMock()
    scalars.all.return_value = []
    session.scalars.return_value = scalars
    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    result.all.return_value = []
    session.execute.return_value = result
    return session


class TestPlaceRepository:
    async def test_list_filters_and_home_first_order(self, session):
        await PlaceRepository(session).list(PlaceFilters(kind="pharmacy", city_id=15, country_id=1, active=True, q="Cor", limit=10))

        sql = _sql(session.scalars.call_args.args[0])
        assert "location.places.kind = 'pharmacy'" in sql
        assert "location.places.city_id = 15" in sql
        assert "location.cities.country_id = 1" in sql
        assert "location.places.active IS true" in sql
        assert "lower(location.places.name) LIKE '%%cor%%'" in sql and "lower(location.countries.name) LIKE '%%cor%%'" in sql
        assert "CASE WHEN (location.places.kind = 'home') THEN 0 ELSE 1 END, lower(location.places.name)" in sql
        assert "LIMIT 10" in sql

    async def test_name_lookup_is_case_insensitive_space_normalised_and_per_city(self, session):
        await PlaceRepository(session).get_by_name("  The   Market ", 15)

        sql = _sql(session.scalars.call_args.args[0])
        assert "lower(location.places.name) = 'the market'" in sql
        assert "location.places.city_id = 15" in sql

    async def test_name_lookup_across_cities(self, session):
        await PlaceRepository(session).get_by_name("Market")
        assert "city_id" not in _sql(session.scalars.call_args.args[0]).split("WHERE")[1]


class TestEverydayPlaceRepository:
    async def test_list_is_members_plus_home_with_filters(self, session):
        await EverydayPlaceRepository(session).list(
            EverydayPlaceFilters(kind="pharmacy", active=True, category_id=3, q="School", limit=10)
        )

        sql = _sql(session.scalars.call_args.args[0])
        assert "location.places.kind = 'home' OR location.places.id IN (SELECT organizer.everyday_places.place_id" in sql
        assert "organizer.places_shopping_categories.category_id = 3" in sql
        assert "lower(location.places.address) LIKE '%%school%%'" in sql
        assert "location.places.active IS true" in sql
        assert "LIMIT 10" in sql

    async def test_list_by_city(self, session):
        await EverydayPlaceRepository(session).list(EverydayPlaceFilters(city_id=7))

        assert "location.places.city_id = 7" in _sql(session.scalars.call_args.args[0])

    async def test_categories_by_name_lowercase(self, session):
        await EverydayPlaceRepository(session).get_categories_by_name(["Groceries"])

        assert "lower(organizer.shopping_categories.name) IN ('groceries')" in _sql(session.execute.call_args.args[0])

    async def test_empty_lookups_skip_the_query(self, session):
        repo = EverydayPlaceRepository(session)

        assert await repo.get_categories([]) == []
        assert await repo.get_categories_by_name([]) == []
        assert await repo.members([]) == set()
        assert await repo.categories_of([]) == {}
        session.execute.assert_not_called()
        session.scalars.assert_not_called()

    async def test_set_categories_replaces_the_rows(self, session):
        await EverydayPlaceRepository(session).set_categories(4, [1, 2])

        delete_sql = _sql(session.execute.await_args_list[0].args[0])
        assert "DELETE FROM organizer.places_shopping_categories WHERE organizer.places_shopping_categories.place_id = 4" in delete_sql
        assert session.execute.await_args_list[1].args[1] == [
            {"place_id": 4, "category_id": 1}, {"place_id": 4, "category_id": 2},
        ]

    async def test_adding_an_existing_member_changes_nothing(self, session):
        session.get.return_value = object()
        assert await EverydayPlaceRepository(session).add_member(4) is False
        session.add.assert_not_called()
