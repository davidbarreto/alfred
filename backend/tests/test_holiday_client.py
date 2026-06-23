from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.features.briefing.holiday_client import NagerDateHolidayClient


def _make_response(entries: list[dict], status_code: int = 200) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.is_error = status_code >= 400
    resp.json.return_value = entries
    resp.raise_for_status = MagicMock(
        side_effect=Exception("HTTP error") if status_code >= 400 else None
    )
    return resp


class TestNagerDateHolidayClient:
    @pytest.mark.asyncio
    async def test_returns_matching_holidays(self):
        target = date(2026, 6, 10)
        pt_holidays = [
            {"date": "2026-06-10", "name": "Portugal Day", "localName": "Dia de Portugal", "countryCode": "PT"},
            {"date": "2026-06-15", "name": "Other Day", "localName": "Outro Dia", "countryCode": "PT"},
        ]
        br_holidays = [
            {"date": "2026-06-10", "name": "Corpus Christi", "localName": "Corpus Christi", "countryCode": "BR"},
        ]

        responses = {"PT": _make_response(pt_holidays), "BR": _make_response(br_holidays)}

        async def fake_get(url, params=None):
            country = url.split("/")[-1]
            return responses[country]

        with patch("app.features.briefing.holiday_client.httpx.AsyncClient") as MockClient:
            mock_http = AsyncMock()
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=None)
            mock_http.get = AsyncMock(side_effect=fake_get)
            MockClient.return_value = mock_http

            client = NagerDateHolidayClient()
            result = await client.get_holidays(target)

        assert len(result) == 2
        countries = {h.country for h in result}
        assert countries == {"PT", "BR"}

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_match(self):
        pt_holidays = [
            {"date": "2026-06-15", "name": "Other", "localName": "Outro", "countryCode": "PT"},
        ]

        async def fake_get(url, params=None):
            return _make_response(pt_holidays)

        with patch("app.features.briefing.holiday_client.httpx.AsyncClient") as MockClient:
            mock_http = AsyncMock()
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=None)
            mock_http.get = AsyncMock(side_effect=fake_get)
            MockClient.return_value = mock_http

            client = NagerDateHolidayClient()
            result = await client.get_holidays(date(2026, 6, 10))

        assert result == []

    @pytest.mark.asyncio
    async def test_logs_warning_on_http_error_and_continues(self):
        async def fake_get(url, params=None):
            country = url.split("/")[-1]
            if country == "PT":
                raise Exception("Network error")
            return _make_response([
                {"date": "2026-06-10", "name": "Holiday", "localName": "Feriado", "countryCode": "BR"}
            ])

        with patch("app.features.briefing.holiday_client.httpx.AsyncClient") as MockClient:
            mock_http = AsyncMock()
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=None)
            mock_http.get = AsyncMock(side_effect=fake_get)
            MockClient.return_value = mock_http

            client = NagerDateHolidayClient()
            result = await client.get_holidays(date(2026, 6, 10))

        assert len(result) == 1
        assert result[0].country == "BR"
