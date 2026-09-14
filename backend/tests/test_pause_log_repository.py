from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.core.pause.repository import PauseLogRepository


def _make_session() -> AsyncMock:
    return AsyncMock(spec=AsyncSession)


def _scalar_all(values):
    result = MagicMock()
    result.scalars.return_value.all.return_value = values
    return result


class TestCreate:
    async def test_adds_commits_and_refreshes(self):
        session = _make_session()
        repo = PauseLogRepository(session)
        started_at = datetime.now(timezone.utc) - timedelta(hours=1)
        ended_at = datetime.now(timezone.utc)

        log = await repo.create(
            started_at=started_at,
            ended_at=ended_at,
            tasks_urgency_reset=3,
            tasks_deadline_shifted=1,
        )

        session.add.assert_called_once_with(log)
        session.commit.assert_awaited_once()
        session.refresh.assert_awaited_once_with(log)
        assert log.started_at == started_at
        assert log.ended_at == ended_at
        assert log.tasks_urgency_reset == 3
        assert log.tasks_deadline_shifted == 1


class TestList:
    async def test_orders_by_started_at_desc_and_applies_limit(self):
        session = _make_session()
        session.execute.return_value = _scalar_all([])
        repo = PauseLogRepository(session)

        await repo.list(limit=25)

        sql = str(session.execute.call_args[0][0].compile(compile_kwargs={"literal_binds": True}))
        assert "ORDER BY core.pause_log.started_at DESC" in sql
        assert "LIMIT 25" in sql

    async def test_returns_repo_results(self):
        session = _make_session()
        expected = [MagicMock(), MagicMock()]
        session.execute.return_value = _scalar_all(expected)
        repo = PauseLogRepository(session)

        result = await repo.list()

        assert result == expected
