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


def _scalar_first(value):
    r = MagicMock()
    r.scalars.return_value.first.return_value = value
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


class TestCreateSession:
    async def test_defaults_grading_status_to_done(self):
        session = _make_session()
        await SessionRepository(session).create_session(
            track_id=1, chunk_id=10, session_type="shadowing", feeds_srs=False,
        )
        added = session.add.call_args.args[0]
        assert added.grading_status == "done"

    async def test_grading_status_can_be_overridden(self):
        session = _make_session()
        await SessionRepository(session).create_session(
            track_id=1, chunk_id=10, session_type="shadowing", feeds_srs=False, grading_status="pending",
        )
        added = session.add.call_args.args[0]
        assert added.grading_status == "pending"


class TestUpdateGradingResult:
    async def test_updates_fields_and_returns_row(self):
        session = _make_session()
        existing = MagicMock()
        session.execute.return_value = _scalar_first(existing)

        result = await SessionRepository(session).update_grading_result(
            session_id=1, quality_score=3.5, ai_feedback_json={"score": 85},
            transcript_or_notes="Nice", grading_status="done", feeds_srs=True,
        )

        assert result is existing
        assert existing.quality_score == 3.5
        assert existing.ai_feedback_json == {"score": 85}
        assert existing.transcript_or_notes == "Nice"
        assert existing.grading_status == "done"
        assert existing.feeds_srs is True
        session.commit.assert_awaited_once()

    async def test_returns_none_when_session_missing(self):
        session = _make_session()
        session.execute.return_value = _scalar_first(None)

        result = await SessionRepository(session).update_grading_result(
            session_id=999, quality_score=None, ai_feedback_json=None,
            transcript_or_notes=None, grading_status="failed", feeds_srs=False,
        )

        assert result is None
        session.commit.assert_not_awaited()
