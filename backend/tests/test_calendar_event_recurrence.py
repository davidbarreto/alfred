from datetime import datetime

import pytest

from app.features.organizer.calendar_events.recurrence import expand_occurrences


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
