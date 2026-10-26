from datetime import date, datetime

import pytest

from app.features.organizer.calendar_events.recurrence import end_rule_before, expand_occurrences


class TestExpandOccurrences:
    def test_weekly_series_expands_into_range(self):
        start = datetime(2026, 1, 5, 10, 0)  # Monday
        end = datetime(2026, 1, 5, 11, 0)
        spans = expand_occurrences(
            start, end, "FREQ=WEEKLY",
            range_start=datetime(2026, 3, 1), range_end=datetime(2026, 3, 31, 23, 59, 59),
        )
        assert [s.date().isoformat() for s, _ in spans] == [
            "2026-03-02", "2026-03-09", "2026-03-16", "2026-03-23", "2026-03-30",
        ]
        for s, e in spans:
            assert e - s == end - start

    def test_series_starting_after_range_returns_empty(self):
        start = datetime(2026, 6, 1, 10, 0)
        end = datetime(2026, 6, 1, 11, 0)
        spans = expand_occurrences(
            start, end, "FREQ=WEEKLY",
            range_start=datetime(2026, 1, 1), range_end=datetime(2026, 1, 31),
        )
        assert spans == []

    def test_occurrence_overlapping_range_start_is_included(self):
        # A multi-hour event whose start precedes range_start but whose end falls inside it.
        start = datetime(2026, 1, 5, 23, 0)
        end = datetime(2026, 1, 6, 1, 0)
        spans = expand_occurrences(
            start, end, "FREQ=WEEKLY",
            range_start=datetime(2026, 1, 13), range_end=datetime(2026, 1, 13, 23, 59, 59),
        )
        assert spans == [(datetime(2026, 1, 12, 23, 0), datetime(2026, 1, 13, 1, 0))]

    def test_master_start_datetime_included_when_no_range(self):
        start = datetime(2026, 1, 5, 10, 0)
        end = datetime(2026, 1, 5, 11, 0)
        spans = expand_occurrences(start, end, "FREQ=WEEKLY;COUNT=3", None, None)
        assert spans == [
            (datetime(2026, 1, 5, 10, 0), datetime(2026, 1, 5, 11, 0)),
            (datetime(2026, 1, 12, 10, 0), datetime(2026, 1, 12, 11, 0)),
            (datetime(2026, 1, 19, 10, 0), datetime(2026, 1, 19, 11, 0)),
        ]

    def test_range_entirely_before_series_start_returns_empty(self):
        start = datetime(2026, 6, 1, 10, 0)
        end = datetime(2026, 6, 1, 11, 0)
        spans = expand_occurrences(
            start, end, "FREQ=DAILY",
            range_start=datetime(2025, 1, 1), range_end=datetime(2025, 1, 31),
        )
        assert spans == []

    def test_invalid_rule_raises_value_error(self):
        start = datetime(2026, 1, 5, 10, 0)
        end = datetime(2026, 1, 5, 11, 0)
        with pytest.raises(ValueError):
            expand_occurrences(start, end, "NOT-A-VALID-RRULE", None, None)

    def test_utc_until_from_google_calendar_does_not_raise(self):
        # Google Calendar always encodes UNTIL in UTC ("Z"), but start_datetime here
        # is the naive local datetime LocalDateTime hands back — this combination
        # used to raise "RRULE UNTIL values must be specified in UTC when DTSTART
        # is timezone-aware" from dateutil.rrule.
        start = datetime(2026, 1, 5, 10, 0)
        end = datetime(2026, 1, 5, 11, 0)
        spans = expand_occurrences(
            start, end, "FREQ=WEEKLY;UNTIL=20260119T100000Z",
            range_start=None, range_end=None,
        )
        assert [s.date().isoformat() for s, _ in spans] == ["2026-01-05", "2026-01-12", "2026-01-19"]


class TestEndRuleBefore:
    def test_timed_series_ends_with_a_utc_until_before_the_excluded_day(self):
        rule = end_rule_before("FREQ=WEEKLY;BYDAY=WE", date(2026, 11, 18), all_day=False)

        assert rule == "FREQ=WEEKLY;BYDAY=WE;UNTIL=20261117T235959Z"

    def test_summer_until_is_shifted_by_the_dst_offset(self):
        rule = end_rule_before("FREQ=DAILY", date(2026, 7, 15), all_day=False)

        assert rule == "FREQ=DAILY;UNTIL=20260714T225959Z"

    def test_all_day_series_ends_with_a_date_until(self):
        assert end_rule_before("FREQ=WEEKLY", date(2026, 11, 18), all_day=True) == "FREQ=WEEKLY;UNTIL=20261117"

    @pytest.mark.parametrize("existing", ["FREQ=WEEKLY;COUNT=10", "FREQ=WEEKLY;UNTIL=20271231T235959Z", "COUNT=5;FREQ=WEEKLY"])
    def test_existing_count_or_until_is_replaced(self, existing):
        rule = end_rule_before(existing, date(2026, 11, 18), all_day=False)

        assert rule == "FREQ=WEEKLY;UNTIL=20261117T235959Z"

    def test_expansion_stops_before_the_excluded_day(self):
        start, end = datetime(2026, 11, 4, 14, 30), datetime(2026, 11, 4, 15, 0)  # a Wednesday
        rule = end_rule_before("FREQ=WEEKLY", date(2026, 11, 18), all_day=False)

        spans = expand_occurrences(start, end, rule, datetime(2026, 11, 1), datetime(2026, 12, 31))

        assert [s.date().isoformat() for s, _ in spans] == ["2026-11-04", "2026-11-11"]

    def test_all_day_expansion_includes_the_last_day_and_stops_after(self):
        start, end = datetime(2026, 11, 4), datetime(2026, 11, 4, 23, 59, 59)
        rule = end_rule_before("FREQ=DAILY", date(2026, 11, 7), all_day=True)

        spans = expand_occurrences(start, end, rule, datetime(2026, 11, 1), datetime(2026, 12, 31))

        assert [s.date().isoformat() for s, _ in spans] == ["2026-11-04", "2026-11-05", "2026-11-06"]


class TestForeignTimezoneSeries:
    """A series keeps its wall time in the event's own zone, so its local time follows that zone's DST."""

    # 2026-10-21 18:00 in Sao Paulo (UTC-3) is 22:00 in Lisbon (UTC+1, summer time) -- stored as naive local.
    START = datetime(2026, 10, 21, 22, 0)
    END = datetime(2026, 10, 21, 23, 0)

    def _spans(self, rule="FREQ=WEEKLY", tz="America/Sao_Paulo"):
        return expand_occurrences(
            self.START, self.END, rule, datetime(2026, 10, 1), datetime(2026, 11, 30), event_timezone=tz
        )

    def test_occurrences_after_lisbon_dst_ends_shift_with_the_offset(self):
        spans = self._spans()
        assert [(s.isoformat(), e.isoformat()) for s, e in spans if s.date().isoformat() in ("2026-10-21", "2026-10-28")] == [
            ("2026-10-21T22:00:00", "2026-10-21T23:00:00"),
            ("2026-10-28T21:00:00", "2026-10-28T22:00:00"),
        ]

    def test_without_a_timezone_the_wall_time_stays_local(self):
        assert {s.hour for s, _ in self._spans(tz=None)} == {22}

    def test_same_zone_as_the_app_behaves_like_no_zone(self):
        assert self._spans(tz="Europe/Lisbon") == self._spans(tz=None)

    def test_unknown_zone_falls_back_to_local_wall_time(self):
        assert self._spans(tz="Not/AZone") == self._spans(tz=None)

    def test_range_is_still_given_in_local_time(self):
        spans = expand_occurrences(
            self.START, self.END, "FREQ=WEEKLY", datetime(2026, 10, 28), datetime(2026, 10, 28, 23, 59), event_timezone="America/Sao_Paulo"
        )
        assert [s.isoformat() for s, _ in spans] == ["2026-10-28T21:00:00"]

    def test_utc_until_is_read_in_the_event_zone(self):
        # UNTIL 2026-10-28T21:00:00Z = 18:00 in Sao Paulo: the 28th occurrence is the last one.
        spans = self._spans(rule="FREQ=WEEKLY;UNTIL=20261028T210000Z")
        assert [s.date().isoformat() for s, _ in spans] == ["2026-10-21", "2026-10-28"]
