from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.organizer.shopping.errors import ShoppingItemAlreadyPendingError
from app.features.organizer.shopping.repository import ShoppingRepository
from app.features.organizer.shopping.schemas import FrequentItemFilters, ShoppingItemCreate, ShoppingItemFilters


def _make_session() -> AsyncMock:
    session = AsyncMock(spec=AsyncSession)
    result = MagicMock()
    result.all.return_value = []
    session.execute.return_value = result
    return session


def _compiled(session: AsyncMock) -> str:
    stmt = session.execute.call_args[0][0]
    return str(stmt.compile(compile_kwargs={"literal_binds": True}))


class TestDelete:
    async def test_soft_deletes_the_entry_and_leaves_its_product_alone(self):
        session = _make_session()

        await ShoppingRepository(session).delete(1)

        compiled = _compiled(session)
        assert "deleted_at=" in compiled
        assert "category_id" not in compiled
        assert "shopping_products" not in compiled


class TestListQueries:
    async def test_joins_the_product_and_filters_category_through_it(self):
        session = _make_session()

        await ShoppingRepository(session).list(ShoppingItemFilters(status="pending", category_id=3))

        compiled = _compiled(session)
        assert "JOIN organizer.shopping_products" in compiled
        assert "organizer.shopping_products.category_id = 3" in compiled
        assert "shopping_items.deleted_at IS NULL" in compiled


class TestGetFrequent:
    async def test_excludes_products_with_a_pending_entry_before_applying_the_limit(self):
        session = _make_session()

        await ShoppingRepository(session).get_frequent(FrequentItemFilters(limit=5))

        compiled = _compiled(session)
        assert "shopping_products.id NOT IN" in compiled
        assert "status = 'pending'" in compiled
        assert "GROUP BY organizer.shopping_products.id" in compiled
        assert "shopping_products.deleted_at IS NULL" in compiled
        assert compiled.index("NOT IN") < compiled.index("LIMIT 5")

    async def test_default_limit_is_five(self):
        assert FrequentItemFilters().limit == 5


class TestPendingConflict:
    @staticmethod
    def _session_failing_commit(message: str) -> AsyncMock:
        session = _make_session()
        session.commit.side_effect = IntegrityError("stmt", {}, Exception(message))
        return session

    async def test_create_turns_the_unique_index_violation_into_already_pending(self):
        session = self._session_failing_commit('duplicate key value violates unique constraint "uq_shopping_items_pending_product"')

        with pytest.raises(ShoppingItemAlreadyPendingError):
            await ShoppingRepository(session).create(1, ShoppingItemCreate(name="Milk"))

        session.rollback.assert_awaited_once()

    async def test_other_integrity_errors_are_not_swallowed(self):
        session = self._session_failing_commit("violates foreign key constraint")

        with pytest.raises(IntegrityError):
            await ShoppingRepository(session).create(1, ShoppingItemCreate(name="Milk"))


class TestGetPurchasesByCategory:
    async def test_groups_bought_items_by_category_excluding_null(self):
        session = _make_session()

        await ShoppingRepository(session).get_purchases_by_category()

        compiled = _compiled(session)
        assert "status = 'bought'" in compiled
        assert "shopping_products.category_id IS NOT NULL" in compiled
        assert "GROUP BY organizer.shopping_products.category_id" in compiled


class TestGetPurchasesByMonth:
    async def test_buckets_by_month_within_window(self):
        session = _make_session()

        await ShoppingRepository(session).get_purchases_by_month(months=3)

        compiled = _compiled(session)
        assert "status = 'bought'" in compiled
        assert "last_bought_at IS NOT NULL" in compiled
        assert "last_bought_at >=" in compiled
        assert "to_char(organizer.shopping_items.last_bought_at" in compiled


class TestGetPriorityCounts:
    async def test_groups_all_non_deleted_items_by_priority(self):
        session = _make_session()

        await ShoppingRepository(session).get_priority_counts()

        compiled = _compiled(session)
        assert "deleted_at IS NULL" in compiled
        assert "GROUP BY organizer.shopping_items.priority" in compiled
        assert "status = 'bought'" not in compiled


class TestGetPurchasesByStore:
    async def test_groups_bought_items_by_store_excluding_null(self):
        session = _make_session()

        await ShoppingRepository(session).get_purchases_by_store()

        compiled = _compiled(session)
        assert "status = 'bought'" in compiled
        assert "store IS NOT NULL" in compiled
        assert "GROUP BY organizer.shopping_items.store" in compiled
