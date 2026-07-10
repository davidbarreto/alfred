from unittest.mock import AsyncMock, MagicMock

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.language.sessions.repository import SessionRepository
from app.features.language.sessions.schemas import SessionFilters


def _make_session() -> AsyncMock:
    return AsyncMock(spec=AsyncSession)


def _scalar_all(values):
    r = MagicMock()
    r.scalars.return_value.all.return_value = values
    return r


def _executed_sql(session: AsyncMock) -> str:
    query = session.execute.call_args.args[0]
    return str(query)


class TestGetSessions:
    async def test_no_filters_returns_all(self):
        session = _make_session()
        rows = [MagicMock(), MagicMock()]
        session.execute.return_value = _scalar_all(rows)
        result = await SessionRepository(session).get_sessions(SessionFilters())
        assert result == rows
        sql = _executed_sql(session)
        assert "JOIN" not in sql
        assert "cefr_level" not in sql

    async def test_track_and_type_filters(self):
        session = _make_session()
        session.execute.return_value = _scalar_all([])
        filters = SessionFilters(track_id=1, session_type="srs_review")
        await SessionRepository(session).get_sessions(filters)
        sql = _executed_sql(session)
        assert "track_id" in sql
        assert "session_type" in sql

    async def test_task_type_filter(self):
        session = _make_session()
        session.execute.return_value = _scalar_all([])
        filters = SessionFilters(task_type="journal")
        await SessionRepository(session).get_sessions(filters)
        assert "task_type" in _executed_sql(session)

    async def test_cefr_filter_joins_chunks(self):
        session = _make_session()
        session.execute.return_value = _scalar_all([])
        filters = SessionFilters(cefr_level="B1")
        await SessionRepository(session).get_sessions(filters)
        sql = _executed_sql(session)
        assert "JOIN" in sql
        assert "chunks" in sql
        assert "cefr_level" in sql

    async def test_orders_newest_first_with_pagination(self):
        session = _make_session()
        session.execute.return_value = _scalar_all([])
        filters = SessionFilters(limit=10, offset=20)
        await SessionRepository(session).get_sessions(filters)
        sql = _executed_sql(session)
        assert "ORDER BY" in sql
        assert "created_at DESC" in sql
        assert "LIMIT" in sql
        assert "OFFSET" in sql
