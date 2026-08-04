import datetime

import pytest
from unittest.mock import AsyncMock

from app.features.cs.stats.schemas import DailyActivity, StatsSummary, TagBreakdown
from app.features.cs.stats.service import StatsService, compute_streaks, format_context_summary


def _d(*args):
    return datetime.date(*args)


class TestComputeStreaks:
    def test_empty_dates_returns_zero(self):
        assert compute_streaks([]) == (0, 0)

    def test_single_day_today(self, monkeypatch):
        today = datetime.datetime.now(datetime.timezone.utc).date()
        assert compute_streaks([today]) == (1, 1)

    def test_consecutive_days_ending_today(self):
        today = datetime.datetime.now(datetime.timezone.utc).date()
        dates = [today - datetime.timedelta(days=2), today - datetime.timedelta(days=1), today]
        assert compute_streaks(dates) == (3, 3)

    def test_gap_breaks_current_streak_but_not_longest(self):
        today = datetime.datetime.now(datetime.timezone.utc).date()
        dates = [
            today - datetime.timedelta(days=10),
            today - datetime.timedelta(days=9),
            today - datetime.timedelta(days=8),
            today,
        ]
        current, longest = compute_streaks(dates)
        assert longest == 3
        assert current == 1

    def test_stale_streak_yesterday_still_counts_as_current(self):
        today = datetime.datetime.now(datetime.timezone.utc).date()
        yesterday = today - datetime.timedelta(days=1)
        dates = [yesterday - datetime.timedelta(days=1), yesterday]
        current, longest = compute_streaks(dates)
        assert current == 2

    def test_stale_streak_two_days_ago_resets_current_to_zero(self):
        today = datetime.datetime.now(datetime.timezone.utc).date()
        stale_day = today - datetime.timedelta(days=3)
        dates = [stale_day - datetime.timedelta(days=1), stale_day]
        current, longest = compute_streaks(dates)
        assert current == 0
        assert longest == 2


@pytest.fixture
def mock_session():
    return AsyncMock()


@pytest.fixture
def service(mock_session):
    svc = StatsService(session=mock_session)
    svc._repo = AsyncMock()
    svc._repo.get_daily_activity.return_value = []
    return svc


class TestGetActivity:
    async def test_maps_repo_rows_and_forwards_days(self, service):
        service._repo.get_daily_activity.return_value = [(_d(2026, 8, 1), 3, 2)]
        result = await service.get_activity(30)
        service._repo.get_daily_activity.assert_called_once_with(30)
        assert result == [DailyActivity(date=_d(2026, 8, 1), attempts=3, solved=2)]

    async def test_none_days_means_unbounded(self, service):
        service._repo.get_daily_activity.return_value = []
        await service.get_activity(None)
        service._repo.get_daily_activity.assert_called_once_with(None)


class TestGetSummary:
    async def test_weakest_tags_excludes_low_attempt_tags(self, service):
        service._repo.get_solved_dates.return_value = []
        service._repo.get_total_attempted.return_value = 0
        service._repo.get_total_solved.return_value = 10
        service._repo.get_difficulty_breakdown.return_value = []
        service._repo.get_language_breakdown.return_value = []
        service._repo.get_tag_breakdown.return_value = [
            ("graph", 2, 0, 5),  # below min-attempts threshold, excluded
            ("dp", 5, 1, 6),
            ("greedy", 4, 3, 4),
        ]
        summary = await service.get_summary()
        weak_names = [t.tag for t in summary.weakest_tags]
        assert "graph" not in weak_names
        assert weak_names[0] == "dp"

    async def test_weakest_tags_sorted_ascending_by_solve_rate(self, service):
        service._repo.get_solved_dates.return_value = []
        service._repo.get_total_attempted.return_value = 0
        service._repo.get_total_solved.return_value = 0
        service._repo.get_difficulty_breakdown.return_value = []
        service._repo.get_language_breakdown.return_value = []
        service._repo.get_tag_breakdown.return_value = [
            ("dp", 4, 3, 5),
            ("greedy", 4, 1, 2),
            ("graph", 4, 2, 3),
        ]
        summary = await service.get_summary()
        assert [t.tag for t in summary.weakest_tags] == ["greedy", "graph", "dp"]

    async def test_weakest_tags_tiebreak_by_avg_attempts_per_solve(self, service):
        service._repo.get_solved_dates.return_value = []
        service._repo.get_total_attempted.return_value = 0
        service._repo.get_total_solved.return_value = 0
        service._repo.get_difficulty_breakdown.return_value = []
        service._repo.get_language_breakdown.return_value = []
        # Both tags have solve_rate 0.5 (2/4). "greedy" took more submissions to
        # land those solves, so it should rank as weaker despite the tied rate.
        service._repo.get_tag_breakdown.return_value = [
            ("dp", 4, 2, 3),
            ("greedy", 4, 2, 8),
        ]
        summary = await service.get_summary()
        assert [t.tag for t in summary.weakest_tags] == ["greedy", "dp"]

    async def test_avg_attempts_per_solve_none_when_never_solved(self, service):
        service._repo.get_solved_dates.return_value = []
        service._repo.get_total_attempted.return_value = 0
        service._repo.get_total_solved.return_value = 0
        service._repo.get_difficulty_breakdown.return_value = []
        service._repo.get_language_breakdown.return_value = []
        service._repo.get_tag_breakdown.return_value = [("dp", 4, 0, 6)]
        summary = await service.get_summary()
        assert summary.by_tag[0].avg_attempts_per_solve is None

    async def test_weakest_tags_excludes_high_solve_rate_even_if_relative_minimum(self, service):
        service._repo.get_solved_dates.return_value = []
        service._repo.get_total_attempted.return_value = 0
        service._repo.get_total_solved.return_value = 0
        service._repo.get_difficulty_breakdown.return_value = []
        service._repo.get_language_breakdown.return_value = []
        # All tags solve well; "math" is only the relative minimum, not weak in
        # absolute terms, and shouldn't be reported as a weakest tag.
        service._repo.get_tag_breakdown.return_value = [
            ("math", 18, 17, 20),  # 94%
            ("string", 30, 29, 32),  # 97%
            ("graph theory", 5, 5, 5),  # 100%
        ]
        summary = await service.get_summary()
        assert summary.weakest_tags == []

    async def test_weakest_tags_low_volume_higher_raw_rate_ranks_weaker_than_high_volume_lower_rate(self, service):
        service._repo.get_solved_dates.return_value = []
        service._repo.get_total_attempted.return_value = 0
        service._repo.get_total_solved.return_value = 0
        service._repo.get_difficulty_breakdown.return_value = []
        service._repo.get_language_breakdown.return_value = []
        # "trie" is 4/5 (80%) on very little evidence; "dp" is 26/40 (65%) on a lot
        # of evidence. Raw solve_rate alone would call dp weaker (65% < 80%), but
        # the confidence-adjusted score should rank trie weaker since its 80% is
        # far less certain than dp's well-established 65%.
        service._repo.get_tag_breakdown.return_value = [
            ("trie", 5, 4, 6),
            ("dp", 40, 26, 45),
        ]
        summary = await service.get_summary()
        assert [t.tag for t in summary.weakest_tags] == ["trie", "dp"]

    async def test_untried_tags_excludes_attempted_and_uses_canonical_list(self, service):
        service._repo.get_solved_dates.return_value = []
        service._repo.get_total_attempted.return_value = 0
        service._repo.get_total_solved.return_value = 0
        service._repo.get_difficulty_breakdown.return_value = []
        service._repo.get_language_breakdown.return_value = []
        service._repo.get_tag_breakdown.return_value = [("dynamic programming", 4, 2, 5)]
        summary = await service.get_summary()
        assert "dynamic programming" not in summary.untried_tags
        assert "graph" in summary.untried_tags
        assert "backtracking" in summary.untried_tags

    async def test_total_attempted_maps_from_repo(self, service):
        service._repo.get_solved_dates.return_value = []
        service._repo.get_total_solved.return_value = 0
        service._repo.get_total_attempted.return_value = 42
        service._repo.get_difficulty_breakdown.return_value = []
        service._repo.get_language_breakdown.return_value = []
        service._repo.get_tag_breakdown.return_value = []
        summary = await service.get_summary()
        assert summary.total_attempted == 42

    async def test_by_day_maps_daily_activity_from_repo(self, service):
        service._repo.get_solved_dates.return_value = []
        service._repo.get_total_attempted.return_value = 0
        service._repo.get_total_solved.return_value = 0
        service._repo.get_difficulty_breakdown.return_value = []
        service._repo.get_language_breakdown.return_value = []
        service._repo.get_tag_breakdown.return_value = []
        service._repo.get_daily_activity.return_value = [(_d(2026, 8, 1), 3, 2)]
        summary = await service.get_summary()
        assert len(summary.by_day) == 1
        assert summary.by_day[0].date == _d(2026, 8, 1)
        assert summary.by_day[0].attempts == 3
        assert summary.by_day[0].solved == 2


def _make_summary(**overrides) -> StatsSummary:
    defaults = dict(
        current_streak=2,
        longest_streak=5,
        total_solved=42,
        total_attempted=60,
        by_difficulty=[],
        by_tag=[],
        by_language=[],
        by_day=[],
        weakest_tags=[],
        untried_tags=[],
    )
    defaults.update(overrides)
    return StatsSummary(**defaults)


class TestFormatContextSummary:
    def test_includes_totals_and_streak(self):
        text = format_context_summary(_make_summary())
        assert "42 solved" in text
        assert "streak 2d" in text
        assert "longest 5d" in text

    def test_includes_weakest_tags(self):
        summary = _make_summary(weakest_tags=[
            TagBreakdown(tag="dp", attempted=10, solved=3, solve_rate=0.3, submissions=15, avg_attempts_per_solve=5.0),
        ])
        text = format_context_summary(summary)
        assert "weakest tags: dp (3/10, 30%)" in text

    def test_includes_untried_tags_capped_at_five(self):
        summary = _make_summary(untried_tags=["a", "b", "c", "d", "e", "f"])
        text = format_context_summary(summary)
        assert "untried tags: a, b, c, d, e" in text
        assert "f" not in text.split("untried tags: ")[1]

    def test_omits_empty_sections(self):
        text = format_context_summary(_make_summary())
        assert "weakest tags" not in text
        assert "untried tags" not in text
