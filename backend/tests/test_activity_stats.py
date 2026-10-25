from datetime import date, datetime

from app.features.organizer.activities.stats import LogRow, compute_stats, monday_of, week_starts

WED = date(2026, 10, 21)


def _row(activity_id=1, title="Gym", tags=("health",), done_at=datetime(2026, 10, 20, 18, 0), minutes=60):
    return LogRow(activity_id=activity_id, title=title, tags=tags, done_at=done_at, minutes=minutes)


class TestWeeks:
    def test_monday_of(self):
        assert monday_of(WED) == date(2026, 10, 19)
        assert monday_of(date(2026, 10, 25)) == date(2026, 10, 19)
        assert monday_of(date(2026, 10, 19)) == date(2026, 10, 19)

    def test_week_starts_end_with_the_current_week_oldest_first(self):
        assert week_starts(WED, 3) == [date(2026, 10, 5), date(2026, 10, 12), date(2026, 10, 19)]

    def test_single_week(self):
        assert week_starts(WED, 1) == [date(2026, 10, 19)]


class TestComputeStats:
    def test_counts_and_minutes_per_week_including_empty_weeks(self):
        rows = [
            _row(done_at=datetime(2026, 10, 20, 18, 0), minutes=60),
            _row(done_at=datetime(2026, 10, 19, 7, 0), minutes=30),
            _row(done_at=datetime(2026, 10, 6, 7, 0), minutes=45),
        ]
        stats = compute_stats(rows, week_starts(WED, 3))
        assert [(w.week_start.isoformat(), w.count, w.minutes) for w in stats.weeks] == [
            ("2026-10-05", 1, 45), ("2026-10-12", 0, 0), ("2026-10-19", 2, 90),
        ]
        assert (stats.total_count, stats.total_minutes) == (3, 135)

    def test_logs_without_minutes_count_but_add_no_minutes(self):
        stats = compute_stats([_row(minutes=None), _row(minutes=20)], week_starts(WED, 1))
        assert (stats.total_count, stats.total_minutes) == (2, 20)
        assert stats.weeks[0].count == 2

    def test_rows_outside_the_window_are_ignored(self):
        stats = compute_stats([_row(done_at=datetime(2026, 1, 1, 10, 0))], week_starts(WED, 2))
        assert stats.total_count == 0 and stats.by_activity == [] and stats.by_tag == []

    def test_sunday_night_belongs_to_the_week_that_is_ending(self):
        stats = compute_stats([_row(done_at=datetime(2026, 10, 25, 23, 30))], week_starts(WED, 1))
        assert stats.weeks[0].count == 1

    def test_per_activity_sorted_by_count_then_title(self):
        rows = [
            _row(1, "Gym"), _row(2, "Book", tags=()), _row(2, "Book", tags=()), _row(3, "Art", tags=()), _row(3, "Art", tags=()),
        ]
        stats = compute_stats(rows, week_starts(WED, 1))
        assert [(a.title, a.count) for a in stats.by_activity] == [("Art", 2), ("Book", 2), ("Gym", 1)]

    def test_per_tag_counts_every_tag_of_a_log(self):
        rows = [
            _row(1, "Gym", tags=("health", "out"), minutes=60),
            _row(2, "Run", tags=("health",), minutes=30),
        ]
        stats = compute_stats(rows, week_starts(WED, 1))
        assert [(t.tag, t.count, t.minutes) for t in stats.by_tag] == [("health", 2, 90), ("out", 1, 60)]

    def test_empty(self):
        stats = compute_stats([], week_starts(WED, 2))
        assert len(stats.weeks) == 2 and stats.total_count == 0
