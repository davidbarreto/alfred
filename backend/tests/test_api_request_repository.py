from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.dialects.postgresql import asyncpg

from app.features.core.api_requests.repository import ApiRequestRepository


@pytest.fixture
def session():
    session = AsyncMock()
    session.add = MagicMock()
    result = MagicMock()
    result.all.return_value = []
    session.execute.return_value = result
    return session


def _compiled_sql(session) -> str:
    return str(session.execute.call_args.args[0].compile(dialect=asyncpg.dialect()))


class TestCreate:
    async def test_adds_row_and_commits(self, session):
        row = await ApiRequestRepository(session).create(
            client="web", method="GET", route="/tasks/{id}", status_code=200, duration_ms=7
        )

        session.add.assert_called_once_with(row)
        session.commit.assert_awaited_once()
        assert (row.client, row.route, row.status_code) == ("web", "/tasks/{id}", 200)


class TestUsageQueries:
    """Compiled against the real asyncpg dialect: a mocked session can't catch bind-param
    typing problems (e.g. an untyped literal inside CASE inside SUM)."""

    async def test_usage_by_client_groups_and_types_error_count(self, session):
        await ApiRequestRepository(session).usage_by_client(since=datetime.now(timezone.utc))

        sql = _compiled_sql(session)
        assert "GROUP BY core.api_requests.client" in sql
        assert "THEN $2::INTEGER ELSE $3::INTEGER" in sql

    async def test_usage_by_route_groups_by_caller_method_and_route(self, session):
        await ApiRequestRepository(session).usage_by_route(since=datetime.now(timezone.utc), limit=10)

        sql = _compiled_sql(session)
        assert "GROUP BY core.api_requests.client, core.api_requests.method, core.api_requests.route" in sql
        assert "LIMIT" in sql
