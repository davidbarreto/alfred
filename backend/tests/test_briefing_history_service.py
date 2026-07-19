from datetime import date
from unittest.mock import AsyncMock

import pytest

from app.features.briefing.history_service import BriefingHistoryService
from app.features.briefing.schemas import BriefingHistoryItem


def _make_briefing_orm(**kwargs):
    from unittest.mock import MagicMock
    b = MagicMock()
    b.date = kwargs.get("date", date(2026, 7, 18))
    b.type = kwargs.get("type", "evening")
    b.text = kwargs.get("text", "Some text")
    return b


class TestBriefingHistoryService:
    @pytest.fixture
    def service(self):
        svc = BriefingHistoryService(session=AsyncMock())
        svc._repo = AsyncMock()
        return svc

    @pytest.mark.asyncio
    async def test_returns_history_items(self, service):
        service._repo.list_briefings.return_value = [
            _make_briefing_orm(type="evening", text="Evening digest."),
            _make_briefing_orm(type="morning", text="Morning briefing."),
        ]

        result = await service.list(briefing_type=None, limit=20, offset=0)

        assert result == [
            BriefingHistoryItem(date=date(2026, 7, 18), type="evening", text="Evening digest."),
            BriefingHistoryItem(date=date(2026, 7, 18), type="morning", text="Morning briefing."),
        ]

    @pytest.mark.asyncio
    async def test_forwards_filters_to_repository(self, service):
        service._repo.list_briefings.return_value = []

        await service.list(briefing_type="morning", limit=5, offset=10)

        service._repo.list_briefings.assert_called_once_with("morning", 5, 10)

    @pytest.mark.asyncio
    async def test_empty_when_no_briefings(self, service):
        service._repo.list_briefings.return_value = []

        result = await service.list(briefing_type=None, limit=20, offset=0)

        assert result == []
