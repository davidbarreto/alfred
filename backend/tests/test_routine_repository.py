from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.organizer.routines.repository import RoutineRepository
from app.features.organizer.routines.schemas import RoutineStepBase
import app.features.organizer.notes.tables  # noqa: F401 — registers Note with SQLAlchemy mapper


def _sql(statement) -> str:
    return str(statement.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))


def _session(rows=None, first=None, scalar=None):
    session = AsyncMock(spec=AsyncSession)
    result = MagicMock()
    result.scalars.return_value.all.return_value = rows or []
    result.scalars.return_value.first.return_value = first
    result.all.return_value = rows or []
    result.first.return_value = first
    result.scalar.return_value = scalar
    session.execute.return_value = result
    return session


class TestQueries:
    async def test_active_filter(self):
        session = _session()
        await RoutineRepository(session).get_routines(active=True)
        assert "routines.active IS true" in _sql(session.execute.call_args.args[0])

    async def test_no_filter_returns_all(self):
        session = _session()
        await RoutineRepository(session).get_routines()
        assert "WHERE" not in _sql(session.execute.call_args.args[0])

    async def test_scheduled_routines_are_active_with_a_rule(self):
        session = _session()
        await RoutineRepository(session).get_active_scheduled_routines()
        sql = _sql(session.execute.call_args.args[0])
        assert "routines.active IS true" in sql
        assert "routines.recurrence_rule IS NOT NULL" in sql

    async def test_event_ids_grouped_by_routine(self):
        session = _session(rows=[(1, 7), (1, 9), (2, 4)])
        result = await RoutineRepository(session).get_event_ids_by_routine([1, 2])
        assert result == {1: [7, 9], 2: [4]}

    async def test_event_ids_with_no_routines_skips_the_query(self):
        session = _session()
        assert await RoutineRepository(session).get_event_ids_by_routine([]) == {}
        session.execute.assert_not_called()

    async def test_routines_by_ids_with_no_ids_skips_the_query(self):
        session = _session()
        assert await RoutineRepository(session).get_routines_by_ids([]) == []
        session.execute.assert_not_called()

    async def test_next_position_starts_at_zero(self):
        assert await RoutineRepository(_session(scalar=None)).next_position(1) == 0

    async def test_next_position_follows_the_highest(self):
        assert await RoutineRepository(_session(scalar=4)).next_position(1) == 5

    async def test_position_taken(self):
        assert await RoutineRepository(_session(first=(3,))).position_taken(1, 0) is True
        assert await RoutineRepository(_session(first=None)).position_taken(1, 0) is False

    async def test_position_check_can_ignore_the_step_itself(self):
        session = _session()
        await RoutineRepository(session).position_taken(1, 0, except_step_id=9)
        assert "routine_steps.id != 9" in _sql(session.execute.call_args.args[0])

    async def test_notes_lookup_skips_deleted_notes(self):
        session = _session()
        await RoutineRepository(session).get_notes([26])
        assert "notes.deleted_at IS NULL" in _sql(session.execute.call_args.args[0])

    async def test_set_event_routine_updates_and_commits(self):
        session = _session()
        await RoutineRepository(session).set_event_routine(7, None)
        sql = _sql(session.execute.call_args.args[0])
        assert "UPDATE organizer.calendar_events SET routine_id=NULL WHERE organizer.calendar_events.id = 7" in sql
        session.commit.assert_awaited_once()


class TestStepWrites:
    """Commit expires server-generated columns (updated_at); the step must be reloaded
    before it is serialised outside the async greenlet."""

    async def test_update_step_refreshes_after_commit(self):
        session = _session()
        step = MagicMock()
        data = RoutineStepBase(title="Stretch", duration_minutes=10, anchor="start", offset_minutes=0)
        await RoutineRepository(session).update_step(step, 2, data)
        names = [c[0] for c in session.method_calls if c[0] in ("commit", "refresh")]
        assert names == ["commit", "refresh"]
        session.refresh.assert_awaited_once_with(step)

    async def test_create_step_refreshes_after_commit(self):
        session = _session()
        data = RoutineStepBase(title="Stretch", duration_minutes=10, anchor="start", offset_minutes=0)
        step = await RoutineRepository(session).create_step(1, 0, data)
        names = [c[0] for c in session.method_calls if c[0] in ("commit", "refresh")]
        assert names == ["commit", "refresh"]
        session.refresh.assert_awaited_once_with(step)
