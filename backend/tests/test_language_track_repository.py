from unittest.mock import AsyncMock, MagicMock

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.language.tracks.repository import TrackRepository
from app.features.language.tracks.schemas import TrackFilters


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


class TestGetTracks:
    async def test_default_filters_exclude_paused(self):
        session = _make_session()
        session.execute.return_value = _scalar_all([])
        await TrackRepository(session).get_tracks(TrackFilters())
        sql = _executed_sql(session)
        assert "paused_at IS NULL" in sql

    async def test_exclude_paused_false_omits_paused_at_clause(self):
        session = _make_session()
        session.execute.return_value = _scalar_all([])
        await TrackRepository(session).get_tracks(TrackFilters(exclude_paused=False))
        sql = _executed_sql(session)
        assert "paused_at IS NULL" not in sql


class TestPauseTrack:
    async def test_sets_paused_at_and_commits(self):
        session = _make_session()
        track = MagicMock(paused_at=None)
        session.execute.return_value = _scalar_first(track)
        result = await TrackRepository(session).pause_track(1)
        assert result is track
        assert track.paused_at is not None
        session.commit.assert_awaited_once()
        session.refresh.assert_awaited_once_with(track)

    async def test_returns_none_when_track_not_found(self):
        session = _make_session()
        session.execute.return_value = _scalar_first(None)
        result = await TrackRepository(session).pause_track(999)
        assert result is None
        session.commit.assert_not_awaited()


class TestResumeTrack:
    async def test_clears_paused_at_and_commits(self):
        session = _make_session()
        track = MagicMock(paused_at="2026-08-01T00:00:00+00:00")
        session.execute.return_value = _scalar_first(track)
        result = await TrackRepository(session).resume_track(1)
        assert result is track
        assert track.paused_at is None
        session.commit.assert_awaited_once()

    async def test_returns_none_when_track_not_found(self):
        session = _make_session()
        session.execute.return_value = _scalar_first(None)
        result = await TrackRepository(session).resume_track(999)
        assert result is None
        session.commit.assert_not_awaited()
