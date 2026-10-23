from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from app.features.metrics.series.tables import MetricSeries
from app.features.metrics.stats import service as stats_service
from app.features.metrics.stats.repository import StatRow
from app.features.metrics.stats.service import MetricStatsService, _best, _group_stat, _label
from app.features.metrics.stats.schemas import GroupStat

NOW = datetime(2026, 10, 21, 9, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _frozen_now(monkeypatch):
    monkeypatch.setattr(stats_service, "_now", lambda: NOW)


def _row(key=None, n=10, median=2000.0, p90=2500.0, mean=2100.0, low=1800.0, high=2700.0) -> StatRow:
    return StatRow(key=key, n=n, median=median, p90=p90, mean=mean, min=low, max=high)


def _series(kind="duration", name="commute-work") -> MetricSeries:
    return MetricSeries(id=1, name=name, kind=kind, unit="min", is_archived=False, created_at=NOW, updated_at=NOW)


def _stat(label="x", n=10, median=2000.0) -> GroupStat:
    return GroupStat(key=label, label=label, n=n, median=median, low_confidence=n < 5)


class TestLabels:
    @pytest.mark.parametrize(
        "group_by,key,label",
        [("hour", "8", "08:00"), ("hour", "17", "17:00"), ("weekday", "1", "Mon"), ("weekday", "7", "Sun"),
         ("weather", "rain", "Rain"), ("tag", "bus", "bus"), (None, None, "All")],
    )
    def test_label(self, group_by, key, label):
        assert _label(group_by, key) == label


class TestGroupStat:
    def test_few_samples_are_flagged_low_confidence(self):
        assert _group_stat(_row(n=4), None, True).low_confidence is True
        assert _group_stat(_row(n=5), None, True).low_confidence is False

    def test_count_series_keep_only_the_sample_count(self):
        stat = _group_stat(_row(n=12), None, False)
        assert stat.n == 12 and stat.median is None and stat.p90 is None and stat.mean is None


class TestBest:
    def test_picks_the_lowest_median_among_confident_groups(self):
        best = _best([_stat("bus", 10, 2400), _stat("metro", 8, 2000), _stat("car", 3, 900)])
        assert best.label == "metro"

    def test_low_confidence_groups_are_never_ranked(self):
        assert _best([_stat("bus", 10, 2400), _stat("car", 2, 900)]) is None

    def test_needs_two_groups_to_be_a_comparison(self):
        assert _best([_stat("bus", 10, 2400)]) is None
        assert _best([]) is None


def _by_group(overall=None, **groups):
    """A repo.get_stats stand-in: one row for the ungrouped call, the given rows for each grouped call."""

    async def get_stats(series_id, kind, tz, cap, group_by=None, since=None, until=None, tag=None):
        return [overall or _row()] if group_by is None else groups.get(group_by, [])

    return get_stats


class TestGetStats:
    @pytest.fixture
    def service(self):
        svc = MetricStatsService(AsyncMock())
        svc._repo = AsyncMock()
        svc._series = AsyncMock()
        svc._series.get_series_by_name.return_value = _series()
        return svc

    async def test_unknown_series(self, service):
        service._series.get_series_by_name.return_value = None
        assert await service.get_stats("ghost") is None

    async def test_builds_breakdowns_in_display_order(self, service):
        async def get_stats(series_id, kind, tz, cap, group_by=None, since=None, until=None, tag=None):
            return {
                None: [_row()],
                "tag": [_row("metro", 8, 2000), _row("bus", 12, 2400)],
                "hour": [_row("17", 6), _row("8", 9)],
                "weekday": [_row("5", 6), _row("1", 9)],
                "weather": [_row("unknown", 3), _row("rain", 5), _row("dry", 10)],
            }[group_by]

        service._repo.get_stats.side_effect = get_stats
        service._repo.count_over_cap.return_value = 2

        stats = await service.get_stats("commute-work")

        assert [g.label for g in stats.by_tag] == ["bus", "metro"]
        assert [g.label for g in stats.by_hour] == ["08:00", "17:00"]
        assert [g.label for g in stats.by_weekday] == ["Mon", "Fri"]
        assert [g.label for g in stats.by_weather] == ["Dry", "Rain", "Unknown"]
        assert stats.excluded_over_cap == 2 and stats.sample_threshold == 5
        assert stats.best_tag.label == "metro"

    async def test_trend_compares_the_last_30_days_with_the_30_before(self, service):
        service._repo.get_stats.side_effect = _by_group()
        service._repo.count_over_cap.return_value = 0

        await service.get_stats("commute-work")

        windows = [(c.kwargs.get("since"), c.kwargs.get("until")) for c in service._repo.get_stats.await_args_list
                   if c.kwargs.get("group_by") is None]
        recent_start = datetime(2026, 9, 21, 9, 0, tzinfo=timezone.utc)
        previous_start = datetime(2026, 8, 22, 9, 0, tzinfo=timezone.utc)
        assert (recent_start, None) in windows and (previous_start, recent_start) in windows

    async def test_days_and_tag_filters_reach_every_query(self, service):
        service._repo.get_stats.side_effect = _by_group(tag=[_row("bus")], hour=[_row("8")])
        service._repo.count_over_cap.return_value = 0

        await service.get_stats("commute-work", tag="bus", days=7)

        grouped = [c for c in service._repo.get_stats.await_args_list if c.kwargs.get("group_by")]
        assert grouped and all(c.kwargs["tag"] == "bus" for c in grouped)
        assert all(c.kwargs["since"] == datetime(2026, 10, 14, 9, 0, tzinfo=timezone.utc) for c in grouped)

    async def test_count_series_have_no_percentiles_and_no_best(self, service):
        service._series.get_series_by_name.return_value = _series("count", "coffee")
        service._repo.get_stats.side_effect = _by_group(tag=[_row("bus", 9)], hour=[_row("8", 9), _row("9", 9)])

        stats = await service.get_stats("coffee")

        assert stats.overall.median is None and stats.best_tag is None and stats.best_hour is None
        service._repo.count_over_cap.assert_not_awaited()

    async def test_series_without_entries_gives_empty_breakdowns(self, service):
        service._repo.get_stats.side_effect = lambda *a, group_by=None, **k: (
            [_row(n=0, median=None, p90=None, mean=None, low=None, high=None)] if group_by is None else []
        )
        service._repo.count_over_cap.return_value = 0

        stats = await service.get_stats("commute-work")

        assert stats.overall.n == 0 and stats.overall.low_confidence is True
        assert stats.by_tag == [] and stats.by_hour == [] and stats.best_tag is None
