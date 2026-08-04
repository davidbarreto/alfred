from unittest.mock import AsyncMock, MagicMock

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.core.memories.repository import MemoryRepository
from app.features.core.memories.schemas import MemoryFilters


def _make_session() -> AsyncMock:
    return AsyncMock(spec=AsyncSession)


def _scalar_all(values):
    result = MagicMock()
    result.scalars.return_value.all.return_value = values
    return result


def _compiled(query) -> str:
    return str(query.compile(compile_kwargs={"literal_binds": True}))


class TestList:
    async def test_q_filters_content_with_ilike(self):
        session = _make_session()
        session.execute.return_value = _scalar_all([])
        repo = MemoryRepository(session)

        await repo.list(MemoryFilters(q="Paris"))

        sql = _compiled(session.execute.call_args[0][0])
        assert "lower(core.memories.content) like lower" in sql.lower()
        assert "%Paris%" in sql

    async def test_no_q_omits_content_filter(self):
        session = _make_session()
        session.execute.return_value = _scalar_all([])
        repo = MemoryRepository(session)

        await repo.list(MemoryFilters())

        sql = _compiled(session.execute.call_args[0][0])
        assert "content ILIKE" not in sql

    async def test_default_sort_is_created_at(self):
        session = _make_session()
        session.execute.return_value = _scalar_all([])
        repo = MemoryRepository(session)

        await repo.list(MemoryFilters())

        sql = _compiled(session.execute.call_args[0][0])
        order_clause = sql.split("ORDER BY")[1]
        assert "importance" not in order_clause
        assert "created_at" in order_clause

    async def test_sort_importance_orders_by_importance_desc_then_created_at(self):
        session = _make_session()
        session.execute.return_value = _scalar_all([])
        repo = MemoryRepository(session)

        await repo.list(MemoryFilters(sort="importance"))

        sql = _compiled(session.execute.call_args[0][0])
        order_clause = sql.split("ORDER BY")[1]
        assert "importance DESC" in order_clause
        assert order_clause.index("importance") < order_clause.index("created_at")

    async def test_category_and_active_filters(self):
        session = _make_session()
        session.execute.return_value = _scalar_all([])
        repo = MemoryRepository(session)

        await repo.list(MemoryFilters(category="fact", active=True))

        sql = _compiled(session.execute.call_args[0][0])
        assert "category = 'fact'" in sql
        assert "active = true" in sql.lower()
