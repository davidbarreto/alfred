from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.features.briefing.holiday_client import GooglePublicHolidayClient


def _make_response(items: list[dict], status_code: int = 200) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.is_error = status_code >= 400
    resp.json.return_value = {"items": items}
    resp.raise_for_status = MagicMock(
        side_effect=Exception("HTTP error") if status_code >= 400 else None
    )
    return resp


def _make_item(summary: str, event_date: str = "2026-06-24") -> dict:
    return {"summary": summary, "start": {"date": event_date}}


class TestGooglePublicHolidayClient:
    @pytest.mark.asyncio
    async def test_returns_holidays_for_each_calendar(self):
        responses = {
            "pt.portuguese%23holiday%40group.v.calendar.google.com": _make_response(
                [_make_item("São João do Porto")]
            ),
            "en.brazilian%23holiday%40group.v.calendar.google.com": _make_response(
                [_make_item("Corpus Christi")]
            ),
        }

        async def fake_get(url, params=None):
            for key, resp in responses.items():
                if key in url or key.replace("%23", "#").replace("%40", "@") in url:
                    return resp
            return _make_response([])

        with patch("app.features.briefing.holiday_client.httpx.AsyncClient") as MockClient:
            mock_http = AsyncMock()
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=None)
            mock_http.get = AsyncMock(side_effect=fake_get)
            MockClient.return_value = mock_http

            client = GooglePublicHolidayClient(api_key="test-key")
            result = await client.get_holidays(date(2026, 6, 24), date(2026, 6, 30))

        assert len(result) == 2
        countries = {h.country for h in result}
        assert countries == {"PT", "BR"}

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_events(self):
        async def fake_get(url, params=None):
            return _make_response([])

        with patch("app.features.briefing.holiday_client.httpx.AsyncClient") as MockClient:
            mock_http = AsyncMock()
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=None)
            mock_http.get = AsyncMock(side_effect=fake_get)
            MockClient.return_value = mock_http

            client = GooglePublicHolidayClient(api_key="test-key")
            result = await client.get_holidays(date(2026, 6, 10), date(2026, 6, 17))

        assert result == []

    @pytest.mark.asyncio
    async def test_logs_warning_on_error_and_continues(self):
        call_count = 0

        async def fake_get(url, params=None):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("Network error")
            return _make_response([_make_item("Corpus Christi")])

        with patch("app.features.briefing.holiday_client.httpx.AsyncClient") as MockClient:
            mock_http = AsyncMock()
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=None)
            mock_http.get = AsyncMock(side_effect=fake_get)
            MockClient.return_value = mock_http

            client = GooglePublicHolidayClient(api_key="test-key")
            result = await client.get_holidays(date(2026, 6, 24), date(2026, 6, 30))

        assert len(result) == 1
        assert result[0].country == "BR"

    @pytest.mark.asyncio
    async def test_passes_correct_time_window(self):
        captured_params: list[dict] = []

        async def fake_get(url, params=None):
            captured_params.append(params or {})
            return _make_response([])

        with patch("app.features.briefing.holiday_client.httpx.AsyncClient") as MockClient:
            mock_http = AsyncMock()
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=None)
            mock_http.get = AsyncMock(side_effect=fake_get)
            MockClient.return_value = mock_http

            client = GooglePublicHolidayClient(api_key="test-key")
            await client.get_holidays(date(2026, 6, 24), date(2026, 6, 30))

        assert captured_params[0]["timeMin"] == "2026-06-24T00:00:00Z"
        assert captured_params[0]["timeMax"] == "2026-07-01T00:00:00Z"
        assert captured_params[0]["singleEvents"] == "true"

    @pytest.mark.asyncio
    async def test_computes_days_until_from_event_date(self):
        async def fake_get(url, params=None):
            return _make_response([_make_item("National Day", "2026-06-26")])

        with patch("app.features.briefing.holiday_client.httpx.AsyncClient") as MockClient:
            mock_http = AsyncMock()
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=None)
            mock_http.get = AsyncMock(side_effect=fake_get)
            MockClient.return_value = mock_http

            client = GooglePublicHolidayClient(api_key="test-key")
            result = await client.get_holidays(date(2026, 6, 24), date(2026, 6, 30))

        assert len(result) >= 1
        national_days = [h for h in result if h.name == "National Day"]
        assert national_days[0].days_until == 2
        assert national_days[0].date == date(2026, 6, 26)

    @pytest.mark.asyncio
    async def test_skips_items_without_start_date(self):
        async def fake_get(url, params=None):
            return _make_response([{"summary": "No Date Event", "start": {}}])

        with patch("app.features.briefing.holiday_client.httpx.AsyncClient") as MockClient:
            mock_http = AsyncMock()
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=None)
            mock_http.get = AsyncMock(side_effect=fake_get)
            MockClient.return_value = mock_http

            client = GooglePublicHolidayClient(api_key="test-key")
            result = await client.get_holidays(date(2026, 6, 24), date(2026, 6, 30))

        assert result == []

    @pytest.mark.asyncio
    async def test_results_sorted_by_days_until(self):
        async def fake_get(url, params=None):
            if "pt.portuguese" in url or "pt.portuguese" in url.replace("%23", "#").replace("%40", "@"):
                return _make_response([_make_item("Holiday PT", "2026-06-27")])
            return _make_response([_make_item("Holiday BR", "2026-06-25")])

        with patch("app.features.briefing.holiday_client.httpx.AsyncClient") as MockClient:
            mock_http = AsyncMock()
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=None)
            mock_http.get = AsyncMock(side_effect=fake_get)
            MockClient.return_value = mock_http

            client = GooglePublicHolidayClient(api_key="test-key")
            result = await client.get_holidays(date(2026, 6, 24), date(2026, 6, 30))

        assert result[0].days_until <= result[1].days_until
