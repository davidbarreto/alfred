from datetime import timedelta
from unittest.mock import AsyncMock

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.language.chunks.repository import ChunkRepository


def _make_session() -> AsyncMock:
    return AsyncMock(spec=AsyncSession)


def _executed_sql(session: AsyncMock) -> str:
    query = session.execute.call_args.args[0]
    return str(query)


class TestShiftDueDates:
    async def test_updates_due_at_and_prod_due_at_for_track(self):
        session = _make_session()
        await ChunkRepository(session).shift_due_dates(1, timedelta(days=3))
        sql = _executed_sql(session)
        assert "due_at" in sql
        assert "prod_due_at" in sql
        assert "track_id" in sql
        assert "status" in sql
        session.commit.assert_awaited_once()
