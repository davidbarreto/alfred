from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from app.features.organizer.shopping.frequency import average_interval_days, next_expected_on, purchase_days

_LISBON = ZoneInfo("Europe/Lisbon")


def _utc(y, m, d, h=12, minute=0):
    return datetime(y, m, d, h, minute, tzinfo=timezone.utc)


class TestPurchaseDays:
    def test_entries_ticked_on_the_same_day_are_one_purchase(self):
        moments = [_utc(2026, 10, 1, 18, 0), _utc(2026, 10, 1, 18, 5), _utc(2026, 10, 1, 19, 0)]

        assert purchase_days(moments, _LISBON) == [date(2026, 10, 1)]

    def test_days_are_local_not_utc(self):
        # 23:30 UTC in July is 00:30 the next day in Lisbon
        assert purchase_days([_utc(2026, 7, 15, 23, 30)], _LISBON) == [date(2026, 7, 16)]

    def test_sorted_oldest_first(self):
        moments = [_utc(2026, 10, 9), _utc(2026, 10, 1), _utc(2026, 10, 5)]

        assert purchase_days(moments, _LISBON) == [date(2026, 10, 1), date(2026, 10, 5), date(2026, 10, 9)]


class TestAverageIntervalDays:
    def test_none_without_two_purchases(self):
        assert average_interval_days([]) is None
        assert average_interval_days([date(2026, 10, 1)]) is None

    def test_mean_gap_between_consecutive_purchases(self):
        days = [date(2026, 10, 1), date(2026, 10, 5), date(2026, 10, 13)]  # gaps 4 and 8

        assert average_interval_days(days) == 6


class TestNextExpectedOn:
    def test_last_purchase_plus_rounded_average(self):
        assert next_expected_on(date(2026, 10, 13), 6.4) == date(2026, 10, 19)
