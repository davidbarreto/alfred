from datetime import date
from unittest.mock import AsyncMock, MagicMock

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.briefing.repository import BriefingRepository
from app.features.briefing.tables import Briefing


def _make_session() -> AsyncMock:
    return AsyncMock(spec=AsyncSession)


def _scalar_first(value):
    result = MagicMock()
    result.scalars.return_value.first.return_value = value
    return result


def _make_briefing_orm(**kwargs):
    b = MagicMock()
    b.id = kwargs.get("id", 1)
    b.date = kwargs.get("date", date(2026, 7, 10))
    b.text = kwargs.get("text", "Good morning!")
    return b


class TestGetBriefingByDate:
    async def test_found(self):
        session = _make_session()
        briefing = _make_briefing_orm()
        session.execute.return_value = _scalar_first(briefing)

        repo = BriefingRepository(session)
        result = await repo.get_briefing_by_date(date(2026, 7, 10), "morning")

        assert result == briefing
        session.execute.assert_called_once()

    async def test_not_found(self):
        session = _make_session()
        session.execute.return_value = _scalar_first(None)

        repo = BriefingRepository(session)
        assert await repo.get_briefing_by_date(date(2026, 7, 10), "morning") is None


class TestUpsertBriefing:
    async def test_creates_when_missing(self):
        session = _make_session()
        session.execute.return_value = _scalar_first(None)
        session.add = MagicMock()

        repo = BriefingRepository(session)
        result = await repo.upsert_briefing(date(2026, 7, 10), "morning", "Fresh text")

        session.add.assert_called_once()
        added = session.add.call_args[0][0]
        assert isinstance(added, Briefing)
        assert added.date == date(2026, 7, 10)
        assert added.type == "morning"
        assert added.text == "Fresh text"
        assert result is added
        session.flush.assert_called_once()

    async def test_updates_when_existing(self):
        session = _make_session()
        existing = _make_briefing_orm(text="Old text")
        session.execute.return_value = _scalar_first(existing)
        session.add = MagicMock()

        repo = BriefingRepository(session)
        result = await repo.upsert_briefing(date(2026, 7, 10), "morning", "New text")

        session.add.assert_not_called()
        assert result is existing
        assert existing.text == "New text"
        session.flush.assert_called_once()

    async def test_creates_separate_row_per_type(self):
        session = _make_session()
        session.execute.return_value = _scalar_first(None)
        session.add = MagicMock()

        repo = BriefingRepository(session)
        result = await repo.upsert_briefing(date(2026, 7, 10), "evening", "Evening text")

        added = session.add.call_args[0][0]
        assert added.type == "evening"
        assert result.type == "evening"
