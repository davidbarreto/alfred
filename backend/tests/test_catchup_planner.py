from datetime import datetime, timedelta
from types import SimpleNamespace

from app.features.core.catchup import planner

NOW = datetime(2026, 10, 23, 10, 0)
TOMORROW = NOW.date() + timedelta(days=1)


def _task(
    id=1, priority="MEDIUM", urgency="NORMAL", deadline=None, created_at=None,
    recurrence_rule=None, is_done_in_cycle=False, missed_count=None,
):
    return SimpleNamespace(
        id=id, title=f"Task {id}", priority=priority, urgency=urgency, deadline=deadline,
        created_at=created_at or datetime(2026, 1, 1), recurrence_rule=recurrence_rule,
        is_done_in_cycle=is_done_in_cycle, missed_count=missed_count,
    )


class TestTopTasks:
    def test_picks_overdue_due_today_and_urgent_tasks(self):
        tasks = [
            _task(1, deadline=NOW - timedelta(days=2)),
            _task(2, deadline=NOW + timedelta(hours=3)),
            _task(3, urgency="URGENT"),
            _task(4, deadline=NOW + timedelta(days=3)),
            _task(5),
        ]

        assert {t.id for t in planner.top_tasks(tasks, NOW, limit=10)} == {1, 2, 3}

    def test_higher_priority_first_then_urgent_then_earliest_deadline(self):
        tasks = [
            _task(1, priority="LOW", deadline=NOW - timedelta(days=9)),
            _task(2, priority="HIGH", deadline=NOW - timedelta(days=1)),
            _task(3, priority="HIGH", deadline=NOW - timedelta(days=5)),
            _task(4, priority="HIGH", urgency="URGENT", deadline=NOW - timedelta(days=1)),
        ]

        assert [t.id for t in planner.top_tasks(tasks, NOW)] == [4, 3, 2]

    def test_limited_to_three_by_default(self):
        tasks = [_task(i, deadline=NOW - timedelta(days=i)) for i in range(1, 8)]

        assert len(planner.top_tasks(tasks, NOW)) == 3

    def test_recurring_task_done_this_cycle_is_skipped(self):
        task = _task(1, urgency="URGENT", recurrence_rule="FREQ=WEEKLY;BYDAY=FR", is_done_in_cycle=True)

        assert planner.top_tasks([task], NOW) == []


class TestStaleTasks:
    def test_overdue_beyond_the_threshold_is_stale(self):
        old = _task(1, deadline=NOW - timedelta(days=31))
        fresh = _task(2, deadline=NOW - timedelta(days=29))

        assert [t.id for t in planner.stale_tasks([old, fresh], NOW, NOW, 30)] == [1]

    def test_high_priority_is_never_stale(self):
        task = _task(1, priority="HIGH", deadline=NOW - timedelta(days=100))

        assert planner.stale_tasks([task], NOW, NOW, 30) == []

    def test_recurring_tasks_are_never_stale(self):
        task = _task(1, deadline=NOW - timedelta(days=100), recurrence_rule="FREQ=DAILY")

        assert planner.stale_tasks([task], NOW, NOW, 30) == []

    def test_undated_task_is_stale_only_when_urgent_and_old(self):
        old = datetime(2026, 8, 1)
        urgent_old = _task(1, urgency="URGENT", created_at=old)
        normal_old = _task(2, created_at=old)
        urgent_new = _task(3, urgency="URGENT", created_at=NOW - timedelta(days=5))

        stale = planner.stale_tasks([urgent_old, normal_old, urgent_new], NOW, NOW, 30)

        assert [t.id for t in stale] == [1]

    def test_oldest_deadline_first(self):
        a = _task(1, deadline=NOW - timedelta(days=40))
        b = _task(2, deadline=NOW - timedelta(days=90))

        assert [t.id for t in planner.stale_tasks([a, b], NOW, NOW, 30)] == [2, 1]


class TestMissedHabits:
    def test_threshold_and_ordering(self):
        habits = [
            _task(1, recurrence_rule="FREQ=DAILY", missed_count=2),
            _task(2, recurrence_rule="FREQ=WEEKLY;BYDAY=MO,TU,WE", missed_count=3),
            _task(3, recurrence_rule="FREQ=WEEKLY;BYDAY=MO,TU,WE,TH", missed_count=4),
            _task(4, missed_count=9),
        ]

        assert [t.id for t in planner.missed_habits(habits, 3)] == [3, 2]

    def test_none_missed_count_counts_as_zero(self):
        assert planner.missed_habits([_task(1, recurrence_rule="FREQ=DAILY")], 1) == []


class TestPlanSpread:
    def test_fills_days_from_tomorrow_at_the_daily_cap(self):
        tasks = [_task(i, deadline=NOW - timedelta(days=i)) for i in range(1, 6)]

        moves = planner.plan_spread(tasks, NOW, per_day=2, exclude_ids=set())

        days = [m.new_deadline.date() for m in moves]
        assert days == [TOMORROW, TOMORROW, TOMORROW + timedelta(days=1), TOMORROW + timedelta(days=1),
                        TOMORROW + timedelta(days=2)]

    def test_most_important_goes_first(self):
        tasks = [
            _task(1, priority="LOW", deadline=NOW - timedelta(days=10)),
            _task(2, priority="HIGH", deadline=NOW - timedelta(days=1)),
            _task(3, priority="HIGH", deadline=NOW - timedelta(days=3)),
        ]

        moves = planner.plan_spread(tasks, NOW, per_day=1, exclude_ids=set())

        assert [m.task.id for m in moves] == [3, 2, 1]

    def test_keeps_the_time_of_day(self):
        task = _task(1, deadline=datetime(2026, 10, 1, 14, 30))

        (move,) = planner.plan_spread([task], NOW, per_day=3, exclude_ids=set())

        assert move.new_deadline == datetime.combine(TOMORROW, datetime(2026, 1, 1, 14, 30).time())

    def test_days_already_full_are_skipped(self):
        busy = [_task(100 + i, deadline=datetime.combine(TOMORROW, datetime(2026, 1, 1, 9, 0).time())) for i in range(3)]
        overdue = [_task(1, deadline=NOW - timedelta(days=2))]

        (move,) = planner.plan_spread(busy + overdue, NOW, per_day=3, exclude_ids=set())

        assert move.new_deadline.date() == TOMORROW + timedelta(days=1)

    def test_excluded_recurring_future_and_undated_tasks_are_left_alone(self):
        tasks = [
            _task(1, deadline=NOW - timedelta(days=2)),
            _task(2, deadline=NOW - timedelta(days=2)),
            _task(3, deadline=NOW - timedelta(days=2), recurrence_rule="FREQ=DAILY"),
            _task(4, deadline=NOW + timedelta(days=2)),
            _task(5),
        ]

        moves = planner.plan_spread(tasks, NOW, per_day=3, exclude_ids={2})

        assert [m.task.id for m in moves] == [1]

    def test_gives_up_past_the_horizon(self):
        full = [
            _task(100 + i, deadline=datetime.combine(TOMORROW + timedelta(days=d), datetime(2026, 1, 1, 9, 0).time()))
            for d in range(0, 62) for i in range(3)
        ]
        overdue = [_task(1, deadline=NOW - timedelta(days=2))]

        assert planner.plan_spread(full + overdue, NOW, per_day=3, exclude_ids=set()) == []


class TestDaysOverdue:
    def test_whole_days_overdue(self):
        assert planner.days_overdue(_task(deadline=NOW - timedelta(days=4, hours=3)), NOW) == 4

    def test_none_when_not_overdue_or_undated(self):
        assert planner.days_overdue(_task(deadline=NOW + timedelta(hours=1)), NOW) is None
        assert planner.days_overdue(_task(), NOW) is None
