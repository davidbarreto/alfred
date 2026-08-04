from unittest.mock import AsyncMock, MagicMock

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.core.working_memory.repository import WorkingMemoryRepository
from app.features.core.working_memory.schemas import WorkingMemoryFilters


def _make_session() -> AsyncMock:
    return AsyncMock(spec=AsyncSession)


def _scalar_all(values):
    result = MagicMock()
    result.scalars.return_value.all.return_value = values
    return result


def _compiled(query) -> str:
    return str(query.compile(compile_kwargs={"literal_binds": True}))


class TestList:
    async def test_default_expired_all_has_no_expiry_where_clause(self):
        session = _make_session()
        session.execute.return_value = _scalar_all([])
        repo = WorkingMemoryRepository(session)

        await repo.list(WorkingMemoryFilters())

        sql = _compiled(session.execute.call_args[0][0])
        assert "WHERE" not in sql

    async def test_expired_active_excludes_expired_rows(self):
        session = _make_session()
        session.execute.return_value = _scalar_all([])
        repo = WorkingMemoryRepository(session)

        await repo.list(WorkingMemoryFilters(expired="active"))

        sql = _compiled(session.execute.call_args[0][0])
        assert "expires_at IS NULL" in sql
        assert "expires_at >" in sql

    async def test_expired_expired_only_returns_expired_rows(self):
        session = _make_session()
        session.execute.return_value = _scalar_all([])
        repo = WorkingMemoryRepository(session)

        await repo.list(WorkingMemoryFilters(expired="expired"))

        sql = _compiled(session.execute.call_args[0][0])
        assert "expires_at IS NOT NULL" in sql
        assert "expires_at <=" in sql

    async def test_key_contains_uses_ilike(self):
        session = _make_session()
        session.execute.return_value = _scalar_all([])
        repo = WorkingMemoryRepository(session)

        await repo.list(WorkingMemoryFilters(key_contains="trav"))

        sql = _compiled(session.execute.call_args[0][0])
        assert "lower(core.working_memory.key) like lower" in sql.lower()
        assert "%trav%" in sql

    async def test_key_prefix_matches_prefix(self):
        session = _make_session()
        session.execute.return_value = _scalar_all([])
        repo = WorkingMemoryRepository(session)

        await repo.list(WorkingMemoryFilters(key_prefix="language"))

        sql = _compiled(session.execute.call_args[0][0])
        assert "language:%" in sql

    async def test_orders_by_expiry_nulls_first_then_created_desc(self):
        session = _make_session()
        session.execute.return_value = _scalar_all([])
        repo = WorkingMemoryRepository(session)

        await repo.list(WorkingMemoryFilters())

        sql = _compiled(session.execute.call_args[0][0])
        order_clause = sql.split("ORDER BY")[1]
        assert "expires_at" in order_clause
        assert order_clause.index("expires_at") < order_clause.index("created_at")

    async def test_session_id_filter(self):
        session = _make_session()
        session.execute.return_value = _scalar_all([])
        repo = WorkingMemoryRepository(session)

        await repo.list(WorkingMemoryFilters(session_id=5))

        sql = _compiled(session.execute.call_args[0][0])
        assert "session_id = 5" in sql
