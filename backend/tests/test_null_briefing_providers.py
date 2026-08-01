from datetime import date

import pytest

from app.integrations.null.holiday_provider import NullHolidayProvider
from app.integrations.null.weather_provider import NullWeatherProvider


class TestNullWeatherProvider:

    @pytest.mark.asyncio
    async def test_get_daily_forecast_returns_a_well_formed_placeholder(self):
        provider = NullWeatherProvider()

        forecast = await provider.get_daily_forecast(date(2026, 1, 1))

        assert forecast.precipitation_probability == 0
        assert forecast.advice == []


class TestNullHolidayProvider:

    @pytest.mark.asyncio
    async def test_get_holidays_returns_empty_list(self):
        provider = NullHolidayProvider()

        holidays = await provider.get_holidays(date(2026, 1, 1), date(2026, 1, 31))

        assert holidays == []
