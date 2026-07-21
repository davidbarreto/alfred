from datetime import date
from unittest.mock import AsyncMock, patch

import pytest

from app.integrations.google_public_holidays.provider import GooglePublicHolidayProvider


def _event(summary: str, event_date: str = "2026-06-24") -> dict:
    return {"summary": summary, "start": {"date": event_date}}


class TestGetHolidays:
    @pytest.fixture
    def client(self):
        return AsyncMock()

    @pytest.fixture
    def provider(self, client):
        return GooglePublicHolidayProvider(client)

    @pytest.mark.asyncio
    async def test_returns_holidays_for_each_calendar(self, provider, client):
        client.fetch_events.side_effect = [
            [_event("São João do Porto")],
            [_event("Corpus Christi")],
        ]

        result = await provider.get_holidays(date(2026, 6, 24), date(2026, 6, 30))

        assert len(result) == 2
        assert {h.country for h in result} == {"PT", "BR"}

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_events(self, provider, client):
        client.fetch_events.return_value = []
        result = await provider.get_holidays(date(2026, 6, 10), date(2026, 6, 17))
        assert result == []

    @pytest.mark.asyncio
    async def test_logs_warning_and_continues_on_error(self, provider, client):
        client.fetch_events.side_effect = [Exception("Network error"), [_event("Corpus Christi")]]

        result = await provider.get_holidays(date(2026, 6, 24), date(2026, 6, 30))

        assert len(result) == 1
        assert result[0].country == "BR"

    @pytest.mark.asyncio
    async def test_passes_correct_time_window(self, provider, client):
        client.fetch_events.return_value = []
        await provider.get_holidays(date(2026, 6, 24), date(2026, 6, 30))

        _, time_min, time_max = client.fetch_events.call_args_list[0].args
        assert time_min == "2026-06-24T00:00:00Z"
        assert time_max == "2026-07-01T00:00:00Z"

    @pytest.mark.asyncio
    async def test_computes_days_until_from_event_date(self, provider, client):
        client.fetch_events.side_effect = [[_event("National Day", "2026-06-26")], []]

        result = await provider.get_holidays(date(2026, 6, 24), date(2026, 6, 30))

        national_days = [h for h in result if h.name == "National Day"]
        assert national_days[0].days_until == 2
        assert national_days[0].date == date(2026, 6, 26)

    @pytest.mark.asyncio
    async def test_skips_items_without_start_date(self, provider, client):
        client.fetch_events.return_value = [{"summary": "No Date Event", "start": {}}]
        result = await provider.get_holidays(date(2026, 6, 24), date(2026, 6, 30))
        assert result == []

    @pytest.mark.asyncio
    async def test_results_sorted_by_days_until(self, provider, client):
        client.fetch_events.side_effect = [
            [_event("Holiday PT", "2026-06-27")],
            [_event("Holiday BR", "2026-06-25")],
        ]

        result = await provider.get_holidays(date(2026, 6, 24), date(2026, 6, 30))

        assert result[0].days_until <= result[1].days_until

    @pytest.mark.asyncio
    async def test_logs_one_sync_call_per_country(self, provider, client):
        client.fetch_events.return_value = [_event("Holiday")]
        session = AsyncMock()

        with patch("app.integrations.google_public_holidays.provider.create_sync_log", new=AsyncMock()) as mock_log:
            await provider.get_holidays(date(2026, 6, 24), date(2026, 6, 30), session=session)

        assert mock_log.await_count == 2
        countries = {c.kwargs["provider_entity_id"] for c in mock_log.call_args_list}
        assert countries == {"PT", "BR"}
        assert all(c.kwargs["status"] == "ok" for c in mock_log.call_args_list)

    @pytest.mark.asyncio
    async def test_skips_logging_when_session_none(self, provider, client):
        client.fetch_events.return_value = []
        with patch("app.integrations.google_public_holidays.provider.create_sync_log", new=AsyncMock()) as mock_log:
            await provider.get_holidays(date(2026, 6, 24), date(2026, 6, 30))

        mock_log.assert_not_called()

    @pytest.mark.asyncio
    async def test_logs_error_status_for_failed_country(self, provider, client):
        client.fetch_events.side_effect = [Exception("Network error"), []]
        session = AsyncMock()

        with patch("app.integrations.google_public_holidays.provider.create_sync_log", new=AsyncMock()) as mock_log:
            await provider.get_holidays(date(2026, 6, 24), date(2026, 6, 30), session=session)

        statuses = {c.kwargs["provider_entity_id"]: c.kwargs["status"] for c in mock_log.call_args_list}
        assert "error" in statuses.values()
