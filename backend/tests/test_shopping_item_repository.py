from unittest.mock import AsyncMock

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.organizer.shopping.repository import ShoppingRepository


def _make_session() -> AsyncMock:
    return AsyncMock(spec=AsyncSession)


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
