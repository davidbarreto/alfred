from datetime import date, datetime
from unittest.mock import AsyncMock, MagicMock
from zoneinfo import ZoneInfo

import pytest
from fastapi import HTTPException

from app.features.organizer.calendar_events.service import CalendarEventService


def _google_record(provider_id: str, title: str) -> dict:
    return {
        "id": provider_id,
        "title": title,
        "description": None,
        "location": None,
        "start_datetime": datetime(2026, 8, 1, 10, 0),
        "end_datetime": datetime(2026, 8, 1, 11, 0),
        "all_day": False,
        "recurrence_rule": None,
        "timezone": "Europe/Lisbon",
        "host": None,
        "invitees": [],
    }


class TestSync:
    @pytest.fixture
    def mock_provider(self):
        return AsyncMock()

    @pytest.fixture
    def mock_repo(self):
        return AsyncMock()

    @pytest.fixture
    def service(self, mock_provider, mock_repo):
        svc = CalendarEventService(provider=mock_provider, session=AsyncMock())
        svc._repo = mock_repo
        return svc

    @pytest.mark.asyncio
    async def test_raises_when_not_authorized(self):
        service = CalendarEventService(provider=None, session=AsyncMock())
        with pytest.raises(HTTPException) as exc_info:
            await service.sync()
        assert exc_info.value.status_code == 503

    @pytest.mark.asyncio
    async def test_creates_new_and_updates_existing_events(self, service, mock_provider, mock_repo):
        mock_provider.list.return_value = [
            _google_record("g-new", "New Event"),
            _google_record("g-existing", "Updated Event"),
        ]
        existing = MagicMock(id=42)
        mock_repo.get_event_by_provider_id.side_effect = [None, existing]

        result = await service.sync(date(2026, 8, 1), date(2026, 8, 2))

        mock_repo.create_event.assert_called_once()
        create_args = mock_repo.create_event.call_args[0]
        assert create_args[1] == "g-new"

        mock_repo.update_event.assert_called_once()
        update_args = mock_repo.update_event.call_args[0]
        assert update_args[0] == 42
        # tags must stay untouched on update so locally-added tags survive a sync
        assert "tags" not in update_args[1].model_dump(exclude_unset=True)

        assert result.created == 1
        assert result.updated == 1
        assert result.start == date(2026, 8, 1)
        assert result.end == date(2026, 8, 2)

    @pytest.mark.asyncio
    async def test_defaults_to_today_through_three_months_ahead(self, service, mock_provider, mock_repo, monkeypatch):
        monkeypatch.setattr(
            "app.features.organizer.calendar_events.service.local_now",
            lambda: datetime(2026, 7, 21, 9, 0, tzinfo=ZoneInfo("Europe/Lisbon")),
        )
        mock_provider.list.return_value = []

        result = await service.sync()

        assert result.start == date(2026, 7, 21)
        assert result.end == date(2026, 10, 21)

        filters = mock_provider.list.call_args[0][0]
        assert filters["start_from"].date() == date(2026, 7, 21)
        assert filters["start_to"].date() == date(2026, 10, 21)
        assert filters["start_from"].tzinfo is not None
        assert filters["start_to"].tzinfo is not None
