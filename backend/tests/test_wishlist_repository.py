from unittest.mock import AsyncMock, MagicMock

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.organizer.shopping.repository import WishlistRepository


def _make_session() -> AsyncMock:
    return AsyncMock(spec=AsyncSession)


def _scalar_first(value):
    result = MagicMock()
    result.scalars.return_value.first.return_value = value
    return result


class TestGet:
    async def test_excludes_promoted_and_deleted_items(self):
        session = _make_session()
        session.execute.return_value = _scalar_first(None)

        await WishlistRepository(session).get(1)

        query = str(session.execute.call_args[0][0])
        assert "promoted_at IS NULL" in query
        assert "deleted_at IS NULL" in query

    async def test_returns_none_when_not_found(self):
        session = _make_session()
        session.execute.return_value = _scalar_first(None)

        assert await WishlistRepository(session).get(999) is None


class TestDelete:
    async def test_clears_category_id_so_the_category_can_later_be_deleted(self):
        session = _make_session()

        await WishlistRepository(session).delete(1)

        stmt = session.execute.call_args[0][0]
        compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
        assert "category_id=NULL" in compiled
        assert "deleted_at=" in compiled
