from datetime import date
from unittest.mock import AsyncMock

import pytest

from app.features.briefing.schemas import HolidayItem
from app.features.organizer.holidays.errors import HolidayRangeError
from app.features.organizer.holidays.service import MAX_RANGE_DAYS, HolidayService


def _item(day: date, name: str, country: str = "PT") -> HolidayItem:
    return HolidayItem(name=name, local_name=name, country=country, days_until=0, date=day)


@pytest.fixture
def provider():
    p = AsyncMock()
    p.get_holidays.return_value = [
        _item(date(2026, 12, 25), "Christmas Day"),
        _item(date(2026, 12, 1), "Restoration of Independence"),
    ]
    return p


class TestList:
    async def test_returns_holidays_sorted_by_date(self, provider):
        result = await HolidayService(provider).list(date(2026, 12, 1), date(2026, 12, 31))

        assert [(h.date, h.name, h.country) for h in result] == [
            (date(2026, 12, 1), "Restoration of Independence", "PT"),
            (date(2026, 12, 25), "Christmas Day", "PT"),
        ]
        provider.get_holidays.assert_awaited_once_with(date(2026, 12, 1), date(2026, 12, 31))

    async def test_drops_holidays_outside_the_range(self, provider):
        result = await HolidayService(provider).list(date(2026, 12, 1), date(2026, 12, 24))

        assert [h.name for h in result] == ["Restoration of Independence"]

    async def test_no_provider_means_no_holidays(self):
        assert await HolidayService(None).list(date(2026, 12, 1), date(2026, 12, 31)) == []

    async def test_single_day_range_is_allowed(self, provider):
        result = await HolidayService(provider).list(date(2026, 12, 25), date(2026, 12, 25))

        assert [h.name for h in result] == ["Christmas Day"]

    async def test_reversed_range_is_rejected(self, provider):
        with pytest.raises(HolidayRangeError):
            await HolidayService(provider).list(date(2026, 12, 2), date(2026, 12, 1))
        provider.get_holidays.assert_not_awaited()

    async def test_too_long_range_is_rejected(self, provider):
        start = date(2026, 1, 1)
        with pytest.raises(HolidayRangeError):
            await HolidayService(provider).list(start, date.fromordinal(start.toordinal() + MAX_RANGE_DAYS))
        provider.get_holidays.assert_not_awaited()
