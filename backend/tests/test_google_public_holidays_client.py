from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.integrations.google_public_holidays.client import GooglePublicHolidayClient


class TestFetchEvents:
    @pytest.mark.asyncio
    async def test_returns_items(self):
        response = MagicMock()
        response.raise_for_status = MagicMock()
        response.json.return_value = {"items": [{"summary": "Holiday"}]}

        client = GooglePublicHolidayClient(api_key="test-key")
        with patch("app.integrations.google_public_holidays.client.httpx.AsyncClient") as mock_http:
            mock_http.return_value.__aenter__.return_value.get = AsyncMock(return_value=response)
            result = await client.fetch_events(
                "pt.portuguese#holiday@group.v.calendar.google.com",
                "2026-06-24T00:00:00Z",
                "2026-07-01T00:00:00Z",
            )

        assert result == [{"summary": "Holiday"}]

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_items(self):
        response = MagicMock()
        response.raise_for_status = MagicMock()
        response.json.return_value = {}

        client = GooglePublicHolidayClient(api_key="test-key")
        with patch("app.integrations.google_public_holidays.client.httpx.AsyncClient") as mock_http:
            mock_http.return_value.__aenter__.return_value.get = AsyncMock(return_value=response)
            result = await client.fetch_events("cal-id", "2026-06-24T00:00:00Z", "2026-07-01T00:00:00Z")

        assert result == []

    @pytest.mark.asyncio
    async def test_passes_api_key_and_window(self):
        response = MagicMock()
        response.raise_for_status = MagicMock()
        response.json.return_value = {"items": []}

        client = GooglePublicHolidayClient(api_key="test-key")
        with patch("app.integrations.google_public_holidays.client.httpx.AsyncClient") as mock_http:
            get_mock = AsyncMock(return_value=response)
            mock_http.return_value.__aenter__.return_value.get = get_mock
            await client.fetch_events("cal-id", "2026-06-24T00:00:00Z", "2026-07-01T00:00:00Z")

        params = get_mock.call_args[1]["params"]
        assert params["key"] == "test-key"
        assert params["timeMin"] == "2026-06-24T00:00:00Z"
        assert params["timeMax"] == "2026-07-01T00:00:00Z"
        assert params["singleEvents"] == "true"

    @pytest.mark.asyncio
    async def test_raises_on_http_error(self):
        response = MagicMock()
        response.raise_for_status = MagicMock(side_effect=Exception("HTTP error"))

        client = GooglePublicHolidayClient(api_key="test-key")
        with patch("app.integrations.google_public_holidays.client.httpx.AsyncClient") as mock_http:
            mock_http.return_value.__aenter__.return_value.get = AsyncMock(return_value=response)
            with pytest.raises(Exception):
                await client.fetch_events("cal-id", "2026-06-24T00:00:00Z", "2026-07-01T00:00:00Z")
