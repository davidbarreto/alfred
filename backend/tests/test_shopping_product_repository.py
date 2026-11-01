from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.organizer.shopping.errors import ShoppingProductNameTakenError
from app.features.organizer.shopping_products.repository import ShoppingProductRepository
from app.features.organizer.shopping_products.schemas import (
    ShoppingProductCreate,
    ShoppingProductFilters,
    ShoppingProductUpdate,
)


def _make_session() -> AsyncMock:
    session = AsyncMock(spec=AsyncSession)
    session.add = MagicMock()
    result = MagicMock()
    result.all.return_value = []
    result.scalars.return_value.first.return_value = MagicMock()
    session.execute.return_value = result
    return session


def _compiled(session: AsyncMock, call: int = -1) -> str:
    stmt = session.execute.call_args_list[call][0][0]
    return str(stmt.compile(compile_kwargs={"literal_binds": True}))


class TestGetByName:
    async def test_matches_case_insensitively_among_live_products(self):
        session = _make_session()

        await ShoppingProductRepository(session).get_by_name("  MILK ")

        compiled = _compiled(session)
        assert "lower(organizer.shopping_products.name) = 'milk'" in compiled
        assert "deleted_at IS NULL" in compiled


class TestList:
    async def test_counts_bought_entries_flags_pending_and_filters(self):
        session = _make_session()

        await ShoppingProductRepository(session).list(ShoppingProductFilters(q="mil", category_id=2, limit=10, offset=5))

        compiled = _compiled(session)
        assert "status = 'bought'" in compiled
        assert "status = 'pending'" in compiled
        assert "lower('%mil%')" in compiled
        assert "shopping_products.category_id = 2" in compiled
        assert "LIMIT 10 OFFSET 5" in compiled


class TestDelete:
    async def test_soft_deletes_and_releases_the_category(self):
        session = _make_session()

        await ShoppingProductRepository(session).delete(1)

        compiled = _compiled(session)
        assert "deleted_at=" in compiled
        assert "category_id=NULL" in compiled


class TestNameConflicts:
    async def test_create_maps_unique_violation_to_name_taken(self):
        session = _make_session()
        session.commit.side_effect = IntegrityError("stmt", {}, Exception("uq_shopping_products_name"))

        with pytest.raises(ShoppingProductNameTakenError):
            await ShoppingProductRepository(session).create(ShoppingProductCreate(name="Milk"))

        session.rollback.assert_awaited_once()

    async def test_rename_maps_unique_violation_to_name_taken(self):
        session = _make_session()
        session.commit.side_effect = IntegrityError("stmt", {}, Exception("uq_shopping_products_name"))

        with pytest.raises(ShoppingProductNameTakenError):
            await ShoppingProductRepository(session).update(1, ShoppingProductUpdate(name="Milk"))


class TestRepointItems:
    async def test_moves_every_entry_of_the_source_product(self):
        session = _make_session()

        await ShoppingProductRepository(session).repoint_items(1, 2)

        compiled = _compiled(session)
        assert "UPDATE organizer.shopping_items" in compiled
        assert "product_id=2" in compiled
        assert "product_id = 1" in compiled


class TestCountByCategory:
    async def test_counts_products_in_the_category(self):
        session = _make_session()
        session.execute.return_value.scalar_one.return_value = 3

        assert await ShoppingProductRepository(session).count_by_category(4) == 3
        assert "shopping_products.category_id = 4" in _compiled(session)
