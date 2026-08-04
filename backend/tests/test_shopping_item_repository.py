from unittest.mock import AsyncMock, MagicMock

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.organizer.shopping.repository import ShoppingRepository


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
    async def test_clears_category_id_so_the_category_can_later_be_deleted(self):
        session = _make_session()

        await ShoppingRepository(session).delete(1)

        compiled = _compiled(session)
        assert "category_id=NULL" in compiled
        assert "deleted_at=" in compiled


class TestGetPurchasesByCategory:
    async def test_groups_bought_items_by_category_excluding_null(self):
        session = _make_session()

        await ShoppingRepository(session).get_purchases_by_category()

        compiled = _compiled(session)
        assert "status = 'bought'" in compiled
        assert "category_id IS NOT NULL" in compiled
        assert "GROUP BY organizer.shopping_items.category_id" in compiled


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
